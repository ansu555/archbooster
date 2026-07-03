#!/usr/bin/env python3
"""
ArchBooster — entry point.
Usage:
  archbooster          → launch TUI
  archbooster --daemon → run background check (called by systemd)
  archbooster --scan   → print available updates and exit
"""
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(prog="archbooster")
    parser.add_argument("--daemon", action="store_true", help="Run background scan (systemd mode)")
    parser.add_argument("--scan",   action="store_true", help="Print available updates and exit")
    args = parser.parse_args()

    if args.daemon:
        from archbooster.daemon import run_daemon
        run_daemon()
    elif args.scan:
        from archbooster.core.backends.registry import BackendRegistry
        updates = BackendRegistry().scan()
        for pkg in updates:
            print(f"{pkg.source:8} {pkg.name:40} {pkg.current:20} → {pkg.new}")
    else:
        from archbooster.app import ArchBoosterApp
        ArchBoosterApp().run()

if __name__ == "__main__":
    main()
