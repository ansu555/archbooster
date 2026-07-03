"""Headless TUI tests for SnapshotsScreen: the rollback confirmation must
require an explicit 'y' and must never fire from a single keystroke, including
one that would otherwise navigate away (escape/q).

Uses asyncio.run() inside plain sync test functions (matching test_stream.py's
convention) rather than pytest-asyncio, which isn't a project dependency."""
import asyncio

from archbooster.app import ArchBoosterApp
from archbooster.core.snapshot import Snapshot, SnapshotManager
from archbooster.screens.snapshots import SnapshotsScreen


def _with_fake_snapshots(monkeypatch, snapshots=None):
    monkeypatch.setattr(SnapshotManager, "is_available", lambda self: True)
    monkeypatch.setattr(
        SnapshotManager, "list",
        lambda self: snapshots if snapshots is not None else
        [Snapshot(id="7", date="2024", description="test", backend="snapper")],
    )


def test_no_tool_shows_empty_state(monkeypatch):
    monkeypatch.setattr(SnapshotManager, "is_available", lambda self: False)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            screen = SnapshotsScreen()
            app.push_screen(screen)
            await pilot.pause()
            assert screen.query("#empty")

    asyncio.run(run())


def test_r_arms_rollback(monkeypatch):
    _with_fake_snapshots(monkeypatch)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            screen = SnapshotsScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            assert screen._armed is True

    asyncio.run(run())


def test_non_y_key_cancels_armed_rollback(monkeypatch):
    _with_fake_snapshots(monkeypatch)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            screen = SnapshotsScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            assert screen._armed is True
            await pilot.press("x")
            await pilot.pause()
            assert screen._armed is False

    asyncio.run(run())


def test_escape_while_armed_cancels_instead_of_leaving_screen(monkeypatch):
    _with_fake_snapshots(monkeypatch)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            screen = SnapshotsScreen()
            app.push_screen(screen)
            await pilot.pause()
            stack_before = len(app.screen_stack)
            await pilot.press("r")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert screen._armed is False
            assert len(app.screen_stack) == stack_before  # still on the snapshots screen

    asyncio.run(run())


def test_escape_when_not_armed_leaves_the_screen(monkeypatch):
    _with_fake_snapshots(monkeypatch)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            screen = SnapshotsScreen()
            app.push_screen(screen)
            await pilot.pause()
            stack_before = len(app.screen_stack)
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == stack_before - 1

    asyncio.run(run())


def test_confirm_triggers_rollback(monkeypatch):
    _with_fake_snapshots(monkeypatch)
    captured = {}

    def fake_rollback(self, snapshot_id):
        captured["id"] = snapshot_id
        yield "rolled back\n"

    monkeypatch.setattr(SnapshotManager, "rollback", fake_rollback)

    async def run():
        app = ArchBoosterApp()
        async with app.run_test() as pilot:
            screen = SnapshotsScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            assert captured.get("id") == "7"

    asyncio.run(run())
