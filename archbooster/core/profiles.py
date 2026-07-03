"""
Update profiles / pinning — named groups of package-name patterns from
config.toml's [profiles] section (e.g. `browsers = ["firefox", "chromium",
"*chrome*"]`). Used two places:

  - the dashboard's profile filter (press [P] to cycle profiles, pre-selecting
    matching rows so [ENTER] updates just that group), and
  - the daemon's opt-in auto-update ([automation] auto_update_profile), which
    only ever touches packages a profile matches.

Patterns are fnmatch globs: a plain name ("firefox") is an exact match, "*"
wildcards make it a prefix/suffix/substring match ("*chrome*").
"""
from __future__ import annotations

import fnmatch

from archbooster.core.scanner import Package


def matches_profile(name: str, patterns: list[str]) -> bool:
    nl = name.lower()
    return any(fnmatch.fnmatch(nl, pattern.lower()) for pattern in patterns)


def filter_by_profile(packages: list[Package], patterns: list[str]) -> list[Package]:
    return [pkg for pkg in packages if matches_profile(pkg.name, patterns)]
