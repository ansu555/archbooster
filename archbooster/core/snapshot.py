"""
Snapshot + rollback — the killer feature for the SYSTEM layer per the roadmap:
no single command (`pacman -Syu`, `apt upgrade`, `dnf upgrade`) gives you an
undo button for a full system upgrade. This wraps whichever snapshot tool is
already on the host — snapper (the near-universal choice on Arch/openSUSE-style
btrfs setups) or timeshift (a common cross-distro alternative, rsync or btrfs
backed) — so a full upgrade can be preceded by a snapshot and, if it breaks
something, rolled back.

This is a safety *bonus*, not a hard requirement: `is_available()` is False
(and every method no-ops) when neither tool is installed, so a full upgrade
still runs normally on a host without either one configured.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass

from archbooster.core.procutil import stream_subprocess

# The snapper config name for the root subvolume — the near-universal
# convention (Arch wiki's "Snapper" page, openSUSE's default) for a config
# that snapshots `/`. A host with a differently-named config isn't supported
# here; that's a reasonable MVP scope.
SNAPPER_CONFIG = "root"


@dataclass
class Snapshot:
    id:          str
    date:        str
    description: str
    backend:     str   # "snapper" | "timeshift"


class SnapshotManager:
    def __init__(self, backend: str = "auto") -> None:
        # `backend` mirrors config.toml's [snapshot].backend: "auto" picks
        # whichever tool is installed (snapper first), "snapper"/"timeshift"
        # pins one, "none" disables the feature entirely.
        self.backend = self._detect(backend)

    def _detect(self, backend: str) -> str | None:
        if backend == "none":
            return None
        if backend in ("snapper", "timeshift"):
            return backend if shutil.which(backend) else None
        if shutil.which("snapper"):
            return "snapper"
        if shutil.which("timeshift"):
            return "timeshift"
        return None

    def is_available(self) -> bool:
        return self.backend is not None

    # ---- create ------------------------------------------------------ #

    def create(self, description: str) -> str | None:
        """Create a snapshot, returning its id, or None on failure/unavailable."""
        if not self.is_available():
            return None
        try:
            if self.backend == "snapper":
                result = subprocess.run(
                    ["sudo", "snapper", "-c", SNAPPER_CONFIG, "create",
                     "--description", description, "--print-number"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    return None
                return result.stdout.strip() or None
            else:  # timeshift
                result = subprocess.run(
                    ["sudo", "timeshift", "--create",
                     "--comments", description, "--scripted"],
                    capture_output=True, text=True, timeout=300,
                )
                return description if result.returncode == 0 else None
        except subprocess.TimeoutExpired:
            return None

    # ---- list ---------------------------------------------------------- #

    def list(self) -> list[Snapshot]:
        if not self.is_available():
            return []
        return self._list_snapper() if self.backend == "snapper" else self._list_timeshift()

    def _list_snapper(self) -> list[Snapshot]:
        try:
            result = subprocess.run(
                ["snapper", "--jsonout", "-c", SNAPPER_CONFIG, "list"],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        entries = data.get(SNAPPER_CONFIG, [])
        return [
            Snapshot(
                id=str(entry.get("number")),
                date=entry.get("date") or "",
                description=entry.get("description") or "",
                backend="snapper",
            )
            for entry in entries
        ]

    # `timeshift --list` prints a header/rule block then rows like:
    #   0    2024-01-01_12-00-00   O    Ondemand snapshot
    _TIMESHIFT_LINE_RE = re.compile(
        r"^(?P<num>\d+)\s+(?P<name>\S+)\s+(?P<tags>\S+)\s+(?P<desc>.*)$"
    )

    def _list_timeshift(self) -> list[Snapshot]:
        try:
            result = subprocess.run(
                ["timeshift", "--list", "--scripted"],
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return []
        snapshots = []
        for line in result.stdout.splitlines():
            match = self._TIMESHIFT_LINE_RE.match(line.strip())
            if not match:
                continue
            snapshots.append(Snapshot(
                id=match.group("name"),
                date=match.group("name"),  # timeshift names snapshots by timestamp
                description=match.group("desc").strip(),
                backend="timeshift",
            ))
        return snapshots

    # ---- rollback ------------------------------------------------------- #

    def rollback(self, snapshot_id: str) -> Iterator[str]:
        """Yield output lines while rolling back to `snapshot_id`.

        For snapper this creates a new default subvolume that takes effect on
        next boot (needs the host's bootloader/subvolume layout to support
        it — `snapper rollback`'s own documented behaviour, not something
        ArchBooster can guarantee). For timeshift this restores in place.
        """
        if not self.is_available():
            yield "[archbooster] No snapshot backend available.\n"
            return
        if self.backend == "snapper":
            cmd = ["sudo", "snapper", "-c", SNAPPER_CONFIG, "rollback", snapshot_id]
        else:
            cmd = ["sudo", "timeshift", "--restore", "--snapshot", snapshot_id, "--yes"]
        yield from stream_subprocess(cmd)
