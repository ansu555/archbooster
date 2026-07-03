"""
Runs the actual package update via yay / paru / pacman.
Streams stdout/stderr line-by-line so the TUI can show live progress.

Two update paths, deliberately separated:

  run(names)          — selective APP-layer update. Installs only the named
                        packages (`-S`, no `-y`, so it never syncs the whole
                        system). System-layer packages are refused here so a
                        partial upgrade of the OS/drivers can't happen — see
                        `archbooster.core.categorizer.is_system`.
  run_full_upgrade()  — the correct way to update the SYSTEM layer: a full
                        `-Syu`. Never cherry-picks.

Usage:
    for line in Updater().run(["google-chrome", "cursor-bin"]):
        print(line)
    for line in Updater().run_full_upgrade():
        print(line)
"""
import shutil
import subprocess
from collections.abc import Iterator

from archbooster.core.categorizer import is_system


class Updater:
    def __init__(self, confirm: bool = False) -> None:
        # confirm=False appends `--noconfirm` (the package manager runs
        # non-interactively — the user's selection in the TUI is the
        # confirmation). confirm=True surfaces pacman/yay's own prompts.
        self.confirm = confirm

    def run(self, package_names: list[str]) -> Iterator[str]:
        """Yield lines of output as a selective (app-layer) update runs.

        Any system-layer package is filtered out and reported, so this path can
        never trigger a partial upgrade of the OS or drivers.
        """
        if not package_names:
            return

        blocked = [n for n in package_names if is_system(n)]
        allowed = [n for n in package_names if not is_system(n)]

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

    def run_full_upgrade(self) -> Iterator[str]:
        """Yield lines of output as a full system upgrade (`-Syu`) runs."""
        cmd = self._build_full_upgrade_command()
        yield from self._stream(cmd)

    # ------------------------------------------------------------------ #

    def _stream(self, cmd: list[str]) -> Iterator[str]:
        yield f"[archbooster] Running: {' '.join(cmd)}\n"

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # No TTY is attached here, so a prompt would otherwise block
            # forever. DEVNULL makes any prompt read hit EOF instead of hanging.
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            yield line
        process.wait()

        if process.returncode != 0:
            yield f"[archbooster] ERROR: exited with code {process.returncode}\n"
        else:
            yield "[archbooster] Update complete.\n"

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

    def _build_full_upgrade_command(self) -> list[str]:
        # `-Syu`: refresh databases and upgrade everything — the only supported
        # way to update system-layer packages on a rolling release.
        for helper in ("yay", "paru"):
            if shutil.which(helper):
                return [helper, "-Syu"] + self._noconfirm()
        if shutil.which("pacman"):
            return ["sudo", "pacman", "-Syu"] + self._noconfirm()
        raise RuntimeError("No package manager found (yay, paru, or pacman)")
