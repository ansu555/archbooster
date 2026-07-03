"""
Shared subprocess-streaming helper used by every backend that shells out to a
package manager (pacman/yay/paru, flatpak, apt, dnf, ...). Each backend still
builds its own command line — this just runs it and yields output line-by-line
so the TUI's progress screen can show it live instead of buffering.
"""
import subprocess
from collections.abc import Iterator


def stream_subprocess(cmd: list[str]) -> Iterator[str]:
    """Run `cmd`, yielding stdout+stderr line-by-line, then a final status line."""
    yield f"[archbooster] Running: {' '.join(cmd)}\n"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        # No TTY is attached here, so a prompt would otherwise block forever.
        # DEVNULL makes any prompt read hit EOF instead of hanging.
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
