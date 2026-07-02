"""Tests for the package categorizer (priority + system-layer guardrail)."""
from archbooster.core.categorizer import classify, is_system


def test_critical_exact_and_prefix():
    assert classify("linux") == "critical"
    assert classify("linux-zen") == "critical"          # startswith "linux"
    assert classify("linux-firmware") == "critical"
    assert classify("nvidia") == "critical"
    assert classify("systemd") == "critical"


def test_optional_fonts_and_themes():
    assert classify("ttf-dejavu") == "optional"
    assert classify("papirus-icon-theme") == "optional"
    assert classify("noto-fonts-emoji") == "optional"


def test_normal_is_the_default():
    assert classify("google-chrome") == "normal"
    assert classify("firefox") == "normal"
    assert classify("cursor-bin") == "normal"


def test_extra_lists_extend_builtins():
    assert classify("mycorp-agent", extra_critical=["mycorp"]) == "critical"
    assert classify("acme-cursor", extra_optional=["acme"]) == "optional"


def test_is_system_matches_critical():
    assert is_system("nvidia") is True
    assert is_system("mesa") is True
    assert is_system("firefox") is False
    assert is_system("google-chrome") is False
