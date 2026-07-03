"""Tests for the Phase 7 apps-first update path: `-Syu --ignore=<held>`
command building, the system-layer guard inside Updater.run_apps, and the
registry's per-backend hold computation."""
from collections.abc import Iterator

import archbooster.core.updater as up
from archbooster.core.backends.base import Backend
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.scanner import Package
from archbooster.core.updater import Updater


def _only_yay(monkeypatch):
    monkeypatch.setattr(
        up.shutil, "which",
        lambda name: "/usr/bin/yay" if name == "yay" else None,
    )


def _only_pacman(monkeypatch):
    monkeypatch.setattr(
        up.shutil, "which",
        lambda name: "/usr/bin/pacman" if name == "pacman" else None,
    )


def _pkg(name, source="official", priority="normal"):
    return Package(name=name, current="1", new="2", source=source, priority=priority)


# ---- command building ------------------------------------------------- #

def test_apps_command_carries_holds_as_ignore(monkeypatch):
    _only_yay(monkeypatch)
    cmd = Updater(confirm=False)._build_apps_command(["linux", "nvidia"])
    assert cmd == ["yay", "-Syu", "--ignore=linux,nvidia", "--noconfirm"]


def test_apps_command_without_holds_is_plain_syu(monkeypatch):
    _only_yay(monkeypatch)
    assert Updater(confirm=True)._build_apps_command([]) == ["yay", "-Syu"]


def test_apps_command_pacman_fallback_uses_sudo(monkeypatch):
    _only_pacman(monkeypatch)
    cmd = Updater(confirm=False)._build_apps_command(["linux"])
    assert cmd == ["sudo", "pacman", "-Syu", "--ignore=linux", "--noconfirm"]


# ---- run_apps guardrail ------------------------------------------------ #

def test_run_apps_forces_selected_system_packages_into_holds(monkeypatch):
    u = Updater(confirm=False)
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(u, "_stream", fake_stream)
    _only_yay(monkeypatch)

    out = list(u.run_apps(["linux", "firefox"], held=["mesa"]))

    assert any("System packages stay held" in line for line in out)
    ignore_flag = next(arg for arg in captured["cmd"] if arg.startswith("--ignore="))
    held = ignore_flag.removeprefix("--ignore=").split(",")
    assert "linux" in held and "mesa" in held
    assert "firefox" not in held


def test_run_apps_with_only_system_selected_runs_nothing(monkeypatch):
    u = Updater(confirm=False)
    monkeypatch.setattr(u, "_stream", lambda cmd: (_ for _ in ()).throw(
        AssertionError("must not run a command for system-only selection")))
    out = list(u.run_apps(["linux", "nvidia"], held=[]))
    assert any("only system packages were selected" in line for line in out)


def test_run_apps_with_empty_selection_runs_nothing(monkeypatch):
    u = Updater(confirm=False)
    monkeypatch.setattr(u, "_stream", lambda cmd: (_ for _ in ()).throw(
        AssertionError("must not run a command for an empty selection")))
    out = list(u.run_apps([], held=["linux"]))
    assert any("Nothing selected" in line for line in out)


def test_run_apps_dedupes_hold_list(monkeypatch):
    u = Updater(confirm=False)
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(u, "_stream", fake_stream)
    _only_yay(monkeypatch)

    list(u.run_apps(["firefox"], held=["mesa", "mesa", "linux"]))
    ignore_flag = next(arg for arg in captured["cmd"] if arg.startswith("--ignore="))
    held = ignore_flag.removeprefix("--ignore=").split(",")
    assert held == ["mesa", "linux"]


# ---- registry hold computation ----------------------------------------- #

class _FakeSystemBackend(Backend):
    name = "fakesys"
    sources = ("official",)
    has_system_layer = True

    def __init__(self):
        self.calls = []

    def is_available(self):
        return True

    def scan(self):
        return []

    def update(self, names):
        yield f"legacy:{','.join(names)}\n"

    def update_apps(self, selected, held) -> Iterator[str]:
        self.calls.append((
            [p.name for p in selected], [p.name for p in held],
        ))
        yield "sys-backend ran\n"

    def full_upgrade(self):
        yield "full\n"


class _FakeAppBackend(Backend):
    name = "fakeapp"
    sources = ("Flatpak",)
    has_system_layer = False

    def __init__(self):
        self.updated = []

    def is_available(self):
        return True

    def scan(self):
        return []

    def update(self, names):
        self.updated.append(names)
        yield "app-backend ran\n"

    def full_upgrade(self):
        yield "full\n"


def _registry_with(*backends) -> BackendRegistry:
    registry = BackendRegistry.__new__(BackendRegistry)
    registry.backends = list(backends)
    return registry


def test_registry_update_apps_computes_holds_per_backend():
    sys_b, app_b = _FakeSystemBackend(), _FakeAppBackend()
    registry = _registry_with(sys_b, app_b)

    firefox = _pkg("firefox")
    ripgrep = _pkg("ripgrep")
    linux   = _pkg("linux", priority="critical")
    gimp    = _pkg("org.gimp.GIMP", source="Flatpak")

    pending  = [firefox, ripgrep, linux, gimp]
    selected = [firefox, gimp]

    list(registry.update_apps(selected, pending))

    # pacman-side: selected firefox, held = the rest of ITS pending packages
    assert sys_b.calls == [(["firefox"], ["ripgrep", "linux"])]
    # app-only backend: default update_apps = plain selective update; the
    # flatpak "hold" is simply not being named
    assert app_b.updated == [["org.gimp.GIMP"]]


def test_registry_update_apps_reports_orphan_sources():
    registry = _registry_with(_FakeAppBackend())
    stray = _pkg("mystery", source="dnf")
    out = list(registry.update_apps([stray], [stray]))
    assert any("No backend for mystery" in line for line in out)


def test_registry_update_apps_snapshots_before_system_backend():
    sys_b = _FakeSystemBackend()
    registry = _registry_with(sys_b)

    class FakeSnapshot:
        backend = "snapper"
        def is_available(self):
            return True
        def create(self, desc):
            return "42"

    firefox = _pkg("firefox")
    out = list(registry.update_apps([firefox], [firefox], snapshot=FakeSnapshot()))
    snap_idx = next(i for i, line in enumerate(out) if "Snapshot created: 42" in line)
    run_idx  = next(i for i, line in enumerate(out) if "sys-backend ran" in line)
    assert snap_idx < run_idx


def test_registry_update_apps_no_snapshot_for_app_only_backends():
    app_b = _FakeAppBackend()
    registry = _registry_with(app_b)

    class ExplodingSnapshot:
        backend = "snapper"
        def is_available(self):
            raise AssertionError("snapshot must not be consulted for app-only backends")

    gimp = _pkg("org.gimp.GIMP", source="Flatpak")
    out = list(registry.update_apps([gimp], [gimp], snapshot=ExplodingSnapshot()))
    assert any("app-backend ran" in line for line in out)
