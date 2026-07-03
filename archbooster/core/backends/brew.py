"""
Homebrew backend — `brew` (Linuxbrew on Linux), mostly used for CLI dev tools
rather than GUI apps, plus GUI apps distributed as casks.

Fully user-space (installs under the user's home directory, never run as
root — Homebrew explicitly warns against sudo), so like Flatpak/Snap there's
no system layer and no `is_system` guardrail to enforce.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterator

from archbooster.core.backends.base import Backend
from archbooster.core.procutil import stream_subprocess
from archbooster.core.scanner import Package

# `brew outdated --verbose` output, one line per formula/cask:
#   git (2.39.0) < 2.42.0
_LINE_RE = re.compile(r"^(?P<name>\S+)\s+\((?P<current>[^)]+)\)\s*<\s*(?P<new>\S+)$")


class BrewBackend(Backend):
    name = "brew"
    sources = ("brew",)
    has_system_layer = False

    def __init__(self, confirm: bool = False) -> None:
        # `brew upgrade` has no confirmation prompt to skip, so — like
        # SnapBackend — `confirm` is accepted only for interface consistency
        # with the registry's uniform `cls(confirm=confirm)` construction.
        self.confirm = confirm

    def is_available(self) -> bool:
        return shutil.which("brew") is not None

    def scan(self) -> list[Package]:
        """Return pending updates for both formulae and casks."""
        if not shutil.which("brew"):
            return []
        packages = []
        for args in (["outdated", "--verbose"], ["outdated", "--cask", "--verbose"]):
            try:
                result = subprocess.run(
                    ["brew", *args], capture_output=True, text=True, timeout=60,
                )
            except subprocess.TimeoutExpired:
                continue
            for line in result.stdout.splitlines():
                pkg = self._parse_line(line)
                if pkg:
                    packages.append(pkg)
        return packages

    def update(self, names: list[str]) -> Iterator[str]:
        """Yield output lines while selectively upgrading the named formulae/casks."""
        if not names:
            return
        yield from self._stream(["brew", "upgrade", *names])

    def full_upgrade(self) -> Iterator[str]:
        """Yield output lines while upgrading every outdated formula/cask."""
        yield from self._stream(["brew", "upgrade"])

    # ------------------------------------------------------------------ #

    def _parse_line(self, line: str) -> Package | None:
        match = _LINE_RE.match(line.strip())
        if not match:
            return None
        return Package(
            name=match.group("name"),
            current=match.group("current"),
            new=match.group("new"),
            source="brew",
            priority="normal",
        )

    def _stream(self, cmd: list[str]) -> Iterator[str]:
        yield from stream_subprocess(cmd)
