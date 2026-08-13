"""
Assigns a priority to each package, which defines the three update layers:

  critical  → the HOLD layer: kernel, modules, firmware, GPU drivers,
              microcode, bootloader, X server. Never cherry-picked and never
              upgraded on the apps-first path — always `--ignore`d, moves only
              via a full upgrade.
  core      → the RIDE-ALONG layer: glibc, openssl, systemd, sudo, dbus and
              friends. Never cherry-picked either, but never held back: these
              upgrade *with* everything else on the full `-Syu`.
  normal    → the APP layer: user-facing applications.
  optional  → the APP layer: fonts, themes, icon packs, minor utilities.

"Don't cherry-pick this" and "hold this back" are two different ideas, and
conflating them is actively dangerous. Both the kernel block and the core libs
are unsafe to install *alone* (`-S glibc` against a stale sync DB is a partial
upgrade), which is why neither is ever selectable. But they part ways on the
apps-first path:

  * The kernel/driver/firmware/bootloader block is safe to hold. Nothing in
    userspace links against a kernel soname; the block is internally coherent
    and simply lands on the next reboot. `is_system()` marks it.
  * glibc, openssl and systemd are the exact opposite. Every binary on the box
    links against them, so holding them back while upgrading everything that
    links against them is the *dangerous* direction of a partial upgrade — an
    openssl soname bump is the canonical way to end up with a system full of
    binaries pointing at a libcrypto.so that is no longer installed. These must
    ride along. `rides_along()` marks them, and `Updater` strips them from the
    `--ignore` list no matter what a caller asks for.

`never_cherry_pick()` is the union — the guardrail for the `-S`-style paths.

Package *names* mean different things per distro, so each backend has its own
base pattern lists below (Arch/pacman, Debian/apt, Fedora/dnf). `classify()` /
`is_system()` default to the Arch lists for backward compatibility, but accept
`base_critical`/`base_core`/`base_optional` overrides — `categorize()` picks the
right set per `Package.source` automatically via `SOURCE_BASE_PATTERNS`, so a
mixed-source scan (e.g. pacman + apt) classifies each package against its own
distro's list.
"""
from archbooster.core.scanner import Package

# The HOLD layer. Deliberately mirrors `Updater.SYSTEM_HOLD_GLOBS`: kernel,
# modules, firmware, GPU, microcode, bootloader — and nothing else. Every entry
# here is something that can be held back without stranding the rest of the
# system against a soname that no longer exists.
#
# xorg-server is in the block (not with the `xorg-*` client utilities below)
# because it shares a driver ABI with mesa / nvidia-utils / xf86-video-*, which
# are held here too. Upgrading the X server while its video driver stays pinned
# is how X stops starting, so the pair moves together.
CRITICAL_PATTERNS = [
    "linux", "linux-lts", "linux-zen", "linux-hardened",
    "linux-firmware", "mesa", "nvidia", "amdgpu", "intel-ucode", "amd-ucode",
    "xorg-server", "xf86-video",
    "grub", "efibootmgr", "refind", "systemd-boot",
]

# The RIDE-ALONG layer: the ABI providers. Not selectable (you never cherry-pick
# libc), but never held either — they upgrade with everything else or the
# upgrade isn't coherent. Checked *after* CRITICAL_PATTERNS, so "systemd-boot"
# lands in the hold block above while "systemd" and "systemd-libs" land here.
ALWAYS_UPGRADE_PATTERNS = [
    "glibc", "gcc-libs", "openssl", "systemd", "dbus", "pam",
    "sudo", "networkmanager", "wayland", "xorg",
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
    "mesa", "xserver-xorg",
    "nvidia-driver", "nvidia-dkms", "nvidia-kernel", "amdgpu",
    "grub-pc", "grub-efi", "grub-common",
]

APT_ALWAYS_UPGRADE_PATTERNS = [
    "libc6", "libgcc", "libssl", "openssl", "systemd", "dbus", "libpam",
    "sudo", "network-manager", "libwayland", "xorg",
]

APT_OPTIONAL_PATTERNS = [
    "fonts-", "ttf-", "theme-", "-theme", "-icon-theme", "papirus", "breeze",
    "adwaita", "gtk-theme", "cursor-theme",
]

# Fedora/RHEL (dnf) — kernel/system package names again differ from Arch.
DNF_CRITICAL_PATTERNS = [
    "kernel", "kernel-core", "kernel-modules", "kernel-devel",
    "linux-firmware", "mesa", "xorg-x11-server",
    "nvidia-driver", "akmod-nvidia", "kmod-nvidia", "amdgpu",
    "grub2", "shim", "microcode_ctl",
]

DNF_ALWAYS_UPGRADE_PATTERNS = [
    "glibc", "libgcc", "openssl", "systemd", "dbus", "pam",
    "sudo", "networkmanager", "wayland", "xorg-x11-",
]

DNF_OPTIONAL_PATTERNS = [
    "fonts-", "-fonts", "papirus", "breeze", "adwaita",
    "gtk-theme", "icon-theme", "cursor-theme",
]

# categorize() picks the right base pattern pair for each package by its
# Package.source tag. Sources not listed here (a future backend) fall back to
# the Arch lists, same as classify()'s own defaults.
#
# Flatpak/Snap/Homebrew have no system layer at all (has_system_layer=False on
# their Backend), so nothing from them should ever classify as "critical" —
# they get an empty critical list rather than falling back to Arch's. This
# matters for flat package-name backends in particular: a Homebrew formula is
# commonly named e.g. "openssl", which collides with an Arch CRITICAL_PATTERNS
# entry and would otherwise get wrongly flagged critical.
SOURCE_BASE_PATTERNS: dict[str, tuple[list[str], list[str], list[str]]] = {
    "official": (CRITICAL_PATTERNS, ALWAYS_UPGRADE_PATTERNS, OPTIONAL_PATTERNS),
    "AUR":      (CRITICAL_PATTERNS, ALWAYS_UPGRADE_PATTERNS, OPTIONAL_PATTERNS),
    "apt":      (APT_CRITICAL_PATTERNS, APT_ALWAYS_UPGRADE_PATTERNS, APT_OPTIONAL_PATTERNS),
    "dnf":      (DNF_CRITICAL_PATTERNS, DNF_ALWAYS_UPGRADE_PATTERNS, DNF_OPTIONAL_PATTERNS),
    "Flatpak":  ([], [], OPTIONAL_PATTERNS),
    "snap":     ([], [], OPTIONAL_PATTERNS),
    "brew":     ([], [], OPTIONAL_PATTERNS),
}


# ---------------------------------------------------------------------------
# Display taxonomy (Package.category) — user vocabulary for filtering: nobody
# thinks "critical", they think "drivers". Purely presentational; the
# critical/normal/optional priority above remains the only safety input.
# Pattern lists are generic across distros on purpose (apt's "linux-image-*"
# and dnf's "kernel-core" both land in "kernel" via the same prefixes).
# ---------------------------------------------------------------------------

# Checked BEFORE kernel: "linux-firmware" must land in drivers, not kernel.
DRIVER_CATEGORY_PATTERNS = [
    "nvidia", "mesa", "amdgpu", "intel-ucode", "amd-ucode",
    "linux-firmware", "xf86-video", "vulkan-", "broadcom", "sof-firmware",
]

KERNEL_CATEGORY_PATTERNS = [
    "linux", "linux-lts", "linux-zen", "linux-hardened",   # Arch
    "linux-image", "linux-headers", "linux-modules",        # Debian/Ubuntu
    "kernel",                                               # Fedora
]

# Sources whose every package is a user-facing app by definition — no
# .desktop-file lookup needed. (brew is deliberately absent: Homebrew on
# Linux is overwhelmingly CLI formulae, so its packages default to "cli".)
APP_ONLY_SOURCES = {"Flatpak", "snap"}


def display_category(pkg: Package, gui_packages: frozenset[str] | set[str] = frozenset()) -> str:
    """Map a (already priority-classified) package to its display category.

    `gui_packages` is the set of native package names shipping a .desktop
    launcher (see core.desktopdb) — the proxy for "user-facing app".
    """
    nl = pkg.name.lower()
    if pkg.priority == "critical":
        if any(p in nl for p in DRIVER_CATEGORY_PATTERNS):
            return "drivers"
        if any(nl == p or nl.startswith(p) for p in KERNEL_CATEGORY_PATTERNS):
            return "kernel"
        return "system"
    if pkg.priority == "core":
        # Same "system" bucket for filtering purposes — a user looking for
        # glibc looks under system. The held/rides-along distinction is carried
        # by priority, and shown per-row by the dashboard.
        return "system"
    if pkg.priority == "optional":
        return "fonts-themes"
    if pkg.source in APP_ONLY_SOURCES or pkg.name in gui_packages:
        return "apps"
    return "cli"


def classify(
    name: str,
    extra_critical: list[str] | None = None,
    extra_optional: list[str] | None = None,
    base_critical: list[str] = CRITICAL_PATTERNS,
    base_optional: list[str] = OPTIONAL_PATTERNS,
    base_core: list[str] = ALWAYS_UPGRADE_PATTERNS,
) -> str:
    """Return "critical" | "core" | "normal" | "optional" for a package name.

    `extra_critical` / `extra_optional` are user-configured name prefixes from
    config.toml that extend the built-in lists. `base_critical`/`base_core`/
    `base_optional` let a non-Arch backend (apt, dnf) classify against its own
    distro's package names instead of Arch's; they default to the Arch lists.

    Order matters: the hold block is tested before the ride-along block, so a
    more specific hold entry ("systemd-boot", "xorg-server") wins over the
    broader ride-along prefix it sits under ("systemd", "xorg").
    """
    nl = name.lower()
    critical = list(base_critical) + [p.lower() for p in (extra_critical or [])]
    optional = list(base_optional) + [p.lower() for p in (extra_optional or [])]
    if any(nl == p or nl.startswith(p) for p in critical):
        return "critical"
    if any(nl == p or nl.startswith(p) for p in base_core):
        return "core"
    if any(nl.startswith(p) or p in nl for p in optional):
        return "optional"
    return "normal"


def is_system(
    name: str,
    extra_critical: list[str] | None = None,
    base_critical: list[str] = CRITICAL_PATTERNS,
) -> bool:
    """True if `name` is a HOLD-layer package: kernel, modules, firmware, GPU
    driver, microcode, bootloader, X server.

    These are held back (`--ignore`) on the apps-first path and only move via a
    full upgrade. This is deliberately *not* "is it important" — glibc is more
    important than the bootloader and is emphatically not in here, because
    holding glibc back is the dangerous move, not the safe one. See
    `rides_along()`.
    """
    return classify(name, extra_critical=extra_critical, base_critical=base_critical) == "critical"


def rides_along(
    name: str,
    base_core: list[str] = ALWAYS_UPGRADE_PATTERNS,
    base_critical: list[str] = CRITICAL_PATTERNS,
) -> bool:
    """True if `name` is a RIDE-ALONG package that must never be held back.

    glibc, openssl, systemd and friends: everything on the box links against
    them, so they have to advance in the same transaction as the packages that
    link against them. `Updater` strips these from `--ignore` unconditionally,
    which is what keeps an under-reporting scan or an over-eager caller from
    turning the apps-first update into an openssl-pinned partial upgrade.
    """
    return classify(name, base_critical=base_critical, base_core=base_core) == "core"


def never_cherry_pick(
    name: str,
    extra_critical: list[str] | None = None,
    base_critical: list[str] = CRITICAL_PATTERNS,
    base_core: list[str] = ALWAYS_UPGRADE_PATTERNS,
) -> bool:
    """True if `name` must never be installed on its own (`-S <name>`).

    The union of the two non-app layers. They're excluded from cherry-picking
    for opposite reasons — the kernel block because it should wait for a full
    upgrade, the core libs because they should never lag one — but the `-S`
    path treats them the same: not alone.
    """
    priority = classify(name, extra_critical=extra_critical,
                        base_critical=base_critical, base_core=base_core)
    return priority in ("critical", "core")


def categorize(
    packages: list[Package],
    extra_critical: list[str] | None = None,
    extra_optional: list[str] | None = None,
    gui_packages: frozenset[str] | set[str] | None = None,
) -> list[Package]:
    """Set each package's safety priority AND display category.

    `gui_packages` (native packages shipping a .desktop launcher) drives the
    apps-vs-cli split; None means "unknown" and native packages fall back to
    "cli" — callers with a real host should pass core.desktopdb's set. Kept as
    an argument rather than looked up here so this module stays subprocess-free
    and hermetically testable.
    """
    gui = gui_packages or frozenset()
    for pkg in packages:
        base_critical, base_core, base_optional = SOURCE_BASE_PATTERNS.get(
            pkg.source, (CRITICAL_PATTERNS, ALWAYS_UPGRADE_PATTERNS, OPTIONAL_PATTERNS)
        )
        pkg.priority = classify(
            pkg.name, extra_critical, extra_optional,
            base_critical=base_critical, base_optional=base_optional,
            base_core=base_core,
        )
        pkg.category = display_category(pkg, gui)
    return packages
