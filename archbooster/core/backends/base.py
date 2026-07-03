"""
Backend interface — the seam that lets ArchBooster coordinate several package
managers behind one UI instead of hardcoding pacman.

Each backend wraps a single package manager and answers four questions the rest
of the app needs:

  is_available()  → is this package manager actually installed on this host?
  scan()          → which of its packages have updates?  (list[Package])
  update(names)   → run a selective, app-layer update of the named packages.
  full_upgrade()  → run this backend's whole-layer upgrade.
  changelog(pkg)  → optional: what changed in this pending update? (str | None)

Identifying attributes:

  name              — short id for the backend itself ("pacman", "flatpak");
                      used by the registry and in diagnostics.
  sources           — the Package.source tags this backend produces and owns.
                      The registry routes an update to the backend whose
                      `sources` contains the package's source, and the dashboard
                      groups rows by source. pacman emits two ("official",
                      "AUR"); Flatpak will emit one ("Flatpak").
  has_system_layer  — True only for backends that manage OS/driver packages
                      (pacman). Those are the only ones a full `-Syu`-style
                      upgrade applies to; app-only backends like Flatpak leave
                      it False.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from archbooster.core.scanner import Package


class Backend(ABC):
    name: str = ""
    sources: tuple[str, ...] = ()
    has_system_layer: bool = False

    @abstractmethod
    def is_available(self) -> bool:
        """True if this package manager is installed and usable on this host."""

    @abstractmethod
    def scan(self) -> list[Package]:
        """Return the packages this backend has updates for.

        Backends never cache — the registry owns caching so the combined,
        multi-backend result is stored exactly once.
        """

    @abstractmethod
    def update(self, names: list[str]) -> Iterator[str]:
        """Yield output lines while selectively updating the named packages."""

    @abstractmethod
    def full_upgrade(self) -> Iterator[str]:
        """Yield output lines while running this backend's full upgrade."""

    def owns(self, package: Package) -> bool:
        """True if `package` came from (and is updated by) this backend."""
        return package.source in self.sources

    def changelog(self, package: Package) -> str | None:
        """Return a human-readable changelog/diff for `package`'s pending
        update, or None if this backend has no way to produce one.

        Concrete by default (unlike the methods above) — most backends won't
        have anything meaningful to show for every package, so returning None
        is a valid, common answer rather than something every backend must
        implement.
        """
        return None
