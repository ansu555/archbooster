"""
Assigns a priority to each package, which also defines the two update layers:

  critical  → the SYSTEM layer: kernel, firmware, display drivers, core libs.
  normal    → the APP layer: user-facing applications.
  optional  → the APP layer: fonts, themes, icon packs, minor utilities.

ArchBooster's selective (cherry-pick) update flow only ever touches the APP
layer. System-layer packages are never cherry-picked — updating only a subset
of the system is a "partial upgrade", which is unsupported on a rolling release
and can break the install. The system layer may only be updated via a full
`pacman -Syu` (or the equivalent full upgrade on other distros). Use
`is_system()` to test which layer a package belongs to.

Package *names* mean different things per distro, so each backend has its own
base pattern lists below (Arch/pacman, Debian/apt, Fedora/dnf). `classify()` /
`is_system()` default to the Arch lists for backward compatibility, but accept
`base_critical`/`base_optional` overrides — `categorize()` picks the right pair
per `Package.source` automatically via `SOURCE_BASE_PATTERNS`, so a mixed-source
scan (e.g. pacman + apt) classifies each package against its own distro's list.
"""
from archbooster.core.scanner import Package

CRITICAL_PATTERNS = [
    "linux", "linux-lts", "linux-zen", "linux-hardened",
    "linux-firmware", "mesa", "nvidia", "amdgpu", "intel-ucode",
    "xorg", "wayland", "systemd", "glibc", "openssl", "sudo",
    "grub", "efibootmgr", "networkmanager",
]

OPTIONAL_PATTERNS = [
    "ttf-", "otf-", "noto-fonts", "font-",
    "papirus", "breeze", "adwaita", "gtk-theme",
    "icon-theme", "cursor-theme", "kvantum",
]

# Debian/Ubuntu (apt) — package-name conventions differ from Arch (e.g.
# "linux-image-*" instead of "linux", "libc6" instead of "glibc").
APT_CRITICAL_PATTERNS = [
    "linux-image", "linux-headers", "linux-firmware", "linux-modules",
    "systemd", "libc6", "mesa", "xserver-xorg", "xorg",
    "nvidia-driver", "nvidia-dkms", "nvidia-kernel", "amdgpu",
    "grub-pc", "grub-efi", "grub-common", "network-manager", "dbus",
]

APT_OPTIONAL_PATTERNS = [
    "fonts-", "ttf-", "theme-", "-theme", "-icon-theme", "papirus", "breeze",
    "adwaita", "gtk-theme", "cursor-theme",
]

# Fedora/RHEL (dnf) — kernel/system package names again differ from Arch.
DNF_CRITICAL_PATTERNS = [
    "kernel", "kernel-core", "kernel-modules", "kernel-devel",
    "systemd", "glibc", "mesa", "xorg-x11-server",
    "nvidia-driver", "akmod-nvidia", "kmod-nvidia", "amdgpu",
    "grub2", "networkmanager", "dbus",
]

DNF_OPTIONAL_PATTERNS = [
    "fonts-", "-fonts", "papirus", "breeze", "adwaita",
    "gtk-theme", "icon-theme", "cursor-theme",
]

# categorize() picks the right base pattern pair for each package by its
# Package.source tag. Sources not listed here (a future backend) fall back to
# the Arch lists, same as classify()'s own defaults.
SOURCE_BASE_PATTERNS: dict[str, tuple[list[str], list[str]]] = {
    "official": (CRITICAL_PATTERNS, OPTIONAL_PATTERNS),
    "AUR":      (CRITICAL_PATTERNS, OPTIONAL_PATTERNS),
    "apt":      (APT_CRITICAL_PATTERNS, APT_OPTIONAL_PATTERNS),
    "dnf":      (DNF_CRITICAL_PATTERNS, DNF_OPTIONAL_PATTERNS),
}


def classify(
    name: str,
    extra_critical: list[str] | None = None,
    extra_optional: list[str] | None = None,
    base_critical: list[str] = CRITICAL_PATTERNS,
    base_optional: list[str] = OPTIONAL_PATTERNS,
) -> str:
    """Return "critical" | "normal" | "optional" for a package name.

    `extra_critical` / `extra_optional` are user-configured name prefixes from
    config.toml that extend the built-in lists. `base_critical`/`base_optional`
    let a non-Arch backend (apt, dnf) classify against its own distro's system
    package names instead of Arch's; they default to the Arch lists.
    """
    nl = name.lower()
    critical = list(base_critical) + [p.lower() for p in (extra_critical or [])]
    optional = list(base_optional) + [p.lower() for p in (extra_optional or [])]
    if any(nl == p or nl.startswith(p) for p in critical):
        return "critical"
    if any(nl.startswith(p) or p in nl for p in optional):
        return "optional"
    return "normal"


def is_system(
    name: str,
    extra_critical: list[str] | None = None,
    base_critical: list[str] = CRITICAL_PATTERNS,
) -> bool:
    """True if `name` is a SYSTEM-layer package that must never be cherry-picked.

    This is the guardrail: each backend's selective updater consults it (with
    its own `base_critical` list) so a partial upgrade of the system/drivers
    can't happen by accident, on any distro.
    """
    return classify(name, extra_critical=extra_critical, base_critical=base_critical) == "critical"


def categorize(
    packages: list[Package],
    extra_critical: list[str] | None = None,
    extra_optional: list[str] | None = None,
) -> list[Package]:
    for pkg in packages:
        base_critical, base_optional = SOURCE_BASE_PATTERNS.get(
            pkg.source, (CRITICAL_PATTERNS, OPTIONAL_PATTERNS)
        )
        pkg.priority = classify(
            pkg.name, extra_critical, extra_optional,
            base_critical=base_critical, base_optional=base_optional,
        )
    return packages
