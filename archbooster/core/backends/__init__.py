"""
Package-manager backends.

Each backend wraps one package manager (pacman/AUR today, Flatpak next) behind
the common `Backend` interface in `base.py`. The `registry` module auto-detects
which are usable on this host and presents them to the rest of the app as a
single, unified update source — the seam that lets ArchBooster span distros
instead of hardcoding pacman.
"""
