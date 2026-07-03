# Roadmap — Phase 6+ (v0.3 and beyond)

v0.2 (Phases 0–5) is the "release-ready, cross-distro, has a reason to exist"
milestone: unification across pacman/AUR/Flatpak, the app-vs-system guardrail,
and pipx/binary/AUR distribution. Everything below is a **standout feature**,
picked by how much it deepens that identity rather than adding breadth:

- **Changelog / PKGBUILD diff viewer** — show what actually changed in a
  package before you update it. Strong trust feature.
- **Snapshot + rollback** — trigger a snapper/timeshift/btrfs snapshot before
  a full `-Syu`, with one-key rollback. The killer feature for the *system*
  layer: no single command (`pacman -Syu`, `flatpak update`) gives you this.
- **apt / dnf native backends** — deeper Debian/Fedora integration. Each needs
  its own system-package list for the guardrail, since `categorizer.py` is
  currently pacman-name-based (kernel, mesa, nvidia, glibc, systemd, ...).
- **Update profiles / pinning** — "only bump browsers & editors," per-backend
  ignore lists, scheduled auto-update of a chosen safe subset.
- **Optional extra backends** — Snap, Homebrew.

## Why not "more features" instead?

The differentiator is already latent in what's shipped: **unification + the
safety guardrail + (eventually) rollback**. Those are the things no single
package-manager command can do on its own. The plan is to build depth on that
rather than breadth (more backends for their own sake) — hence rollback
ranking above apt/dnf support despite apt/dnf reaching more users.
