"""
Assigns a priority to each package:
  critical  → kernel, firmware, display drivers, core system libs
  normal    → user-facing applications
  optional  → fonts, themes, icon packs, minor utilities
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


def categorize(packages: list[Package]) -> list[Package]:
    for pkg in packages:
        pkg.priority = _classify(pkg.name)
    return packages


def _classify(name: str) -> str:
    nl = name.lower()
    if any(nl == p or nl.startswith(p) for p in CRITICAL_PATTERNS):
        return "critical"
    if any(nl.startswith(p) or p in nl for p in OPTIONAL_PATTERNS):
        return "optional"
    return "normal"
