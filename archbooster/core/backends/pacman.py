"""
Pacman/AUR backend — wraps the existing Scanner and Updater so today's proven
pacman + yay/paru logic becomes the first Backend implementation without a
rewrite.

This is the only backend with a *system* layer, so its guardrail
(`categorizer.is_system`, enforced inside `Updater.run`) stays here: selective
updates can never cherry-pick a kernel/driver/core-lib package.
"""
from __future__ import annotations

import difflib
import shutil
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from archbooster.core.backends.base import Backend
from archbooster.core.scanner import Package, Scanner
from archbooster.core.updater import Updater

# AUR's cgit mirror serves the raw PKGBUILD for any package at this stable URL
# — no auth, no cloning needed just to read it.
AUR_PKGBUILD_URL = "https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h={name}"


class PacmanBackend(Backend):
    name = "pacman"
    # checkupdates -> "official"; yay/paru -Qu --aur -> "AUR".
    sources = ("official", "AUR")
    has_system_layer = True

    def __init__(self, confirm: bool = False) -> None:
        self._scanner = Scanner()
        self._updater = Updater(confirm=confirm)

    def is_available(self) -> bool:
        # Usable if we can either detect updates (checkupdates) or apply them
        # (pacman / an AUR helper). On a non-Arch host none of these exist, so
        # the backend simply drops out of the registry.
        return any(shutil.which(tool)
                   for tool in ("checkupdates", "pacman", "yay", "paru"))

    def scan(self) -> list[Package]:
        return self._scanner.scan()

    def update(self, names: list[str]) -> Iterator[str]:
        return self._updater.run(names)

    def full_upgrade(self) -> Iterator[str]:
        return self._updater.run_full_upgrade()

    def changelog(self, package: Package) -> str | None:
        """PKGBUILD diff for AUR packages, fetched from AUR's cgit mirror and
        diffed against a locally cached PKGBUILD (yay/paru's build cache) when
        one exists.

        Official-repo packages return None — Arch doesn't publish a
        machine-readable per-package changelog ArchBooster can fetch offline,
        so faking one would be worse than admitting there's nothing to show.
        """
        if package.source != "AUR":
            return None
        try:
            with urllib.request.urlopen(
                AUR_PKGBUILD_URL.format(name=package.name), timeout=10
            ) as response:
                remote_pkgbuild = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, ValueError):
            return None

        local_path = self._local_pkgbuild_path(package.name)
        if local_path is None:
            return (
                f"No local PKGBUILD cached for {package.name} to diff against.\n\n"
                f"Latest PKGBUILD from AUR:\n\n{remote_pkgbuild}"
            )

        local_pkgbuild = local_path.read_text(errors="replace")
        diff = "".join(difflib.unified_diff(
            local_pkgbuild.splitlines(keepends=True),
            remote_pkgbuild.splitlines(keepends=True),
            fromfile=f"{package.name}/PKGBUILD (installed)",
            tofile=f"{package.name}/PKGBUILD (latest)",
        ))
        return diff or "No PKGBUILD changes detected."

    def _local_pkgbuild_path(self, name: str) -> Path | None:
        home = Path.home()
        for candidate in (
            home / ".cache" / "yay" / name / "PKGBUILD",
            home / ".cache" / "paru" / "clone" / name / "PKGBUILD",
        ):
            if candidate.exists():
                return candidate
        return None
