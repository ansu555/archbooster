"""
Background daemon — called by systemd timer.
Runs a scan, caches results.
(Notification hook lives here, wired up in a later phase.)
"""
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.categorizer import categorize
from archbooster.core.config import load_config


def run_daemon() -> None:
    cfg      = load_config()
    packages = BackendRegistry().scan(force=True)
    packages = [p for p in packages if p.name not in cfg.ignored]
    packages = categorize(
        packages,
        extra_critical=cfg.extra_critical,
        extra_optional=cfg.extra_optional,
    )

    critical = [p for p in packages if p.priority == "critical"]
    total    = len(packages)

    if total == 0:
        return   # nothing to do

    # TODO (phase 5): send desktop notification via notify-send
    print(f"[archbooster daemon] {total} update(s) available "
          f"({len(critical)} critical). Cache written.")
