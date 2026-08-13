"""Tests for the package categorizer (priority + the two update-layer guardrails)."""
from archbooster.core.categorizer import (
    APT_ALWAYS_UPGRADE_PATTERNS,
    APT_CRITICAL_PATTERNS,
    DNF_ALWAYS_UPGRADE_PATTERNS,
    DNF_CRITICAL_PATTERNS,
    Package,
    categorize,
    classify,
    is_system,
    never_cherry_pick,
    rides_along,
)


def test_critical_exact_and_prefix():
    assert classify("linux") == "critical"
    assert classify("linux-zen") == "critical"          # startswith "linux"
    assert classify("linux-firmware") == "critical"
    assert classify("nvidia") == "critical"


def test_core_libraries_are_not_in_the_hold_layer():
    # The whole point of the critical/core split: these are load-bearing, so
    # they may never be cherry-picked — but they may never be *held* either,
    # because everything on the box links against them. Classifying them
    # "critical" is what puts them into `--ignore` and produces exactly the
    # partial upgrade this tool exists to avoid.
    for name in ("glibc", "openssl", "systemd", "systemd-libs",
                 "sudo", "networkmanager", "dbus", "wayland"):
        assert classify(name) == "core", name
        assert is_system(name) is False, name
        assert rides_along(name) is True, name
        assert never_cherry_pick(name) is True, name


def test_hold_layer_wins_over_ride_along_prefix():
    # "systemd-boot" sits under the "systemd" ride-along prefix but is a
    # bootloader, and "xorg-server" sits under "xorg" but shares a driver ABI
    # with the held video drivers. The more specific hold entry must win.
    assert classify("systemd-boot") == "critical"
    assert classify("xorg-server") == "critical"
    assert is_system("systemd-boot") is True
    assert is_system("xorg-server") is True
    # ...while the generic siblings still ride along.
    assert classify("systemd-libs") == "core"
    assert classify("xorg-xrandr") == "core"


def test_app_layer_is_neither():
    for name in ("firefox", "google-chrome", "ttf-dejavu"):
        assert is_system(name) is False, name
        assert rides_along(name) is False, name
        assert never_cherry_pick(name) is False, name


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

def test_apt_base_patterns_classify_debian_names():
    assert classify("linux-image-generic", base_critical=APT_CRITICAL_PATTERNS) == "critical"
    assert classify("firefox", base_critical=APT_CRITICAL_PATTERNS) == "normal"
    # libc6 is Debian's glibc: ride-along, not hold.
    assert classify("libc6", base_critical=APT_CRITICAL_PATTERNS,
                    base_core=APT_ALWAYS_UPGRADE_PATTERNS) == "core"


def test_dnf_base_patterns_classify_fedora_names():
    assert classify("kernel-core", base_critical=DNF_CRITICAL_PATTERNS) == "critical"
    assert classify("firefox", base_critical=DNF_CRITICAL_PATTERNS) == "normal"
    assert classify("glibc", base_critical=DNF_CRITICAL_PATTERNS,
                    base_core=DNF_ALWAYS_UPGRADE_PATTERNS) == "core"
    # xorg-x11-server holds (driver ABI); the rest of xorg-x11-* rides along.
    assert classify("xorg-x11-server-Xorg", base_critical=DNF_CRITICAL_PATTERNS,
                    base_core=DNF_ALWAYS_UPGRADE_PATTERNS) == "critical"


def test_is_system_honours_base_critical_override():
    # "xserver-xorg" isn't in the Arch list (which uses "xorg-server"), so it
    # must default to "normal" unless the apt base list is supplied.
    assert is_system("xserver-xorg") is False
    assert is_system("xserver-xorg", base_critical=APT_CRITICAL_PATTERNS) is True


def test_never_cherry_pick_honours_distro_overrides():
    # libc6 must be refused by apt's selective path, via the core list.
    assert never_cherry_pick("libc6", base_critical=APT_CRITICAL_PATTERNS,
                             base_core=APT_ALWAYS_UPGRADE_PATTERNS) is True
    assert never_cherry_pick("firefox", base_critical=APT_CRITICAL_PATTERNS,
                             base_core=APT_ALWAYS_UPGRADE_PATTERNS) is False


def _pkg(name: str, source: str) -> Package:
    return Package(name=name, current="1", new="2", source=source, priority="normal")


def test_categorize_routes_pattern_lists_by_source():
    packages = [
        _pkg("linux", "official"),   # Arch hold layer
        _pkg("libc6", "apt"),        # apt core layer, NOT in the Arch list
        _pkg("kernel-core", "dnf"),  # dnf hold layer, NOT in the Arch list
        _pkg("firefox", "apt"),      # apt normal
    ]
    categorize(packages)
    assert [p.priority for p in packages] == ["critical", "core", "critical", "normal"]


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
