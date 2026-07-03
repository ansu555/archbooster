"""Shared test fixtures.

Phase 7 made the dashboard (and CLI) fetch the installed-package inventory
and the GUI-app (.desktop) set alongside every scan. The headless TUI tests
monkeypatch `BackendRegistry.scan` only, so without these autouse stubs they
would shell out to the real host's pacman/flatpak on every test — slow and
host-dependent. Tests that exercise the inventory or GUI detection override
these with their own monkeypatches (test-level setattr wins over the
fixture's, since it runs later).
"""
import pytest


@pytest.fixture(autouse=True)
def _hermetic_inventory(monkeypatch):
    import archbooster.core.desktopdb as desktopdb
    import archbooster.screens.dashboard as dashboard
    from archbooster.core.backends.registry import BackendRegistry

    monkeypatch.setattr(BackendRegistry, "list_installed", lambda self: [])
    # dashboard imported the function by name, so both references need the stub
    monkeypatch.setattr(desktopdb, "gui_package_names", lambda: frozenset())
    monkeypatch.setattr(dashboard, "gui_package_names", lambda: frozenset())
