"""
apt backend — Debian/Ubuntu (and derivatives). Alongside dnf.py, this is what
takes ArchBooster from "Arch + Flatpak" to genuinely covering the major desktop
package managers.

Debian package names don't match Arch's system-layer patterns (`linux-image-*`
instead of `linux`, `libc6` instead of `glibc`, ...), so this backend enforces
its own guardrail using `categorizer.APT_CRITICAL_PATTERNS` rather than the
Arch-shaped default in `categorizer.is_system()`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterator

from archbooster.core.backends.base import Backend
from archbooster.core.categorizer import (
    APT_ALWAYS_UPGRADE_PATTERNS,
    APT_CRITICAL_PATTERNS,
    never_cherry_pick,
)
from archbooster.core.procutil import stream_subprocess
from archbooster.core.scanner import Package

# `apt list --upgradable` output, one line per package:
#   firefox/jammy-updates,jammy-security 120.0+build2 amd64 [upgradable from: 119.0]
# The repo field (after the "/") can list multiple repos comma-separated; the
# "[upgradable from: ...]" suffix is present for actual upgrades (always, in
# practice, for this command) but treated as optional to stay tolerant of
# format drift.
_LINE_RE = re.compile(
    r"^(?P<name>\S+?)/\S+\s+(?P<new>\S+)\s+\S+"
    r"(?:\s+\[upgradable from:\s*(?P<current>[^\]]+)\])?"
)


class AptBackend(Backend):
    name = "apt"
    sources = ("apt",)
    has_system_layer = True

    def __init__(self, confirm: bool = False) -> None:
        self.confirm = confirm

    def is_available(self) -> bool:
        return shutil.which("apt-get") is not None or shutil.which("apt") is not None

    def scan(self) -> list[Package]:
        """Return pending apt updates via `apt list --upgradable` (no root)."""
        if not shutil.which("apt"):
            return []
        try:
            result = subprocess.run(
                ["apt", "list", "--upgradable"],
                capture_output=True, text=True, timeout=60,
            )
            packages = []
            for line in result.stdout.splitlines():
                if not line or line.startswith("Listing..."):
                    continue
                pkg = self._parse_line(line)
                if pkg:
                    packages.append(pkg)
            return packages
        except subprocess.TimeoutExpired:
            return []

    def update(self, names: list[str]) -> Iterator[str]:
        """Yield output lines while selectively upgrading the named packages.

        Neither non-app layer may be cherry-picked here — not the kernel/driver
        block, and not the core ABI libs (libc6, libssl, systemd) either — so a
        partial upgrade of Debian's system layer can't happen by accident. Same
        guardrail PacmanBackend enforces, using apt's own name patterns.
        """
        if not names:
            return

        blocked = [n for n in names if never_cherry_pick(
            n, base_critical=APT_CRITICAL_PATTERNS, base_core=APT_ALWAYS_UPGRADE_PATTERNS)]
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
        """Yield output lines while running `apt-get upgrade` (the system layer)."""
        yield from self._stream(self._build_full_upgrade_command())

    # ------------------------------------------------------------------ #

    def _build_update_command(self, names: list[str]) -> list[str]:
        return ["sudo", "apt-get", "install", "--only-upgrade", *self._yes(), *names]

    def _build_full_upgrade_command(self) -> list[str]:
        return ["sudo", "apt-get", "upgrade", *self._yes()]

    def _yes(self) -> list[str]:
        return [] if self.confirm else ["-y"]

    def _parse_line(self, line: str) -> Package | None:
        match = _LINE_RE.match(line)
        if not match:
            return None
        current = (match.group("current") or "?").strip()
        return Package(
            name=match.group("name"),
            current=current or "?",
            new=match.group("new"),
            source="apt",
            priority="normal",
        )

    def _stream(self, cmd: list[str]) -> Iterator[str]:
        yield from stream_subprocess(cmd)
