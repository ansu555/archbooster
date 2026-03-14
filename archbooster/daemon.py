"""
Background daemon — called by systemd timer.
Runs a scan, caches results.
(Notification hook lives here, wired up in a later phase.)
"""
import time
from archbooster.core.scanner import Scanner
from archbooster.core.categorizer import categorize
from archbooster.core.config import load_config


def run_daemon() -> None:
    cfg      = load_config()
    scanner  = Scanner()
    packages = scanner.fetch(force=True)
    packages = categorize(packages)

    critical = [p for p in packages if p.priority == "critical"]
    total    = len(packages)

    if total == 0:
        return   # nothing to do

    # TODO (phase 2): send desktop notification via notify-send
    print(f"[archbooster daemon] {total} update(s) available "
          f"({len(critical)} critical). Cache written.")
