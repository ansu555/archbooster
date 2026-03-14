"""
Pre-flight sudo credential checks and caching for TUI updates.
Uses only stdlib subprocess; no PTY required.
"""
import subprocess


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
