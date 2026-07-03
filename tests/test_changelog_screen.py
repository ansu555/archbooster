"""Headless TUI tests for ChangelogScreen and the dashboard's [C] keybinding
that opens it for the focused row."""
import asyncio

from archbooster.app import ArchBoosterApp
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.scanner import Package
from archbooster.screens.changelog import ChangelogScreen


def _pkg() -> Package:
    return Package(name="firefox", current="1", new="2", source="official", priority="normal")


def test_no_backend_shows_unavailable_message():
    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            app.push_screen(ChangelogScreen(_pkg(), backend=None))
            await pilot.pause(0.2)
            body = app.screen.query_one("#changelog-body")
            text = str(getattr(body, "_renderable", body.render()))
            assert "No backend available" in text

    asyncio.run(run())


def test_backend_with_no_changelog_shows_not_available():
    class NoChangelogBackend:
        def changelog(self, pkg):
            return None

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            app.push_screen(ChangelogScreen(_pkg(), backend=NoChangelogBackend()))
            await pilot.pause(0.2)
            body = app.screen.query_one("#changelog-body")
            text = str(getattr(body, "_renderable", body.render()))
            assert "No changelog available" in text

    asyncio.run(run())


def test_backend_with_changelog_shows_it():
    class DiffBackend:
        def changelog(self, pkg):
            return "-old line\n+new line\n"

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            app.push_screen(ChangelogScreen(_pkg(), backend=DiffBackend()))
            await pilot.pause(0.2)
            body = app.screen.query_one("#changelog-body")
            text = str(getattr(body, "_renderable", body.render()))
            assert "old line" in text and "new line" in text

    asyncio.run(run())


def test_dashboard_c_key_opens_changelog_screen(monkeypatch):
    monkeypatch.setattr(BackendRegistry, "scan", lambda self, force=False: [_pkg()])
    monkeypatch.setattr(BackendRegistry, "backend_for", lambda self, pkg: None)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            for _ in range(20):
                await pilot.pause(0.05)
                if app.screen.query("PackageRow"):
                    break
            await pilot.press("c")
            await pilot.pause(0.2)
            assert isinstance(app.screen, ChangelogScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, ChangelogScreen)

    asyncio.run(run())
