"""Tests for the package categorizer (priority + system-layer guardrail)."""
from archbooster.core.categorizer import (
    APT_CRITICAL_PATTERNS,
    DNF_CRITICAL_PATTERNS,
    Package,
    categorize,
    classify,
    is_system,
)


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


# --------------------------------------------------------------------------- #
# multi-distro base pattern lists (apt/dnf)
# --------------------------------------------------------------------------- #

def test_apt_base_patterns_classify_debian_names_as_critical():
    assert classify("linux-image-generic", base_critical=APT_CRITICAL_PATTERNS) == "critical"
    assert classify("libc6", base_critical=APT_CRITICAL_PATTERNS) == "critical"
    assert classify("firefox", base_critical=APT_CRITICAL_PATTERNS) == "normal"


def test_dnf_base_patterns_classify_fedora_names_as_critical():
    assert classify("kernel-core", base_critical=DNF_CRITICAL_PATTERNS) == "critical"
    assert classify("glibc", base_critical=DNF_CRITICAL_PATTERNS) == "critical"
    assert classify("firefox", base_critical=DNF_CRITICAL_PATTERNS) == "normal"


def test_is_system_honours_base_critical_override():
    # "libc6" isn't in the Arch list (which uses "glibc"), so it must default
    # to "normal" (not critical) unless the apt base list is supplied.
    assert is_system("libc6") is False
    assert is_system("libc6", base_critical=APT_CRITICAL_PATTERNS) is True


def _pkg(name: str, source: str) -> Package:
    return Package(name=name, current="1", new="2", source=source, priority="normal")


def test_categorize_routes_pattern_lists_by_source():
    packages = [
        _pkg("linux", "official"),   # Arch critical
        _pkg("libc6", "apt"),        # apt critical, NOT in the Arch list
        _pkg("kernel-core", "dnf"),  # dnf critical, NOT in the Arch list
        _pkg("firefox", "apt"),      # apt normal
    ]
    categorize(packages)
    assert [p.priority for p in packages] == ["critical", "critical", "critical", "normal"]


def test_categorize_unknown_source_falls_back_to_arch_patterns():
    packages = [_pkg("linux", "some-future-backend")]
    categorize(packages)
    assert packages[0].priority == "critical"


def test_categorize_system_layer_free_sources_never_classify_critical():
    # Flatpak/snap/brew have no system layer at all, so even a name that
    # collides with an Arch CRITICAL_PATTERNS entry (e.g. "openssl" is a very
    # common Homebrew formula) must never come back "critical" for them.
    packages = [
        _pkg("openssl", "brew"),
        _pkg("sudo", "snap"),
        _pkg("systemd", "Flatpak"),
    ]
    categorize(packages)
    assert [p.priority for p in packages] == ["normal", "normal", "normal"]
