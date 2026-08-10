"""Tests for parsing `checkupdates` / `yay -Qu` output lines."""
from archbooster.core.scanner import Scanner, Package


def test_parse_full_line():
    pkg = Scanner()._parse_line("firefox 1.0-1 -> 2.0-1", "official")
    assert pkg == Package(
        name="firefox", current="1.0-1", new="2.0-1",
        source="official", priority="normal",
    )


def test_parse_aur_source():
    pkg = Scanner()._parse_line("brave-bin 1.2-1 -> 1.3-1", "AUR")
    assert pkg.name == "brave-bin"
    assert pkg.new == "1.3-1"
    assert pkg.source == "AUR"


def test_parse_short_line_uses_placeholders():
    # Malformed / truncated line must not raise.
    pkg = Scanner()._parse_line("weirdpkg", "official")
    assert pkg.name == "weirdpkg"
    assert pkg.current == "?"
    assert pkg.new == "?"


# ---- official-scan fallback ------------------------------------------- #
# Without pacman-contrib, `_scan_official` used to return []. That is not a
# cosmetic gap: the apps-first update builds its `--ignore` hold list from the
# scan, so an empty official scan silently turned `-Syu --ignore=<held>` into
# a bare `-Syu` — a full system upgrade, kernel included.

def _no_checkupdates(monkeypatch, helper="yay"):
    import archbooster.core.scanner as sc
    monkeypatch.setattr(
        sc.shutil, "which",
        lambda name: f"/usr/bin/{name}" if name == helper else None,
    )


def test_official_scan_falls_back_to_the_aur_helper(monkeypatch):
    import archbooster.core.scanner as sc
    _no_checkupdates(monkeypatch)
    captured = {}

    class _Result:
        stdout = "linux 7.1.5-1 -> 7.1.6-1\nmesa 26.1.4-1 -> 26.1.5-1\n"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)

    pkgs = Scanner()._scan_official()

    assert captured["cmd"] == ["yay", "-Qu", "--repo"]
    assert [p.name for p in pkgs] == ["linux", "mesa"]
    assert all(p.source == "official" for p in pkgs)


def test_official_scan_prefers_checkupdates_when_present(monkeypatch):
    import archbooster.core.scanner as sc
    monkeypatch.setattr(sc.shutil, "which", lambda name: f"/usr/bin/{name}")
    captured = {}

    class _Result:
        stdout = "firefox 1-1 -> 2-1\n"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)

    assert [p.name for p in Scanner()._scan_official()] == ["firefox"]
    assert captured["cmd"] == ["checkupdates"]


def test_official_scan_is_empty_without_any_tool(monkeypatch):
    import archbooster.core.scanner as sc
    monkeypatch.setattr(sc.shutil, "which", lambda name: None)
    assert Scanner()._scan_official() == []
