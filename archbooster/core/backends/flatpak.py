"""
Flatpak backend — the backend that reaches "all Linux". Flatpak ships on
essentially every desktop distro (Fedora, Ubuntu, openSUSE, Arch, ...)
regardless of the underlying system package manager, so this one backend is
what turns ArchBooster from Arch-only into cross-distro.

Every Flatpak is a sandboxed, per-user application — there is no system/driver
layer here, so unlike PacmanBackend this backend has no `is_system` guardrail
to enforce. `has_system_layer` stays False and every scanned package is always
safe to cherry-pick.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator

from archbooster.core.backends.base import Backend
from archbooster.core.procutil import stream_subprocess
from archbooster.core.scanner import Package


class FlatpakBackend(Backend):
    name = "flatpak"
    sources = ("Flatpak",)
    has_system_layer = False

    def __init__(self, confirm: bool = False) -> None:
        # Mirrors PacmanBackend/Updater: confirm=False runs non-interactively
        # (`-y`); confirm=True surfaces flatpak's own confirmation prompt.
        self.confirm = confirm

    def is_available(self) -> bool:
        return shutil.which("flatpak") is not None

    def scan(self) -> list[Package]:
        """Return pending Flatpak updates (no root needed)."""
        if not shutil.which("flatpak"):
            return []
        try:
            result = subprocess.run(
                ["flatpak", "remote-ls", "--updates",
                 "--columns=application,version"],
                capture_output=True, text=True, timeout=60,
            )
            return [self._parse_line(line)
                    for line in result.stdout.strip().splitlines() if line]
        except subprocess.TimeoutExpired:
            return []

    def update(self, names: list[str]) -> Iterator[str]:
        """Yield output lines while selectively updating the named app ids."""
        if not names:
            return
        yield from self._stream(self._build_update_command(names))

    def full_upgrade(self) -> Iterator[str]:
        """Yield output lines while updating every installed Flatpak."""
        yield from self._stream(self._build_full_upgrade_command())

    # ------------------------------------------------------------------ #

    def _build_update_command(self, names: list[str]) -> list[str]:
        return ["flatpak", "update", *self._yes(), *names]

    def _build_full_upgrade_command(self) -> list[str]:
        return ["flatpak", "update", *self._yes()]

    def _yes(self) -> list[str]:
        return [] if self.confirm else ["-y"]

    def _parse_line(self, line: str) -> Package:
        # Format (tab-separated): <application-id>\t<version>. `version` is
        # blank for refs without an appstream <releases> entry.
        parts = line.split("\t")
        name = parts[0].strip()
        new = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "?"
        return Package(
            name=name,
            current="?",   # remote-ls --updates doesn't expose the installed
                            # version; the dashboard shows "? -> new" for these.
            new=new,
            source="Flatpak",
            priority="normal",
        )

    def _stream(self, cmd: list[str]) -> Iterator[str]:
        yield from stream_subprocess(cmd)

    def changelog(self, package: Package) -> str | None:
        """OSTree commit log for this app's pending update, via
        `flatpak remote-info --log`.

        `remote-ls --updates` doesn't say which remote an app came from, so
        this tries every configured remote until one has a log for the app id
        and returns that.
        """
        if not shutil.which("flatpak"):
            return None
        try:
            remotes_result = subprocess.run(
                ["flatpak", "remotes", "--columns=name"],
                capture_output=True, text=True, timeout=15,
            )
        except subprocess.TimeoutExpired:
            return None

        remotes = [r.strip() for r in remotes_result.stdout.splitlines() if r.strip()]
        for remote in remotes:
            try:
                result = subprocess.run(
                    ["flatpak", "remote-info", "--log", remote, package.name],
                    capture_output=True, text=True, timeout=30,
                )
            except subprocess.TimeoutExpired:
                continue
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        return None
