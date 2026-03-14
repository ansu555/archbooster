"""
Runs the actual package update via yay / paru / pacman.
Streams stdout/stderr line-by-line so the TUI can show live progress.

Usage:
    for line in Updater().run(["google-chrome", "discord"]):
        print(line)
"""
import shutil
import subprocess
from collections.abc import Iterator


class Updater:
    def run(self, package_names: list[str]) -> Iterator[str]:
        """Yield lines of output as the update runs."""
        if not package_names:
            return

        cmd = self._build_command(package_names)
        yield f"[archbooster] Running: {' '.join(cmd)}\n"

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
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

    def _build_command(self, names: list[str]) -> list[str]:
        for helper in ("yay", "paru"):
            if shutil.which(helper):
                return [helper, "-S", "--needed", "--noconfirm"] + names
        if shutil.which("pacman"):
            return ["sudo", "pacman", "-S", "--needed", "--noconfirm"] + names
        raise RuntimeError("No package manager found (yay, paru, or pacman)")
