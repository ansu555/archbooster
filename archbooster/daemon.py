"""
Background daemon — called by systemd timer.
Runs a scan, caches results, fires a desktop notification, and — only if
[automation] auto_update is explicitly enabled — non-interactively updates
whatever the configured profile matches.
"""
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.categorizer import categorize
from archbooster.core.config import Config, load_config
from archbooster.core.history import History
from archbooster.core.notify import notify_send
from archbooster.core.profiles import filter_by_profile
from archbooster.core.scanner import Package


def run_daemon() -> None:
    cfg      = load_config()
    registry = BackendRegistry(confirm=False)
    packages = registry.scan(force=True)
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

    auto_updated = _run_auto_update(cfg, registry, packages)

    summary = f"{total} app update{'s' if total != 1 else ''} available"
    body_parts = [f"{len(critical)} critical" if critical else "None critical"]
    if auto_updated:
        body_parts.append(f"auto-updated: {', '.join(p.name for p in auto_updated)}")
    if cfg.notify:
        notify_send(summary, "; ".join(body_parts))

    print(f"[archbooster daemon] {total} update(s) available "
          f"({len(critical)} critical). Cache written.")
    if auto_updated:
        print(f"[archbooster daemon] Auto-updated: {', '.join(p.name for p in auto_updated)}")


def _run_auto_update(cfg: Config, registry: BackendRegistry, packages: list[Package]) -> list[Package]:
    """Non-interactively update packages matching [automation].auto_update_profile.

    Both non-app layers are hard-excluded here regardless of what the profile's
    patterns match — this path runs unattended and cherry-picks by name, so
    neither the kernel block nor the core ABI libs may enter it. Same guardrail
    as the selective updater, enforced a second time.
    Returns the packages actually updated (empty if disabled, unconfigured, no
    match, or the update failed).
    """
    if not cfg.auto_update or not cfg.auto_update_profile:
        return []
    patterns = cfg.profiles.get(cfg.auto_update_profile)
    if not patterns:
        return []
    candidates = [p for p in filter_by_profile(packages, patterns)
                  if p.priority not in ("critical", "core")]
    if not candidates:
        return []

    success = True
    for line in registry.update(candidates):
        print(f"[archbooster daemon] {line.rstrip()}")
        low = line.lower()
        if "error:" in low or line.startswith("error"):
            success = False

    history = History()
    for pkg in candidates:
        history.record(
            package=pkg.name, old_ver=pkg.current, new_ver=pkg.new,
            status="success" if success else "failed",
        )
    return candidates if success else []
