"""
Snap backend — Canonical's universal package format (`snap install`, `snap
refresh`). Common on Ubuntu but installable on most distros via `snapd`.

Like Flatpak, every snap is a sandboxed, per-application install — there's no
system/driver layer here, so (also like Flatpak) `has_system_layer` stays
False and there's no `is_system` guardrail to enforce.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator

from archbooster.core.backends.base import Backend
from archbooster.core.procutil import stream_subprocess
from archbooster.core.scanner import Package


class SnapBackend(Backend):
    name = "snap"
    sources = ("snap",)
    has_system_layer = False

    def __init__(self, confirm: bool = False) -> None:
        # Unlike pacman/apt/dnf, `snap refresh` has no confirmation prompt to
        # skip — there's no `-y`-equivalent flag. `confirm` is accepted only
        # for interface consistency with the registry's uniform
        # `cls(confirm=confirm)` construction; it has no effect here.
        self.confirm = confirm

    def is_available(self) -> bool:
        return shutil.which("snap") is not None

    def scan(self) -> list[Package]:
        """Return pending snap updates via `snap refresh --list` (no root)."""
        if not shutil.which("snap"):
            return []
        try:
            result = subprocess.run(
                ["snap", "refresh", "--list"],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            return []
        packages = []
        for line in result.stdout.splitlines():
            pkg = self._parse_line(line)
            if pkg:
                packages.append(pkg)
        return packages

    def update(self, names: list[str]) -> Iterator[str]:
        """Yield output lines while selectively refreshing the named snaps."""
        if not names:
            return
        yield from self._stream(["sudo", "snap", "refresh", *names])

    def full_upgrade(self) -> Iterator[str]:
        """Yield output lines while refreshing every installed snap."""
        yield from self._stream(["sudo", "snap", "refresh"])

    # ------------------------------------------------------------------ #

    def _parse_line(self, line: str) -> Package | None:
        # `snap refresh --list` prints a header row ("Name Version Rev Size
        # Publisher Notes") and, when nothing is pending, a plain sentence
        # ("All snaps up to date.") instead of a table — neither is a package
        # row. A real row's 3rd field (Rev) is always a bare integer, which
        # neither of those look-alikes has, so that's the structural check
        # used to tell them apart rather than matching specific wording.
        parts = line.split()
        if len(parts) < 3 or not parts[2].isdigit():
            return None
        return Package(
            name=parts[0],
            current="?",   # refresh --list only shows the version being refreshed to
            new=parts[1],
            source="snap",
            priority="normal",
        )

    def _stream(self, cmd: list[str]) -> Iterator[str]:
        yield from stream_subprocess(cmd)
