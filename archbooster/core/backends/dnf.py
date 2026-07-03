"""
dnf backend — Fedora/RHEL (and derivatives). Alongside apt.py, this covers the
major desktop package managers beyond Arch + Flatpak.

Fedora package names don't match Arch's system-layer patterns (`kernel-core`
instead of `linux`, `glibc` is shared but `mesa`/driver names differ), so this
backend enforces its own guardrail using `categorizer.DNF_CRITICAL_PATTERNS`
rather than the Arch-shaped default in `categorizer.is_system()`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterator

from archbooster.core.backends.base import Backend
from archbooster.core.categorizer import DNF_CRITICAL_PATTERNS, is_system
from archbooster.core.procutil import stream_subprocess
from archbooster.core.scanner import Package

# `dnf check-update` output, one line per package (after a header line and a
# blank line, and an optional "Obsoleting Packages" section we don't want):
#   firefox.x86_64                    120.0-1.fc39                    updates
# exits 100 (not 0) when updates are found — that's expected, not an error.
_LINE_RE = re.compile(r"^(?P<namearch>\S+)\s+(?P<version>\S+)\s+(?P<repo>\S+)$")


class DnfBackend(Backend):
    name = "dnf"
    sources = ("dnf",)
    has_system_layer = True

    def __init__(self, confirm: bool = False) -> None:
        self.confirm = confirm

    def is_available(self) -> bool:
        return shutil.which("dnf") is not None

    def scan(self) -> list[Package]:
        """Return pending dnf updates via `dnf check-update` (no root)."""
        if not shutil.which("dnf"):
            return []
        try:
            result = subprocess.run(
                ["dnf", "check-update"],
                capture_output=True, text=True, timeout=90,
            )
            # returncode 100 = updates available, 0 = none, both are success
            # for our purposes; anything else means check-update itself failed.
            if result.returncode not in (0, 100):
                return []
            packages = []
            for line in result.stdout.splitlines():
                pkg = self._parse_line(line)
                if pkg:
                    packages.append(pkg)
            return packages
        except subprocess.TimeoutExpired:
            return []

    def update(self, names: list[str]) -> Iterator[str]:
        """Yield output lines while selectively upgrading the named packages.

        System-layer packages (kernel, systemd, glibc, drivers, ...) are
        filtered out here so a partial upgrade of Fedora's system layer can't
        happen by accident — the same guardrail PacmanBackend enforces, using
        dnf's own package-name patterns.
        """
        if not names:
            return

        blocked = [n for n in names if is_system(n, base_critical=DNF_CRITICAL_PATTERNS)]
        allowed = [n for n in names if n not in blocked]

        if blocked:
            yield (
                "[archbooster] Skipping system packages (use Full system "
                f"upgrade instead): {', '.join(blocked)}\n"
            )
        if not allowed:
            yield "[archbooster] Nothing to update — only system packages were selected.\n"
            return

        cmd = self._build_update_command(allowed)
        yield from self._stream(cmd)

    def full_upgrade(self) -> Iterator[str]:
        """Yield output lines while running `dnf upgrade` (the system layer)."""
        yield from self._stream(self._build_full_upgrade_command())

    # ------------------------------------------------------------------ #

    def _build_update_command(self, names: list[str]) -> list[str]:
        return ["sudo", "dnf", "upgrade", *self._yes(), *names]

    def _build_full_upgrade_command(self) -> list[str]:
        return ["sudo", "dnf", "upgrade", *self._yes()]

    def _yes(self) -> list[str]:
        return [] if self.confirm else ["-y"]

    def _parse_line(self, line: str) -> Package | None:
        line = line.strip()
        if not line or line == "Obsoleting Packages":
            return None
        match = _LINE_RE.match(line)
        if not match or "." not in match.group("namearch"):
            return None
        name = match.group("namearch").rsplit(".", 1)[0]
        return Package(
            name=name,
            current="?",   # check-update doesn't expose the installed version
            new=match.group("version"),
            source="dnf",
            priority="normal",
        )

    def _stream(self, cmd: list[str]) -> Iterator[str]:
        yield from stream_subprocess(cmd)
