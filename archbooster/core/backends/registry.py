"""
Backend registry — the unified entry point over every package manager
ArchBooster supports.

Responsibilities:
  * Auto-detect which backends are usable on this host (via each backend's
    is_available(), a shutil.which check underneath), so the app works on
    Arch (pacman/AUR), on a Flatpak-only distro, or on both at once.
  * Aggregate a single, combined list of pending updates across backends and
    cache it to ~/.cache/archbooster/pending.json for fast TUI startup after a
    background daemon scan.
  * Route a selective update to the backend that owns each package, and a full
    upgrade to the backend(s) that actually have a system layer.

Adding a new package manager is one line — append its class to
BACKEND_CLASSES; everything else here already iterates generically.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from archbooster.core.backends.apt import AptBackend
from archbooster.core.backends.base import Backend
from archbooster.core.backends.brew import BrewBackend
from archbooster.core.backends.dnf import DnfBackend
from archbooster.core.backends.flatpak import FlatpakBackend
from archbooster.core.backends.pacman import PacmanBackend
from archbooster.core.backends.snap import SnapBackend
from archbooster.core.scanner import Package
from archbooster.core.snapshot import SnapshotManager

CACHE_FILE = Path.home() / ".cache" / "archbooster" / "pending.json"
CACHE_TTL = timedelta(hours=1)

# Every backend ArchBooster knows how to drive. A backend only participates if
# its is_available() is True on this host — that's what makes a Flatpak-only
# (non-Arch) host degrade cleanly instead of showing a misleading empty list.
BACKEND_CLASSES: list[type[Backend]] = [
    PacmanBackend, FlatpakBackend, AptBackend, DnfBackend, SnapBackend, BrewBackend,
]


class BackendRegistry:
    def __init__(self, confirm: bool = False) -> None:
        # confirm is forwarded to backends so their updaters honour the
        # config's `confirm` flag; it has no effect on scanning.
        self.backends: list[Backend] = [
            backend
            for backend in (cls(confirm=confirm) for cls in BACKEND_CLASSES)
            if backend.is_available()
        ]

    # ---- scanning -------------------------------------------------- #

    def scan(self, force: bool = False) -> list[Package]:
        """Combined pending updates across all available backends.

        Returns the cached result when it is still fresh, unless `force` is set.
        """
        if not force and self._cache_is_fresh():
            return self._load_cache()
        packages: list[Package] = []
        for backend in self.backends:
            packages += backend.scan()
        self._save_cache(packages)
        return packages

    def list_installed(self) -> list[Package]:
        """Every installed package across all available backends, as
        up-to-date rows. Uncached — local package-list queries (`pacman -Q`,
        `flatpak list`) are milliseconds, unlike the network-bound scan."""
        installed: list[Package] = []
        for backend in self.backends:
            installed += backend.list_installed()
        return installed

    # ---- updating -------------------------------------------------- #

    def backend_for(self, package: Package) -> Backend | None:
        """The backend that owns `package` (by its source tag), or None."""
        for backend in self.backends:
            if backend.owns(package):
                return backend
        return None

    def update(self, packages: list[Package]) -> Iterator[str]:
        """Selectively update `packages`, routing each to its owning backend.

        Packages are grouped by backend so each package manager is invoked once.
        """
        by_backend: dict[int, tuple[Backend, list[str]]] = {}
        for pkg in packages:
            backend = self.backend_for(pkg)
            if backend is None:
                yield f"[archbooster] No backend for {pkg.name} ({pkg.source}); skipping.\n"
                continue
            by_backend.setdefault(id(backend), (backend, []))[1].append(pkg.name)
        for backend, names in by_backend.values():
            yield from backend.update(names)

    def update_apps(
        self,
        selected: list[Package],
        pending: list[Package],
        snapshot: SnapshotManager | None = None,
    ) -> Iterator[str]:
        """The apps-first update (Phase 7): update `selected`, hold back
        everything else in `pending` — the system layer always is.

        Each backend gets one invocation with its own selected/held split;
        for pacman that becomes a single `-Syu --ignore=<held>` instead of
        per-package cherry-picks. Because the system-layer sync now really
        advances libraries, a snapshot is taken first (when available), same
        safety net as the full-upgrade path.
        """
        if not selected:
            yield "[archbooster] Nothing selected to update.\n"
            return

        for pkg in selected:
            if self.backend_for(pkg) is None:
                yield f"[archbooster] No backend for {pkg.name} ({pkg.source}); skipping.\n"

        selected_keys = {(p.source, p.name) for p in selected}
        snapshot_taken = False
        for backend in self.backends:
            backend_selected = [p for p in selected if backend.owns(p)]
            if not backend_selected:
                continue
            backend_held = [
                p for p in pending
                if backend.owns(p) and (p.source, p.name) not in selected_keys
            ]
            if (backend.has_system_layer and not snapshot_taken
                    and snapshot is not None and snapshot.is_available()):
                snapshot_taken = True
                yield f"[archbooster] Creating {snapshot.backend} snapshot before update...\n"
                snap_id = snapshot.create("archbooster: pre-app-update")
                if snap_id:
                    yield f"[archbooster] Snapshot created: {snap_id}\n"
                else:
                    yield "[archbooster] Snapshot creation failed; continuing without one.\n"
            yield from backend.update_apps(backend_selected, backend_held)

    def full_upgrade(self, snapshot: SnapshotManager | None = None) -> Iterator[str]:
        """Run a full upgrade on every backend that has a system layer.

        Today that is pacman/apt/dnf; app-only backends like Flatpak have no
        OS layer and are excluded from the full-upgrade path.

        If `snapshot` is given and available, a snapshot is created first —
        the pre-upgrade safety net so a broken full upgrade can be rolled
        back. Snapshot creation failing or being unavailable never blocks the
        upgrade itself; it's a bonus, not a requirement.
        """
        ran = False
        for backend in self.backends:
            if backend.has_system_layer:
                if not ran and snapshot is not None and snapshot.is_available():
                    yield f"[archbooster] Creating {snapshot.backend} snapshot before full upgrade...\n"
                    snap_id = snapshot.create("archbooster: pre-full-upgrade")
                    if snap_id:
                        yield f"[archbooster] Snapshot created: {snap_id}\n"
                    else:
                        yield "[archbooster] Snapshot creation failed; continuing without one.\n"
                ran = True
                yield from backend.full_upgrade()
        if not ran:
            yield "[archbooster] No system-layer backend available for full upgrade.\n"

    # ---- cache ----------------------------------------------------- #

    def _cache_is_fresh(self) -> bool:
        if not CACHE_FILE.exists():
            return False
        mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
        return datetime.now() - mtime < CACHE_TTL

    def _load_cache(self) -> list[Package]:
        data = json.loads(CACHE_FILE.read_text())
        return [Package(**p) for p in data]

    def _save_cache(self, packages: list[Package]) -> None:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps([asdict(p) for p in packages], indent=2))
