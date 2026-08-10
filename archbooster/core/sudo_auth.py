"""
Pre-flight sudo credential checks and caching for TUI updates.
Uses only stdlib subprocess; no PTY required.

A one-shot pre-flight is not enough on its own: sudo's timestamp expires after
`timestamp_timeout` (15 minutes by default), and an AUR update easily runs
longer than that — a `-Syu` that pulls a kernel spends minutes in dkms and
mkinitcpio hooks before yay ever gets to `sudo pacman -U` for the built
packages. Because updates stream with stdin=DEVNULL (see core.procutil), that
late prompt reads EOF and sudo aborts with "conversation failed", failing a run
that had already done all the work. `SudoKeepalive` refreshes the timestamp in
the background so the credentials outlive the update.
"""
import shutil
import subprocess
import threading

# Comfortably below sudo's default 15-minute timestamp_timeout, and below the
# 5-minute timeout of anyone who has tightened it.
KEEPALIVE_INTERVAL = 60.0


def is_sudo_cached() -> bool:
    """Return True if sudo credentials are already cached (no password needed)."""
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def authenticate(password: str) -> bool:
    """Cache sudo credentials using password on stdin. Returns True on success."""
    if not password:
        return False
    try:
        result = subprocess.run(
            ["sudo", "-S", "-v"],
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def refresh() -> bool:
    """Extend the cached sudo timestamp without prompting.

    `-n` means the refresh can only ever succeed while credentials are still
    cached — it never blocks on a password prompt we have no TTY to answer.
    """
    try:
        result = subprocess.run(
            ["sudo", "-n", "-v"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


class SudoKeepalive:
    """Context manager that keeps sudo credentials alive for a long command.

    Starts a daemon thread that calls `refresh()` every `interval` seconds
    until the block exits. It is a no-op when sudo is missing or credentials
    are not cached to begin with — there is then nothing to keep alive, and a
    keepalive must never be what triggers a password prompt.

    Usage:
        with SudoKeepalive():
            ...run a long privileged command...
    """

    def __init__(self, interval: float = KEEPALIVE_INTERVAL) -> None:
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "SudoKeepalive":
        if shutil.which("sudo") and is_sudo_cached():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            # The worker only ever waits on the event or runs a 5s-capped
            # subprocess, so this join cannot outlast the refresh timeout.
            self._thread.join(timeout=10)
            self._thread = None

    def _loop(self) -> None:
        # wait() returns True once stop() is called, ending the loop promptly
        # instead of sleeping out the remaining interval.
        while not self._stop.wait(self.interval):
            if not refresh():
                # Credentials are gone and we cannot prompt from here; further
                # refreshes would only spawn futile sudo calls.
                return
