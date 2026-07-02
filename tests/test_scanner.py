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
