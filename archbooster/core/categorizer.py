"""
Assigns a priority to each package, which also defines the two update layers:

  critical  → the SYSTEM layer: kernel, firmware, display drivers, core libs.
  normal    → the APP layer: user-facing applications.
  optional  → the APP layer: fonts, themes, icon packs, minor utilities.

ArchBooster's selective (cherry-pick) update flow only ever touches the APP
layer. System-layer packages are never cherry-picked — updating only a subset
of the system is a "partial upgrade", which is unsupported on a rolling release
and can break the install. The system layer may only be updated via a full
`pacman -Syu`. Use `is_system()` to test which layer a package belongs to.
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


def classify(
    name: str,
    extra_critical: list[str] | None = None,
    extra_optional: list[str] | None = None,
) -> str:
    """Return "critical" | "normal" | "optional" for a package name.

    `extra_critical` / `extra_optional` are user-configured name prefixes from
    config.toml that extend the built-in lists.
    """
    nl = name.lower()
    critical = CRITICAL_PATTERNS + [p.lower() for p in (extra_critical or [])]
    optional = OPTIONAL_PATTERNS + [p.lower() for p in (extra_optional or [])]
    if any(nl == p or nl.startswith(p) for p in critical):
        return "critical"
    if any(nl.startswith(p) or p in nl for p in optional):
        return "optional"
    return "normal"


def is_system(name: str, extra_critical: list[str] | None = None) -> bool:
    """True if `name` is a SYSTEM-layer package that must never be cherry-picked.

    This is the guardrail: the selective updater and the dashboard both consult
    it so a partial upgrade of the system/drivers can't happen by accident.
    """
    return classify(name, extra_critical=extra_critical) == "critical"


def categorize(
    packages: list[Package],
    extra_critical: list[str] | None = None,
    extra_optional: list[str] | None = None,
) -> list[Package]:
    for pkg in packages:
        pkg.priority = classify(pkg.name, extra_critical, extra_optional)
    return packages
