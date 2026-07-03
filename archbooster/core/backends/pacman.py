"""
Pacman/AUR backend — wraps the existing Scanner and Updater so today's proven
pacman + yay/paru logic becomes the first Backend implementation without a
rewrite.

This is the only backend with a *system* layer, so its guardrail
(`categorizer.is_system`, enforced inside `Updater.run`) stays here: selective
updates can never cherry-pick a kernel/driver/core-lib package.
"""
from __future__ import annotations

import shutil
from collections.abc import Iterator

from archbooster.core.backends.base import Backend
from archbooster.core.scanner import Package, Scanner
from archbooster.core.updater import Updater


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
