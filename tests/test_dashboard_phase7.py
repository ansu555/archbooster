"""Headless TUI tests for the Phase 7 dashboard: type/source filters, the
[U] apps-only preset, selection persistence across filter re-renders, and
the up-to-date inventory section that keeps the list from ever being blank."""
import asyncio

import archbooster.screens.dashboard as dash
from archbooster.app import ArchBoosterApp
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.scanner import Package


def _pkg(name, source="official", priority="normal", status="update"):
    new = "2" if status == "update" else "1"
    return Package(name=name, current="1", new=new, source=source,
                   priority=priority, status=status)


def _wire(monkeypatch, pending, installed=(), gui=frozenset()):
    monkeypatch.setattr(BackendRegistry, "scan", lambda self, force=False: list(pending))
    monkeypatch.setattr(BackendRegistry, "list_installed", lambda self: list(installed))
    monkeypatch.setattr(dash, "gui_package_names", lambda: gui)


async def _wait_for_rows(pilot, app, selector="PackageRow"):
    for _ in range(20):
        await pilot.pause(0.05)
        if app.screen.query(selector):
            return


def _row_names(app):
    return [r.pkg.name for r in app.screen.query("PackageRow")]


def test_tab_cycles_type_filter(monkeypatch):
    _wire(monkeypatch,
          pending=[_pkg("firefox"), _pkg("ripgrep"), _pkg("linux", priority="critical")],
          gui=frozenset({"firefox"}))

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            assert sorted(_row_names(app)) == ["firefox", "linux", "ripgrep"]
            await pilot.press("tab")            # first present category: apps
            await pilot.pause()
            assert _row_names(app) == ["firefox"]
            await pilot.press("tab")            # cli
            await pilot.pause()
            assert _row_names(app) == ["ripgrep"]
            await pilot.press("tab")            # kernel
            await pilot.pause()
            assert _row_names(app) == ["linux"]
            await pilot.press("tab")            # back to no filter
            await pilot.pause()
            assert sorted(_row_names(app)) == ["firefox", "linux", "ripgrep"]

    asyncio.run(run())


def test_m_cycles_source_filter(monkeypatch):
    _wire(monkeypatch,
          pending=[_pkg("firefox"), _pkg("org.gimp.GIMP", source="Flatpak")])

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            await pilot.press("m")              # first source: official
            await pilot.pause()
            assert _row_names(app) == ["firefox"]
            await pilot.press("m")              # Flatpak
            await pilot.pause()
            assert _row_names(app) == ["org.gimp.GIMP"]
            await pilot.press("m")              # clear
            await pilot.pause()
            assert len(_row_names(app)) == 2

    asyncio.run(run())


def test_u_preset_selects_user_facing_apps_only(monkeypatch):
    _wire(monkeypatch,
          pending=[_pkg("firefox"), _pkg("ripgrep"),
                   _pkg("org.gimp.GIMP", source="Flatpak")],
          gui=frozenset({"firefox"}))

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            # default: the whole safe layer selected
            selection = {r.pkg.name: r.selected for r in app.screen.query("PackageRow")}
            assert all(selection.values())
            await pilot.press("u")
            await pilot.pause()
            selection = {r.pkg.name: r.selected for r in app.screen.query("PackageRow")}
            assert selection == {
                "firefox": True, "org.gimp.GIMP": True, "ripgrep": False,
            }

    asyncio.run(run())


def test_selection_survives_filter_cycling(monkeypatch):
    _wire(monkeypatch,
          pending=[_pkg("firefox"), _pkg("ripgrep")],
          gui=frozenset({"firefox"}))

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            await pilot.press("space")          # deselect the cursor row (firefox)
            await pilot.pause()
            deselected = next(r.pkg.name for r in app.screen.query("PackageRow")
                              if not r.selected)
            # cycle type filter all the way around (apps → cli → clear)
            for _ in range(3):
                await pilot.press("tab")
                await pilot.pause()
            selection = {r.pkg.name: r.selected for r in app.screen.query("PackageRow")}
            assert selection[deselected] is False
            assert sum(1 for v in selection.values() if v) == 1

    asyncio.run(run())


def test_no_updates_still_shows_inventory_not_blank(monkeypatch):
    _wire(monkeypatch, pending=[],
          installed=[_pkg("bash", status="up-to-date"),
                     _pkg("linux", status="up-to-date")])

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app, selector="UpToDateRow")
            rows = list(app.screen.query("UpToDateRow"))
            assert len(rows) == 2
            headers = [str(h.render()) for h in app.screen.query("SourceHeader")]
            assert any("Up to date (2)" in h for h in headers)

    asyncio.run(run())


def test_locked_system_row_stays_locked(monkeypatch):
    _wire(monkeypatch, pending=[_pkg("linux", priority="critical"), _pkg("firefox")])

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            await _wait_for_rows(pilot, app)
            await pilot.press("a")              # select-all must not catch linux
            await pilot.pause()
            locked = next(r for r in app.screen.query("PackageRow")
                          if r.pkg.name == "linux")
            assert locked.selected is False

    asyncio.run(run())
