"""
Shared subprocess-streaming helper used by every backend that shells out to a
package manager (pacman/yay/paru, flatpak, apt, dnf, ...). Each backend still
builds its own command line — this just runs it and yields output line-by-line
so the TUI's progress screen can show it live instead of buffering.
"""
import subprocess
from collections.abc import Iterator

from archbooster.core.sudo_auth import SudoKeepalive

# Sentinels the progress screen matches on to decide success/failure. The exit
# code is the only trustworthy signal: package managers print `error:` lines
# they go on to recover from (a mirror 404 that the next mirror serves fine),
# so scanning the stream for the word would fail runs that actually succeeded.
STATUS_OK = "[archbooster] Update complete.\n"
STATUS_FAIL_PREFIX = "[archbooster] ERROR: exited with code "


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
    # Because of that DEVNULL, a sudo password prompt raised part-way through a
    # long run is fatal — sudo reads EOF and aborts. Updates routinely outlive
    # sudo's 15-minute timestamp (kernel dkms/mkinitcpio hooks alone can take
    # ten), and yay only needs root at the *end*, to `pacman -U` what it built.
    # Keeping the timestamp warm for the life of the process is what stops that
    # late `sudo pacman -U` from failing after all the work is already done.
    with SudoKeepalive():
        for line in process.stdout:
            yield line
        process.wait()

    if process.returncode != 0:
        yield f"{STATUS_FAIL_PREFIX}{process.returncode}\n"
    else:
        yield STATUS_OK
