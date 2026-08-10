#!/usr/bin/env python3
"""
ArchBooster — entry point.
Usage:
  archbooster              → launch TUI
  archbooster --daemon     → run background check (called by systemd)
  archbooster --scan       → print pending updates + inventory summary
  archbooster --scan --all → also list every up-to-date package
  archbooster --update     → the one command: update the app layer, hold the
                             system layer (kernel/drivers/firmware/bootloader)
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="archbooster")
    parser.add_argument("--daemon", action="store_true", help="Run background scan (systemd mode)")
    parser.add_argument("--scan",   action="store_true", help="Print pending updates and a summary, then exit")
    parser.add_argument("--all",    action="store_true", dest="list_all",
                        help="With --scan: also list every up-to-date package")
    parser.add_argument("--update", action="store_true",
                        help="Update the app layer now; the system layer is always held back")
    parser.add_argument("--scope",  choices=("safe", "apps"), default=None,
                        help="With --update: 'safe' = everything except the system layer "
                             "(default), 'apps' = user-facing apps only")
    args = parser.parse_args()

    if args.daemon:
        from archbooster.daemon import run_daemon
        run_daemon()
    elif args.scan:
        _cmd_scan(list_all=args.list_all)
    elif args.update:
        _cmd_update(scope=args.scope)
    else:
        from archbooster.app import ArchBoosterApp
        ArchBoosterApp().run()


def _load_state(force: bool = False, use_config_confirm: bool = False):
    """Shared scan+categorize for the CLI commands: (cfg, registry, pending,
    up-to-date inventory). `use_config_confirm` matters only when the caller
    will run updates through the registry (scanning ignores the flag)."""
    from archbooster.core.backends.registry import BackendRegistry
    from archbooster.core.categorizer import categorize
    from archbooster.core.config import load_config
    from archbooster.core.desktopdb import gui_package_names

    cfg      = load_config()
    registry = BackendRegistry(confirm=cfg.confirm if use_config_confirm else False)
    gui      = gui_package_names()
    pending  = [p for p in registry.scan(force=force) if p.name not in cfg.ignored]
    pending  = categorize(pending, extra_critical=cfg.extra_critical,
                          extra_optional=cfg.extra_optional, gui_packages=gui)
    pending_keys = {(p.source, p.name) for p in pending}
    installed = [p for p in registry.list_installed()
                 if p.name not in cfg.ignored
                 and (p.source, p.name) not in pending_keys]
    installed = categorize(installed, extra_critical=cfg.extra_critical,
                           extra_optional=cfg.extra_optional, gui_packages=gui)
    return cfg, registry, pending, installed


def _source_summary(packages) -> str:
    counts: dict[str, int] = {}
    for pkg in packages:
        counts[pkg.source] = counts.get(pkg.source, 0) + 1
    return " · ".join(f"{source} {count}" for source, count in sorted(counts.items()))


def _cmd_scan(list_all: bool = False) -> None:
    """Never blank: pending updates first, then what's healthy — so "no
    updates" reads as a status report, not a broken command."""
    _, _, pending, installed = _load_state()

    for pkg in pending:
        held = "  [system — held]" if pkg.priority == "critical" else ""
        print(f"{pkg.source:8} {pkg.name:40} {pkg.current:20} → {pkg.new:20} "
              f"({pkg.category}){held}")

    if pending:
        system = sum(1 for p in pending if p.priority == "critical")
        apps   = len(pending) - system
        parts  = [f"{apps} app-layer"]
        if system:
            parts.append(f"{system} system (held back by --update; full upgrade to apply)")
        print(f"\n{len(pending)} update(s) pending: {', '.join(parts)}")
        print(f"✓ {len(installed)} package(s) up to date ({_source_summary(installed)})")
    else:
        print(f"✓ All up to date — {len(installed)} package(s) checked "
              f"({_source_summary(installed)})")

    if list_all:
        print()
        for pkg in installed:
            print(f"{pkg.source:8} {pkg.name:40} {pkg.current:20} up to date"
                  f"{'':13}({pkg.category})")

    _print_advisories()


def _print_advisories() -> None:
    """Report missing optional tooling after the scan result, not before it.

    Printed last on purpose: the update list is what the user ran the command
    for, and an advisory that pushes it off-screen is worse than no advisory.
    """
    from archbooster.core.preflight import advisories

    for advisory in advisories():
        print(f"\n! {advisory.tool} not found — {advisory.impact}.")
        print(f"  Install it with: {advisory.fix}")


def _cmd_update(scope: str | None = None) -> None:
    """The one command: update the app layer, always hold the system layer."""
    from archbooster.core.snapshot import SnapshotManager

    cfg, registry, pending, _ = _load_state(force=True, use_config_confirm=True)
    if not pending:
        print("✓ Nothing to update — all packages are up to date.")
        return

    scope = scope or cfg.update_scope
    if scope == "apps":
        selected = [p for p in pending
                    if p.priority != "critical" and p.category == "apps"]
    else:
        selected = [p for p in pending if p.priority != "critical"]
    system_held = [p for p in pending if p.priority == "critical"]

    if not selected:
        print(f"Nothing to update in scope '{scope}'.")
        if system_held:
            print(f"Held back (system layer): {', '.join(p.name for p in system_held)}"
                  " — run a full upgrade to apply these.")
        return

    print(f"Updating {len(selected)} package(s) (scope: {scope}); "
          f"holding back {len(pending) - len(selected)}.")
    snapshot = SnapshotManager(cfg.snapshot_backend) if cfg.snapshot_enabled else None
    for line in registry.update_apps(selected, pending, snapshot=snapshot):
        sys.stdout.write(line if line.endswith("\n") else line + "\n")
        sys.stdout.flush()
    if system_held:
        print(f"\nHeld back (system layer): {', '.join(p.name for p in system_held)}"
              " — run a full upgrade when you're ready.")


if __name__ == "__main__":
    main()
