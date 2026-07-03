"""
GUI-app detection for native packages.

"User-facing app" has no formal definition in pacman's metadata, but there is
a reliable proxy every desktop environment already uses: a package that ships
a .desktop launcher is something the user starts from a menu. One batched
`pacman -Qqo <all .desktop files>` resolves every launcher to its owning
package in a single subprocess call, so this stays cheap even with hundreds
of launchers installed.

Flatpak/Snap packages never go through this — they are user-facing apps by
definition and the categorizer tags them "apps" without a lookup.
"""
from __future__ import annotations

import glob
import shutil
import subprocess
from functools import lru_cache

DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
)


@lru_cache(maxsize=1)
def gui_package_names() -> frozenset[str]:
    """Names of installed native packages that ship a .desktop launcher.

    Cached for the process lifetime — the set only changes when packages are
    installed/removed, at which point ArchBooster is restarted or rescanning
    anyway. Returns an empty set on non-pacman hosts (apt/dnf hosts then fall
    back to "cli" for native packages, which is the safe default).
    """
    if not shutil.which("pacman"):
        return frozenset()
    desktop_files: list[str] = []
    for directory in DESKTOP_DIRS:
        desktop_files += glob.glob(f"{directory}/*.desktop")
    if not desktop_files:
        return frozenset()
    try:
        # -Qqo prints just the owning package name, one per owned file;
        # unowned files only produce stderr noise, which we ignore.
        result = subprocess.run(
            ["pacman", "-Qqo", *desktop_files],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return frozenset()
    return frozenset(line.strip() for line in result.stdout.splitlines() if line.strip())
