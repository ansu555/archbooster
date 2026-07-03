# Roadmap — Phase 6+ (v0.3 and beyond)

v0.2 (Phases 0–5) is the "release-ready, cross-distro, has a reason to exist"
milestone: unification across pacman/AUR/Flatpak, the app-vs-system guardrail,
and pipx/binary/AUR distribution. Phase 6 picked four of the five standout
features below by impact (deferring only Snap/Homebrew, the least
differentiating one) and **shipped all four**:

- [x] **Changelog / PKGBUILD diff viewer** — `Backend.changelog(pkg)`:
      AUR packages get a real PKGBUILD diff (fetched from AUR's cgit mirror,
      diffed against yay/paru's local build cache when present); Flatpak apps
      get the OSTree commit log via `flatpak remote-info --log`. Official
      pacman-repo packages return "not available" rather than faking a
      changelog Arch doesn't publish. New `screens/changelog.py`, dashboard
      `[C]` keybinding.
- [x] **Snapshot + rollback** — `core/snapshot.py`'s `SnapshotManager`
      auto-detects snapper (this dev host's real config) or timeshift, takes
      a snapshot before every full upgrade when enabled (never blocks the
      upgrade if creation fails or nothing's installed), and a new
      `screens/snapshots.py` lists snapshots with a rollback flow that
      requires an explicit arm-then-confirm (`R` then `Y`) — any other key,
      including the ones that would otherwise navigate away, cancels the arm
      instead. App-level `[B]` keybinding.
- [x] **apt / dnf native backends** — `backends/apt.py` / `backends/dnf.py`.
      `categorizer.py` gained `APT_CRITICAL_PATTERNS`/`DNF_CRITICAL_PATTERNS`
      and a `base_critical`/`base_optional` override on `classify()`/
      `is_system()` (defaulting to the original Arch lists, so nothing existing
      changed), plus a `SOURCE_BASE_PATTERNS` map so `categorize()` picks the
      right list per `Package.source` in a mixed-source scan. Both backends
      enforce their own system-layer guardrail the same way PacmanBackend does.
      Can't be live-tested on this Arch dev host (no apt/dnf installed) — unit
      tests mock `shutil.which`/`subprocess.run` against real-world
      `apt list --upgradable` / `dnf check-update` output formats instead.
- [x] **Update profiles / pinning** — `core/profiles.py` (fnmatch-based
      matching), a new `[profiles]` config section, dashboard `[P]` cycles
      profiles and auto-selects matching rows (never a locked row), and an
      opt-in `[automation] auto_update` in the daemon that updates a named
      profile's matches on every scan — with a *second*, independent
      exclusion of critical/system packages regardless of what the profile
      itself matches, since this path runs unattended. Logged to history and
      named in the desktop notification, never silent.
- [ ] **Optional extra backends** — Snap, Homebrew. Deferred; lowest-impact of
      the five per the original pick.

Also extracted `core/procutil.py` (`stream_subprocess`) once apt/dnf made it
the 3rd/4th copy of the same subprocess-streaming loop that `updater.py` and
`flatpak.py` already had — refactored those two to use it too, no behavior
change (all pre-existing tests still pass unchanged).

**Phase 6 status: DONE.** 163 tests green (up from 53 at the start of the
phase). `v0.2` itself is still untagged (`pyproject.toml` reads `0.1.0`) —
tagging `v0.2`/`v0.3` and the AUR push (blocked since Phase 4 on
`aur.archlinux.org` registration being closed) are release-process steps for
the user to trigger, not code changes.

## Why not "more features" instead?

The differentiator was already latent in what shipped for v0.2:
**unification + the safety guardrail + rollback**. Those are the things no
single package-manager command can do on its own. Phase 6 built depth on
that — rollback, changelog trust, and safe automation — rather than pure
breadth (Snap/Homebrew for their own sake), while still picking up apt/dnf
since reaching Debian/Fedora users is itself high-impact.
