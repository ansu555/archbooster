"""
Desktop notifications via `notify-send` — present on essentially every
Linux desktop (GNOME, KDE, XFCE, etc. all ship a notification daemon that
implements the freedesktop.org spec `notify-send` talks to).

No-ops silently when `notify-send` isn't installed (headless boxes, minimal
window managers) so the daemon never crashes just because there's nowhere
to show a popup.
"""
import shutil
import subprocess


def notify_send(summary: str, body: str = "", urgency: str = "normal") -> bool:
    """Fire a desktop notification. Returns False (no-op) if unsupported."""
    if not shutil.which("notify-send"):
        return False

    subprocess.run(
        ["notify-send", "--urgency", urgency, "--app-name", "ArchBooster", summary, body],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return True
