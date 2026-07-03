"""Headless TUI tests for the dashboard's [P] profile-cycling keybinding."""
import asyncio

from archbooster.app import ArchBoosterApp
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.scanner import Package
import archbooster.core.config as cfgmod


def _pkgs():
    return [
        Package(name="firefox", current="1", new="2", source="official", priority="normal"),
        Package(name="vlc", current="1", new="2", source="official", priority="normal"),
        Package(name="chromium", current="1", new="2", source="official", priority="normal"),
    ]


def _with_profile(monkeypatch, profiles):
    orig_load = cfgmod.load_config

    def fake_load():
        cfg = orig_load()
        cfg.profiles = profiles
        return cfg

    monkeypatch.setattr(cfgmod, "load_config", fake_load)
    monkeypatch.setattr(BackendRegistry, "scan", lambda self, force=False: _pkgs())


async def _wait_for_rows(pilot, app):
    for _ in range(20):
        await pilot.pause(0.05)
        if app.screen.query("PackageRow"):
            return


def test_no_profiles_configured_notifies_and_does_nothing(monkeypatch):
    _with_profile(monkeypatch, {})

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            rows = list(app.screen.query("PackageRow"))
            before = [(r.pkg.name, r.selected) for r in rows]
            await pilot.press("p")
            await pilot.pause()
            after = [(r.pkg.name, r.selected) for r in list(app.screen.query("PackageRow"))]
            assert before == after

    asyncio.run(run())


def test_cycle_selects_only_matching_packages(monkeypatch):
    _with_profile(monkeypatch, {"browsers": ["firefox", "*chrom*"]})

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            await pilot.press("p")
            await pilot.pause()
            selection = {r.pkg.name: r.selected for r in app.screen.query("PackageRow")}
            assert selection == {"firefox": True, "chromium": True, "vlc": False}

    asyncio.run(run())


def test_cycle_past_last_profile_clears_filter(monkeypatch):
    _with_profile(monkeypatch, {"browsers": ["firefox", "*chrom*"]})

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            await pilot.press("p")   # apply "browsers"
            await pilot.pause()
            await pilot.press("p")   # wrap back to "no filter"
            await pilot.pause()
            selection = {r.pkg.name: r.selected for r in app.screen.query("PackageRow")}
            assert all(selection.values())

    asyncio.run(run())


def test_cycle_never_selects_a_locked_system_row(monkeypatch):
    packages = _pkgs() + [
        Package(name="linux", current="1", new="2", source="official", priority="critical"),
    ]
    monkeypatch.setattr(BackendRegistry, "scan", lambda self, force=False: packages)
    orig_load = cfgmod.load_config

    def fake_load():
        cfg = orig_load()
        cfg.profiles = {"everything": ["*"]}
        return cfg

    monkeypatch.setattr(cfgmod, "load_config", fake_load)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            await pilot.press("p")
            await pilot.pause()
            rows = list(app.screen.query("PackageRow"))
            locked_row = next(r for r in rows if r.pkg.name == "linux")
            assert locked_row.selected is False

    asyncio.run(run())
