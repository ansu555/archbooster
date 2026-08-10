"""
Scans for available pacman/AUR updates:
  - checkupdates   (official repos, no root needed)
  - yay -Qu --aur  (AUR packages)

Returns a list of Package dataclasses. This class only does the raw pacman-side
scan; caching of the combined, multi-backend result lives in
`archbooster.core.backends.registry`, not here.
"""
import subprocess
import shutil
from dataclasses import dataclass


@dataclass
class Package:
    name:     str
    current:  str
    new:      str
    source:   str    # "official" | "AUR" | "Flatpak" | ...
    priority: str    # "critical" | "normal" | "optional"  (set by categorizer)
    # status defaults to "update" so cached pending.json files written before
    # this field existed still deserialize; "up-to-date" rows come only from
    # Backend.list_installed().
    status:   str = "update"      # "update" | "up-to-date"
    # Display taxonomy in user vocabulary ("drivers", not "critical") — set by
    # categorizer.categorize(); purely presentational, never a safety input.
    category: str = ""            # "apps" | "cli" | "drivers" | "kernel"
                                  # | "system" | "fonts-themes"


class Scanner:
    def scan(self) -> list[Package]:
        """Return all pending pacman + AUR updates (raw, uncached)."""
        return self._scan_official() + self._scan_aur()

    # ------------------------------------------------------------------ #

    def _scan_official(self) -> list[Package]:
        """Run checkupdates (pacman-contrib). Safe — no root needed."""
        if not shutil.which("checkupdates"):
            return self._scan_official_via_helper()
        try:
            result = subprocess.run(
                ["checkupdates"],
                capture_output=True, text=True, timeout=60
            )
            # exit code 2 = no updates (not an error)
            return [self._parse_line(line, "official")
                    for line in result.stdout.strip().splitlines() if line]
        except subprocess.TimeoutExpired:
            return []

    def _scan_official_via_helper(self) -> list[Package]:
        """Official-repo updates via `yay/paru -Qu --repo`, for hosts without
        pacman-contrib installed.

        Returning an empty list here instead would be actively dangerous, not
        merely incomplete: the apps-first update derives its `--ignore` hold
        list from the scan, so an official scan that silently reports "nothing
        pending" turns `-Syu --ignore=<held>` into a bare `-Syu` — a full
        system upgrade, kernel and drivers included, from a screen that
        promised to hold them back.

        Unlike checkupdates this reads the local sync database rather than a
        freshly synced temporary one, so it can lag until the next sync. A
        slightly stale hold list is a far better failure mode than none.
        """
        helper = self._detect_aur_helper()
        if not helper:
            return []
        try:
            result = subprocess.run(
                [helper, "-Qu", "--repo"],
                capture_output=True, text=True, timeout=90
            )
            return [self._parse_line(line, "official")
                    for line in result.stdout.strip().splitlines() if line]
        except subprocess.TimeoutExpired:
            return []

    def _scan_aur(self) -> list[Package]:
        """Run yay/paru -Qu for AUR-only updates."""
        helper = self._detect_aur_helper()
        if not helper:
            return []
        try:
            result = subprocess.run(
                [helper, "-Qu", "--aur"],
                capture_output=True, text=True, timeout=90
            )
            return [self._parse_line(line, "AUR")
                    for line in result.stdout.strip().splitlines() if line]
        except subprocess.TimeoutExpired:
            return []

    def _parse_line(self, line: str, source: str) -> Package:
        # Format: <name> <current> -> <new>
        parts = line.split()
        return Package(
            name=parts[0],
            current=parts[1] if len(parts) > 1 else "?",
            new=parts[3]     if len(parts) > 3 else "?",
            source=source,
            priority="normal",
        )

    def _detect_aur_helper(self) -> str | None:
        for h in ("yay", "paru"):
            if shutil.which(h):
                return h
        return None
