"""Tests for profile pattern matching (fnmatch-based, config-driven groups
used by the dashboard's profile filter and the daemon's auto-update)."""
from archbooster.core.profiles import filter_by_profile, matches_profile
from archbooster.core.scanner import Package


def _pkg(name: str) -> Package:
    return Package(name=name, current="1", new="2", source="official", priority="normal")


def test_exact_name_match():
    assert matches_profile("firefox", ["firefox"]) is True
    assert matches_profile("firefox-esr", ["firefox"]) is False


def test_wildcard_substring_match():
    assert matches_profile("google-chrome-stable", ["*chrome*"]) is True
    assert matches_profile("firefox", ["*chrome*"]) is False


def test_wildcard_prefix_match():
    assert matches_profile("cursor-bin", ["cursor*"]) is True
    assert matches_profile("bincursor", ["cursor*"]) is False


def test_match_is_case_insensitive():
    assert matches_profile("Firefox", ["firefox"]) is True
    assert matches_profile("firefox", ["FIREFOX"]) is True


def test_matches_any_pattern_in_list():
    patterns = ["firefox", "chromium", "*chrome*"]
    assert matches_profile("chromium", patterns) is True
    assert matches_profile("vlc", patterns) is False


def test_empty_patterns_never_match():
    assert matches_profile("firefox", []) is False


def test_filter_by_profile_keeps_only_matching_packages():
    packages = [_pkg("firefox"), _pkg("vlc"), _pkg("chromium")]
    filtered = filter_by_profile(packages, ["firefox", "chromium"])
    assert [p.name for p in filtered] == ["firefox", "chromium"]


def test_filter_by_profile_empty_result():
    packages = [_pkg("vlc"), _pkg("gimp")]
    assert filter_by_profile(packages, ["firefox"]) == []
