"""
Background daemon — called by systemd timer.
Runs a scan, caches results, and fires a desktop notification.
"""
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.categorizer import categorize
from archbooster.core.config import load_config
from archbooster.core.notify import notify_send


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

    summary = f"{total} app update{'s' if total != 1 else ''} available"
    body    = f"{len(critical)} critical" if critical else "None critical"
    if cfg.notify:
        notify_send(summary, body)

    print(f"[archbooster daemon] {total} update(s) available "
          f"({len(critical)} critical). Cache written.")
