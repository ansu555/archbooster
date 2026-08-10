"""Tests for the missing-optional-tooling advisories.

Background: a host without pacman-contrib has no `checkupdates`, which used to
make the official scan return an empty list — and because the apps-first update
builds its `--ignore` hold list from that scan, an empty official scan silently
degraded `-Syu --ignore=<held>` into a bare `-Syu`. The code no longer depends
on the tool being present; these advisories exist so the user still learns they
are on the fallback path.
"""
import archbooster.core.preflight as preflight
from archbooster.core.preflight import advisories


def _tools(monkeypatch, *present: str):
    monkeypatch.setattr(
        preflight.shutil, "which",
        lambda name: f"/usr/bin/{name}" if name in present else None,
    )


def test_advises_pacman_contrib_when_checkupdates_is_missing(monkeypatch):
    _tools(monkeypatch, "pacman", "yay")
    found = advisories()
    assert [a.package for a in found] == ["pacman-contrib"]
    assert found[0].fix == "sudo pacman -S pacman-contrib"


def test_silent_when_checkupdates_is_present(monkeypatch):
    _tools(monkeypatch, "pacman", "checkupdates")
    assert advisories() == []


def test_silent_on_hosts_without_pacman(monkeypatch):
    """A Debian/Fedora/Flatpak-only box has no use for pacman-contrib."""
    _tools(monkeypatch, "flatpak", "apt")
    assert advisories() == []


def test_cli_scan_prints_the_advisory(monkeypatch, capsys):
    import archbooster.main as main

    _tools(monkeypatch, "pacman")
    main._print_advisories()
    out = capsys.readouterr().out
    assert "checkupdates not found" in out
    assert "sudo pacman -S pacman-contrib" in out


def test_cli_scan_prints_nothing_when_healthy(monkeypatch, capsys):
    import archbooster.main as main

    _tools(monkeypatch, "pacman", "checkupdates")
    main._print_advisories()
    assert capsys.readouterr().out == ""
