"""Tests for the Backend seam: pacman backend delegation, availability
detection, and the registry's aggregation / caching / update-routing."""
import archbooster.core.backends.flatpak as flat
import archbooster.core.backends.pacman as pac
import archbooster.core.backends.registry as reg
from archbooster.core.backends.base import Backend
from archbooster.core.backends.flatpak import FlatpakBackend
from archbooster.core.backends.pacman import PacmanBackend
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.scanner import Package


def _pkg(name: str, source: str = "official") -> Package:
    return Package(name=name, current="1", new="2", source=source, priority="normal")


# --------------------------------------------------------------------------- #
# PacmanBackend
# --------------------------------------------------------------------------- #

class _StubScanner:
    def scan(self):
        return ["SCANNED"]


class _StubUpdater:
    def __init__(self):
        self.ran = None
        self.full = False

    def run(self, names):
        self.ran = list(names)
        yield "ran\n"

    def run_full_upgrade(self):
        self.full = True
        yield "full\n"


def test_pacman_is_available_true_when_any_tool_present(monkeypatch):
    monkeypatch.setattr(
        pac.shutil, "which",
        lambda name: "/usr/bin/yay" if name == "yay" else None,
    )
    assert PacmanBackend().is_available() is True


def test_pacman_is_available_false_on_non_arch(monkeypatch):
    monkeypatch.setattr(pac.shutil, "which", lambda name: None)
    assert PacmanBackend().is_available() is False


def test_pacman_metadata_marks_system_layer_and_sources():
    b = PacmanBackend()
    assert b.name == "pacman"
    assert b.sources == ("official", "AUR")
    assert b.has_system_layer is True
    assert b.owns(_pkg("firefox", "AUR")) is True
    assert b.owns(_pkg("org.gimp.GIMP", "Flatpak")) is False


def test_pacman_delegates_to_scanner_and_updater():
    b = PacmanBackend()
    b._scanner = _StubScanner()
    b._updater = _StubUpdater()

    assert b.scan() == ["SCANNED"]

    assert list(b.update(["x"])) == ["ran\n"]
    assert b._updater.ran == ["x"]

    assert list(b.full_upgrade()) == ["full\n"]
    assert b._updater.full is True


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class FakeBackend(Backend):
    def __init__(self, name, sources, packages=None, system=False, available=True,
                 confirm=False):
        self.name = name
        self.sources = tuple(sources)
        self.has_system_layer = system
        self._packages = packages or []
        self._available = available
        self.updated = None
        self.full_ran = False

    def is_available(self):
        return self._available

    def scan(self):
        return list(self._packages)

    def update(self, names):
        self.updated = list(names)
        yield f"{self.name}: {' '.join(names)}\n"

    def full_upgrade(self):
        self.full_ran = True
        yield f"{self.name}: full\n"


def _registry_with(backends):
    """A registry whose backend list is swapped for the given fakes."""
    r = BackendRegistry()          # constructor auto-detects real host backends…
    r.backends = list(backends)    # …which we replace with controlled fakes.
    return r


def test_registry_only_includes_available_backends(monkeypatch):
    class Avail(FakeBackend):
        def __init__(self, confirm=False):
            super().__init__("avail", ("official",), available=True)

    class Unavail(FakeBackend):
        def __init__(self, confirm=False):
            super().__init__("unavail", ("AUR",), available=False)

    monkeypatch.setattr(reg, "BACKEND_CLASSES", [Avail, Unavail])
    r = BackendRegistry()
    assert [b.name for b in r.backends] == ["avail"]


def test_registry_scan_aggregates_and_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(reg, "CACHE_FILE", tmp_path / "pending.json")
    official = FakeBackend("pacman", ("official",), packages=[_pkg("firefox")])
    flat = FakeBackend("flatpak", ("Flatpak",),
                       packages=[_pkg("org.gimp.GIMP", "Flatpak")])
    r = _registry_with([official, flat])

    found = r.scan(force=True)
    assert {p.name for p in found} == {"firefox", "org.gimp.GIMP"}
    assert (tmp_path / "pending.json").exists()


def test_registry_scan_returns_cache_when_fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(reg, "CACHE_FILE", tmp_path / "pending.json")
    backend = FakeBackend("pacman", ("official",), packages=[_pkg("firefox")])
    r = _registry_with([backend])

    first = r.scan(force=True)                 # writes cache
    backend._packages = [_pkg("chromium")]     # backend now reports something new
    cached = r.scan()                          # non-force → must read the cache
    assert [p.name for p in cached] == [p.name for p in first] == ["firefox"]

    fresh = r.scan(force=True)                  # force → re-scans
    assert [p.name for p in fresh] == ["chromium"]


def test_registry_backend_for_routes_by_source():
    pac_b = FakeBackend("pacman", ("official", "AUR"))
    flat_b = FakeBackend("flatpak", ("Flatpak",))
    r = _registry_with([pac_b, flat_b])
    assert r.backend_for(_pkg("firefox", "AUR")) is pac_b
    assert r.backend_for(_pkg("gimp", "Flatpak")) is flat_b
    assert r.backend_for(_pkg("mystery", "snap")) is None


def test_registry_update_groups_packages_by_backend():
    pac_b = FakeBackend("pacman", ("official", "AUR"))
    flat_b = FakeBackend("flatpak", ("Flatpak",))
    r = _registry_with([pac_b, flat_b])

    out = list(r.update([
        _pkg("a", "official"),
        _pkg("b", "Flatpak"),
        _pkg("c", "AUR"),
    ]))

    assert pac_b.updated == ["a", "c"]   # both pacman-owned names in one call
    assert flat_b.updated == ["b"]
    assert any("a c" in line for line in out)


def test_registry_update_skips_unowned_package():
    pac_b = FakeBackend("pacman", ("official",))
    r = _registry_with([pac_b])
    out = list(r.update([_pkg("mystery", "snap")]))
    assert any("No backend for mystery" in line for line in out)
    assert pac_b.updated is None


def test_registry_full_upgrade_runs_only_system_layer_backends():
    system = FakeBackend("pacman", ("official",), system=True)
    app_only = FakeBackend("flatpak", ("Flatpak",), system=False)
    r = _registry_with([system, app_only])

    out = list(r.full_upgrade())
    assert system.full_ran is True
    assert app_only.full_ran is False
    assert any("pacman: full" in line for line in out)


def test_registry_full_upgrade_reports_when_no_system_backend():
    app_only = FakeBackend("flatpak", ("Flatpak",), system=False)
    r = _registry_with([app_only])
    out = list(r.full_upgrade())
    assert any("No system-layer backend" in line for line in out)


# --------------------------------------------------------------------------- #
# Cross-distro degrade (Phase 3): a non-Arch host with only Flatpak installed
# --------------------------------------------------------------------------- #

def test_flatpak_registered_as_a_known_backend():
    assert FlatpakBackend in reg.BACKEND_CLASSES


def test_registry_degrades_to_flatpak_only_on_non_arch_host(monkeypatch):
    monkeypatch.setattr(reg, "BACKEND_CLASSES", [PacmanBackend, FlatpakBackend])
    monkeypatch.setattr(pac.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        flat.shutil, "which",
        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None,
    )
    r = BackendRegistry()
    assert [b.name for b in r.backends] == ["flatpak"]
