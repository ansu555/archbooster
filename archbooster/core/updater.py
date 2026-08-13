"""
Runs the actual package update via yay / paru / pacman.
Streams stdout/stderr line-by-line so the TUI can show live progress.

Three update paths:

  run_apps(selected, held) — the apps-first path (Phase 7, the default flow):
                        a full `-Syu` with `--ignore=<held>`, pacman's own
                        sanctioned hold mechanism. Selected apps update along
                        with whatever libraries they need; the kernel/driver
                        block is always held; the core ABI libs (glibc,
                        openssl, systemd) are always *un*-held. This replaced
                        the `-S` cherry-pick as the main path because
                        checkupdates syncs a *temporary* DB: `-S` against the
                        real (stale) sync DB could silently no-op.
  run(names)          — legacy selective update. Installs only the named
                        packages (`-S`, no `-y`, so it never syncs the whole
                        system). Both non-app layers are refused here so a
                        partial upgrade can't happen — see
                        `archbooster.core.categorizer.never_cherry_pick`. Still
                        used by the daemon's auto-update.
  run_full_upgrade()  — the correct way to update the SYSTEM layer: a full
                        `-Syu`. Never cherry-picks.

Usage:
    for line in Updater().run(["google-chrome", "cursor-bin"]):
        print(line)
    for line in Updater().run_full_upgrade():
        print(line)
"""
import shutil
from collections.abc import Iterator

from archbooster.core.categorizer import is_system, never_cherry_pick, rides_along
from archbooster.core.procutil import stream_subprocess

# Always passed to `--ignore` on the apps-first path, on top of the holds the
# caller computed from the scan. pacman matches --ignore entries as globs, so
# these cover the whole kernel/driver/firmware/bootloader layer by name shape
# rather than by what a given scan happened to find.
#
# The scan-derived hold list already contains every one of these that has a
# pending update, so on a healthy host this changes nothing. It exists for the
# unhealthy one: holds are only as complete as the scan, and a scan that
# under-reports (pacman-contrib missing, checkupdates timing out, a stale
# cache) would otherwise silently degrade `-Syu --ignore=<held>` into a plain
# `-Syu`. The apps-first promise cannot be contingent on a scan succeeding.
SYSTEM_HOLD_GLOBS = [
    "linux", "linux-lts", "linux-zen", "linux-hardened", "linux-rt*",
    "linux-headers", "linux-*-headers",
    "linux-firmware", "linux-firmware-*",
    "nvidia*", "lib32-nvidia*", "opencl-nvidia*",
    "mesa", "lib32-mesa", "vulkan-*", "lib32-vulkan-*",
    "xf86-video-*", "xorg-server*", "amd-ucode", "intel-ucode",
    "grub", "efibootmgr", "refind", "systemd-boot*",
]

# The mirror image of SYSTEM_HOLD_GLOBS — the core ABI layer, which is stripped
# out of `--ignore` no matter who put it there — is *not* duplicated here. It
# lives in `categorizer.ALWAYS_UPGRADE_PATTERNS` and is read through
# `rides_along()` by `_drop_ride_along()` below. Two hand-maintained copies of
# "which packages are load-bearing" drifting apart is what put glibc and openssl
# into this ignore list in the first place; one list, one owner.


class Updater:
    def __init__(self, confirm: bool = False) -> None:
        # confirm=False appends `--noconfirm` (the package manager runs
        # non-interactively — the user's selection in the TUI is the
        # confirmation). confirm=True surfaces pacman/yay's own prompts.
        self.confirm = confirm

    def run(self, package_names: list[str]) -> Iterator[str]:
        """Yield lines of output as a selective (app-layer) update runs.

        Both non-app layers are filtered out and reported, so this path can
        never trigger a partial upgrade: not of the kernel/driver block, and
        not of the core libs either — `-S glibc` against the current sync DB is
        just as much a partial upgrade as `-S linux` is.
        """
        if not package_names:
            return

        blocked = [n for n in package_names if never_cherry_pick(n)]
        allowed = [n for n in package_names if not never_cherry_pick(n)]

        if blocked:
            yield (
                "[archbooster] Skipping system packages (use Full system "
                f"upgrade instead): {', '.join(blocked)}\n"
            )
        if not allowed:
            yield "[archbooster] Nothing to update — only system packages were selected.\n"
            return

        cmd = self._build_command(allowed)
        yield from self._stream(cmd)

    def run_apps(self, selected: list[str], held: list[str]) -> Iterator[str]:
        """Yield output while updating `selected` via `-Syu --ignore=<held>`.

        `held` must contain every other pending update (the caller — the
        registry — computes it from the scan), so the sync only advances the
        packages the user chose plus their dependencies. Two corrections are
        applied to the caller's split, in both directions: any hold-layer
        package in `selected` is forced into the hold list, and any core ABI
        package in `held` is forced out of it (see `_build_apps_command`). The
        apps-first promise is that this path never touches kernel/drivers/
        firmware/bootloader and never pins glibc/openssl/systemd underneath an
        upgrade, no matter what the caller passes.
        """
        if not selected:
            yield "[archbooster] Nothing selected to update.\n"
            return

        blocked = [n for n in selected if is_system(n)]
        allowed = [n for n in selected if not is_system(n)]
        # dict.fromkeys: dedupe while keeping a stable order for the command line
        held = list(dict.fromkeys(list(held) + blocked))
        # Report the list that actually reaches `--ignore`, not the one the
        # caller proposed — otherwise this line claims to be holding glibc back
        # while the command it prefaces is (correctly) upgrading it.
        effective_held = self._drop_ride_along(held)
        riding = [n for n in held if n not in effective_held]

        if blocked:
            yield (
                "[archbooster] System packages stay held (use Full system "
                f"upgrade to update them): {', '.join(blocked)}\n"
            )
        if not allowed:
            yield "[archbooster] Nothing to update — only system packages were selected.\n"
            return
        if riding:
            yield (
                "[archbooster] Core libraries upgrade with your apps (holding "
                f"them back would be the partial upgrade): {', '.join(riding)}\n"
            )
        if effective_held:
            yield f"[archbooster] Holding back: {', '.join(effective_held)}\n"

        yield from self._stream(self._build_apps_command(held))

    def run_full_upgrade(self) -> Iterator[str]:
        """Yield lines of output as a full system upgrade (`-Syu`) runs."""
        cmd = self._build_full_upgrade_command()
        yield from self._stream(cmd)

    # ------------------------------------------------------------------ #

    def _stream(self, cmd: list[str]) -> Iterator[str]:
        yield from stream_subprocess(cmd)

    def _noconfirm(self) -> list[str]:
        # Only skip the package manager's own prompts when confirm is off.
        return [] if self.confirm else ["--noconfirm"]

    def _build_command(self, names: list[str]) -> list[str]:
        # `-S` without `-y`: install the named packages against the current
        # database state, without a full system sync.
        for helper in ("yay", "paru"):
            if shutil.which(helper):
                return [helper, "-S", "--needed"] + self._noconfirm() + names
        if shutil.which("pacman"):
            return ["sudo", "pacman", "-S", "--needed"] + self._noconfirm() + names
        raise RuntimeError("No package manager found (yay, paru, or pacman)")

    @staticmethod
    def _drop_ride_along(held: list[str]) -> list[str]:
        """Strip the core ABI layer out of a caller-supplied hold list.

        Runs *before* SYSTEM_HOLD_GLOBS is appended, so a hold-layer glob that
        sits under a ride-along prefix ("systemd-boot*" under "systemd") is
        never at risk of being dropped. `is_system` is checked first for the
        same reason on the caller's own entries.
        """
        return [n for n in held if is_system(n) or not rides_along(n)]

    def _build_apps_command(self, held: list[str]) -> list[str]:
        # A real `-Syu` (fresh databases, coherent dependency solve) with the
        # hold list riding on `--ignore`. Two unconditional corrections are
        # applied to whatever the caller computed:
        #   * the system-layer globs are always appended, so an empty `held`
        #     means "nothing else was deselected" — never "upgrade the kernel".
        #   * the core ABI libs are always removed, so a hold list built by
        #     subtraction can't quietly pin glibc/openssl under the rest of the
        #     upgrade.
        holds = list(dict.fromkeys(self._drop_ride_along(held) + SYSTEM_HOLD_GLOBS))
        ignore = [f"--ignore={','.join(holds)}"]
        for helper in ("yay", "paru"):
            if shutil.which(helper):
                return [helper, "-Syu", *ignore] + self._noconfirm()
        if shutil.which("pacman"):
            return ["sudo", "pacman", "-Syu", *ignore] + self._noconfirm()
        raise RuntimeError("No package manager found (yay, paru, or pacman)")

    def _build_full_upgrade_command(self) -> list[str]:
        # `-Syu`: refresh databases and upgrade everything — the only supported
        # way to update system-layer packages on a rolling release.
        for helper in ("yay", "paru"):
            if shutil.which(helper):
                return [helper, "-Syu"] + self._noconfirm()
        if shutil.which("pacman"):
            return ["sudo", "pacman", "-Syu"] + self._noconfirm()
        raise RuntimeError("No package manager found (yay, paru, or pacman)")
