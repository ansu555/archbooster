"""
Host tooling checks — optional dependencies whose absence degrades ArchBooster
quietly rather than loudly.

The motivating case: without `checkupdates` (pacman-contrib), the official-repo
scan has no fresh sync database to read. The apps-first update derives its
`--ignore` hold list from that scan, so an under-reporting scan used to turn
`-Syu --ignore=<held>` into a bare `-Syu` — a full system upgrade launched from
a screen that promised to hold the kernel back. Both halves of that are now
defended in code (`Scanner._scan_official_via_helper` supplies a fallback,
`Updater.SYSTEM_HOLD_GLOBS` pins the system layer regardless), so this module
is not a safety mechanism. It exists so the user knows they are running on the
fallback and can restore the accurate path.

Advisories are pure data; each surface decides how to render them (installer
banner, `--scan` footer, TUI toast).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class Advisory:
    tool:    str   # the missing executable
    package: str   # what to install to get it
    impact:  str   # what the user loses, in their terms
    fix:     str   # the exact command to run


def advisories() -> list[Advisory]:
    """Recommended-but-missing tooling for this host, in priority order.

    Only checks that apply to the host are returned: the pacman-contrib
    advisory is meaningless on a Flatpak-only or Debian machine, so it is
    gated on pacman actually being present.
    """
    found: list[Advisory] = []

    if shutil.which("pacman") and not shutil.which("checkupdates"):
        found.append(Advisory(
            tool="checkupdates",
            package="pacman-contrib",
            impact=(
                "official-repo updates are read from the local sync database "
                "instead of a fresh one, so the list can lag behind until the "
                "next sync"
            ),
            fix="sudo pacman -S pacman-contrib",
        ))

    return found
