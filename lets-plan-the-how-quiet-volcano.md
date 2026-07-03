# ArchBooster — Cross-Distro Release Roadmap (Phases 2–6)

## Context

ArchBooster is a Python + Textual TUI "selective update manager" — *"update your
apps, leave the OS alone."* Today it is **v0.1.0, Arch-only**: every operation
shells out to `checkupdates` + `yay/paru` + `pacman` (`archbooster/core/scanner.py`,
`updater.py`). The app-vs-system safety guardrail is already built
(`categorizer.is_system()` locks kernel/mesa/nvidia/etc. out of cherry-pick updates).

The goal: get it **release-ready for all Linux distros** and give it a reason to
exist. Decisions made for this roadmap:

- **Cross-distro path = Flatpak-first.** Adding a Flatpak backend makes it work on
  *every* distro at once, and `flatpak update` is literally the app-vs-system
  identity. apt/dnf come later.
- **Scope = lean MVP (v0.2 public), standout features deferred to v0.3+.**
- **Distribution = pipx/PyPI + static binary + distro packages** (not shipped as a
  Flatpak itself — that would sandbox us away from host pacman/apt).

Work happens in the **code repo `~/Documents/archbooster`** (this session's cwd is
the Obsidian design vault; only the vault index note gets a light update).

---

## First: "Can't one command already do this?" (positioning)

Answer honestly, because it decides what the tool must be:

- **Per-backend, a single command already exists.** `flatpak update` updates all
  apps and leaves the OS alone. `yay -Sua` upgrades only AUR/app packages. So
  ArchBooster **cannot** justify itself as "a thing that runs an update."
- **What no single command does:** a *unified* view across backends
  (pacman + AUR + Flatpak + later apt/dnf) with (a) the **safety guardrail** that
  refuses partial system upgrades, (b) **categorization** (critical/normal/optional),
  (c) **selective cherry-pick** of exactly which apps to bump, (d) **history**, and
  (e) **scheduled background checks + notifications**.

**Conclusion for the roadmap:** ArchBooster is a *coordinator / safety layer over
many package managers*, not a replacement for one command. Every standout feature
below reinforces that (unification + safety + UX), because "just update" is a solved
problem.

---

## Phase 0 — Release hardening (blockers; must land before any public tag)

These are correctness/legal blockers, not features. All in the code repo.

- [ ] **LICENSE** — add MIT or Apache-2.0 (`LICENSE` file + `pyproject.toml` metadata).
      Without it the repo is legally "all rights reserved."
- [ ] **Fix systemd path bug** — `systemd/archbooster.service` has
      `ExecStart=/usr/bin/archbooster`, but installs land in `~/.local/bin`. Change to
      `ExecStart=%h/.local/bin/archbooster --daemon` **or** `python -m archbooster --daemon`.
- [ ] **Fix PEP 668 install** — `install.sh` uses `pip install --user`, which modern
      Arch/Ubuntu/Fedora block ("externally-managed-environment"). Switch the installer
      to **pipx** (`pipx install .`), which also fixes the path bug (pipx puts a stable
      shim on PATH).
- [ ] **Drop `--noconfirm` as the default** — `updater._build_command()` /
      `_build_full_upgrade_command()` hardcode `--noconfirm`. Make it a config flag
      (`confirm = true` default); a public tool shouldn't silently skip pacman prompts.
- [ ] **Wire config into categorizer** — `classify()` already accepts
      `extra_critical`/`extra_optional`, but `daemon.py` and `dashboard.py` call
      `categorize(packages)` with no config. Pass `load_config()` values through so
      user overrides actually take effect.
- [ ] **Real repo URL** in `README.md` (currently `github.com/you/archbooster`).
- [ ] **Init/confirm git + push**, add a minimal `pytest` suite for
      `scanner._parse_line`, `categorizer.classify/is_system`, and `updater`
      command-building, plus a GitHub Actions CI job.

---

## Phase 2 — Finish the dashboard + introduce a thin Backend seam

The README's "Phase 2" (full dashboard) is still unchecked. Do that **and** carve out
the minimal abstraction Flatpak needs — without the big plugin refactor.

- [x] **Finish `screens/dashboard.py` + `screens/progress.py`**: checkbox toggle,
      select-all/none/invert (`A`/`N`/`I`), `Enter` → run selected via `Updater.run`,
      `F` → `run_full_upgrade`, live streaming into the progress screen. Rows for
      system packages stay **locked** (guardrail already in `PackageRow.locked`).
      *(Screens were already built; progress output was made genuinely live via a
      threaded `stream_lines()` generator instead of buffering `list(...)`.)*
- [x] **Extract a `Backend` interface** — new `archbooster/core/backends/base.py`:
      `scan() -> list[Package]`, `update(names) -> Iterator[str]`,
      `full_upgrade() -> Iterator[str]`, `is_available() -> bool`, plus a `source` tag.
      Move today's pacman/AUR logic into `backends/pacman.py` (wrapping the existing
      `Scanner`/`Updater` code — reuse, don't rewrite). Keep `is_system()` as the
      pacman backend's guardrail.
      *(Implemented as `name` + `sources` tuple + `has_system_layer` instead of a
      single `source` tag, so the registry can route by `Package.source` and pick the
      system-layer backend for full upgrades. `PacmanBackend` wraps `Scanner`/`Updater`.)*
- [x] **Backend registry** — auto-detect installed backends via `shutil.which`; the
      scanner/daemon iterate over available backends instead of hardcoding pacman.
      *(New `backends/registry.py` owns the pending.json cache + update routing; the
      dashboard, daemon, and `--scan` all now call `BackendRegistry().scan()`.)*

**Phase 2 status: DONE.** 29 tests green (added `tests/test_backends.py`,
`tests/test_stream.py`). Verified headless TUI mount + guardrail (select-all can't
select a locked system pkg). Also fixed two packaging blockers found along the way:
added `archbooster.core.backends` to `pyproject` packages, and removed the PEP 639
license classifier that was breaking the wheel build (relevant to Phase 4).

Critical files: `archbooster/core/scanner.py`, `updater.py`, `categorizer.py`,
new `archbooster/core/backends/{base,pacman}.py`, `screens/dashboard.py`, `progress.py`.

---

## Phase 3 — Flatpak backend  ← this is where "all Linux" is reached

- [x] **`archbooster/core/backends/flatpak.py`**:
      - scan: `flatpak remote-ls --updates --columns=application,version` (no root).
      - update: `flatpak update <app-ids>` (selective) / `flatpak update` (all).
      - **No `is_system` needed** — every Flatpak is app-layer by definition, so the
        whole guardrail question disappears; this is why the identity fits Flatpak
        perfectly.
      *(Takes a `confirm` kwarg like `PacmanBackend`, matching the registry's
      uniform `cls(confirm=confirm)` construction and Phase 0's config-driven
      confirm flag: `confirm=False` appends `-y`, `confirm=True` surfaces
      flatpak's own prompt. Unknown/blank versions parse to `"?"`, mirroring
      `Scanner._parse_line`'s existing placeholder convention.)*
- [x] **Backend registered** — `FlatpakBackend` appended to `BACKEND_CLASSES` in
      `backends/registry.py`; daemon/dashboard/main already call through the
      registry from Phase 2, so no other call site changed.
- [x] **Dashboard groups by source** (Official / AUR / Flatpak) so a mixed system
      (e.g. Arch + Flatpak, or Fedora with only Flatpak) shows one unified list.
      *(New `SourceHeader` divider widget in `screens/dashboard.py`; packages now
      sort by `(source, priority, name)` instead of just `(priority, name)`.)*
- [x] **Graceful degrade**: on a non-Arch box with only Flatpak, pacman backend
      reports `is_available() == False` and the UI shows just Flatpak apps — fixing
      today's misleading "no updates" on non-Arch. Already generic via the Phase 2
      registry; verified with a monkeypatched "no pacman tools, flatpak present"
      host in `test_registry_degrades_to_flatpak_only_on_non_arch_host`, and live
      on this real Arch host (no flatpak installed) where the registry correctly
      returns only `['pacman']`.
- [x] **Bug fix found along the way**: `PackageRow` built its checkbox `Label` with
      `id=f"chk-{pkg.name}"`, but Textual ids disallow dots — every Flatpak app id
      (`org.gimp.GIMP`) crashed the dashboard on first render. Fixed by holding a
      direct widget reference (`self._check_label`) instead of an id-based
      `query_one` lookup; verified via a headless `run_test()` mount with mixed
      official/AUR/Flatpak packages (3 group headers, correct sort order, guardrail
      still blocks the locked system row, Flatpak row toggles correctly).

**Phase 3 status: DONE.** 48 tests green (added `tests/test_flatpak.py`, extended
`tests/test_backends.py` with the degrade test). Critical files:
`archbooster/core/backends/flatpak.py` (new), `backends/registry.py`,
`screens/dashboard.py`.

**Outcome:** ArchBooster now does something useful on Ubuntu/Fedora/openSUSE/Arch —
the cross-distro release milestone.

---

## Phase 4 — Packaging & distribution (pipx + binary + distro packages)

- [x] **pyproject.toml**: add classifiers, `readme`, license metadata, `[project.urls]`;
      publish to **PyPI** → `pipx install archbooster` works everywhere.
      *(Metadata already landed as a side effect of the Phase 2 packaging fix — verified
      with `python -m build` + `twine check` (PASSED on both sdist/wheel) and a clean-venv
      wheel install that exercises the `archbooster` console-script entry point. Actual
      `twine upload`/PyPI publish is left to the release workflow's `publish-pypi` job,
      gated on a `PYPI_API_TOKEN` repo secret the user still needs to add — that's an
      external-account action outside what I can do from here.)*
- [x] **Static binary**: PyInstaller (or Nuitka) single-file build in CI, attached to
      **GitHub Releases** with SHA256 checksums — zero-Python install path.
      *(New `packaging/build_binary.sh` runs `pyinstaller --onefile --collect-all textual`;
      `--collect-all` was needed since Textual ships data resources. Verified end-to-end:
      the frozen 16MB binary was actually launched and rendered the real dashboard TUI
      correctly, not just `--help`.)*
- [x] **Distro packages**: AUR `PKGBUILD` (`archbooster` / `archbooster-bin`) for Arch;
      `.deb`/`.rpm` (or COPR/PPA) for Debian/Fedora later.
      *(New `packaging/aur/{archbooster,archbooster-bin}/PKGBUILD` + generated `.SRCINFO`
      (validated via `makepkg --printsrcinfo`). Source package builds the wheel via
      `python -m build`/`python -m installer`; bin package installs the release binary
      as `/usr/bin/archbooster`. Both ship a *repackaged* systemd service pointing
      `ExecStart` at `/usr/bin/archbooster` — the repo's own `systemd/archbooster.service`
      intentionally targets `%h/.local/bin` for the pipx path from Phase 0, which is wrong
      once pacman puts the binary in `/usr/bin`. `sha256sums` are `SKIP` placeholders since
      no tag/release exists yet; `packaging/aur/README.md` documents the
      `updpkgsums`+`.SRCINFO` regen step per release. Debian/Fedora packages deferred, as
      originally scoped.)*
- [x] **Release CI**: tag-triggered workflow that builds wheel + binary + checksums.
      *(New `.github/workflows/release.yml`, triggered on `v*` tags: parallel
      `build-wheel`/`build-binary` jobs, a `release` job that computes `SHA256SUMS.txt`
      and publishes a GitHub Release via `softprops/action-gh-release`, and an opt-in
      `publish-pypi` job that no-ops until `PYPI_API_TOKEN` is set.)*

**Phase 4 status: SHIPPED.** `v0.1.0` is live: https://github.com/ansu555/archbooster/releases/tag/v0.1.0
and https://pypi.org/project/archbooster. Hit and fixed a real GitHub Actions bug along
the way — the `secrets` context isn't valid in *any* `if:` conditional (job or step
level), which silently killed the whole workflow (0 jobs scheduled) until routed through
`env:` instead; `actionlint` (via `go install`, no sudo needed) nailed the diagnosis after
the REST API gave nothing useful. **AUR push is blocked**, not skipped: `aur.archlinux.org`
currently has new-account registration disabled (Arch-side anti-abuse decision). The
PKGBUILDs in `packaging/aur/` are otherwise ready, still carrying `SKIP` checksum
placeholders — revisit once registration reopens (see `packaging/aur/README.md` for the
`updpkgsums` + `.SRCINFO` + push steps). 48 tests still green.
Also cleaned up incidental repo mess found along the way: a stray copy of this plan file
had been committed into `archbooster/widgets/`, and `archbooster.egg-info/` (a build
artifact) had been tracked in git since the initial commit despite being `.gitignore`d —
both removed. Critical files: `pyproject.toml`, new `packaging/build_binary.sh`,
`packaging/aur/**`, `.github/workflows/release.yml`.

---

## Phase 5 — Notifications & polish → tag **v0.2 public release**

- [x] **Desktop notifications** from the daemon — `notify_send()` in
      `archbooster/core/notify.py` wraps `notify-send`, no-ops quietly when it isn't
      installed. `daemon.py` fires it with an "N app updates (M critical)" summary,
      gated on the new `[general] notify` config flag.
- [x] **README rewrite** for the cross-distro story + install matrix (pipx / binary / AUR).
- [x] **Docs**: `docs/config.md` config reference, `docs/screenshot.svg` embedded in
      the README, the app-vs-system explanation as the headline "Why this" section.
- [ ] Update the Obsidian vault index (`ArchBooster — overview.md`) to reflect
      "cross-distro via Flatpak, released." *(Out of scope from the code repo —
      the vault lives in a separate location; do from the Obsidian-vault session.)*

**Phase 5 status: DONE** (code + docs side). Landed in a prior session
(`b7c1978`/`bac22e4`, undocumented here until now) — 53 tests green at the time
Phase 6 started. `v0.2` has not been tagged yet (`pyproject.toml` still reads
`0.1.0`, no `v0.2` git tag); tagging is a release-process step, not a code change,
left for the user to trigger alongside the AUR-push follow-up from Phase 4.

---

## Phase 6+ — Standout features (v0.3 and beyond)

These are the differentiators that make it more than "a nicer update prompt." Picked
by impact (user chose all four higher-impact items; Snap/Homebrew deferred):

- [x] **Changelog / PKGBUILD diff viewer** (README's old Phase 4) — show what actually
      changed before you update. Strong trust feature.
      *(`Backend.changelog(package)` — concrete default `None` on the base class so
      not every backend needs one. `PacmanBackend`: AUR packages fetch the PKGBUILD
      from AUR's cgit mirror (`aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h=...`)
      and diff it against yay/paru's local build cache when present (`difflib`);
      official-repo packages return `None` — Arch doesn't publish a machine-readable
      per-package changelog offline, so faking one would be worse than admitting
      there's nothing to show. `FlatpakBackend`: tries every configured remote's
      `flatpak remote-info --log` until one has the app (since `remote-ls --updates`
      doesn't say which remote an app came from). New `screens/changelog.py`;
      dashboard `[C]` opens it for the highlighted row.)*
- [x] **Snapshot + rollback** — trigger snapper/timeshift/btrfs snapshot before a full
      `-Syu`; one-key rollback. This is the killer feature for the *system* layer that
      no single command gives you.
      *(New `core/snapshot.py`: `SnapshotManager` auto-detects snapper — confirmed
      real and configured (`root` config) on this dev host — or timeshift, `auto`/
      pinned/`none` via `[snapshot].backend`. Wired into `registry.full_upgrade()` as
      an optional `snapshot=` kwarg: creates a snapshot before the first system-layer
      backend runs, never blocks the upgrade if creation fails or nothing's installed.
      `screens/snapshots.py` lists snapshots and rolls back via an explicit two-step
      arm-then-confirm (`R` then `Y`) — verified via headless Pilot tests that any
      other key, *including escape* (which would otherwise leave the screen), cancels
      the arm instead of firing or navigating away. App-level `[B]` keybinding.)*
- [x] **apt / dnf native backends** — deeper integration for Debian/Fedora (each needs
      its own system-package list for the guardrail, since `categorizer` is currently
      pacman-name-based).
      *(New `backends/apt.py` (`apt list --upgradable` parsing, regex-based to handle
      the multi-repo/comma-separated field) and `backends/dnf.py` (`dnf check-update`,
      which exits 100 — not 0 — when updates exist; handled explicitly). `categorizer`
      gained `APT_CRITICAL_PATTERNS`/`DNF_CRITICAL_PATTERNS` and a
      `base_critical`/`base_optional` override on `classify()`/`is_system()` that
      defaults to the original Arch lists (zero behavior change for existing callers),
      plus a `SOURCE_BASE_PATTERNS` map so `categorize()` — previously classifying
      every package against Arch's list regardless of source, a latent bug for any
      future non-Arch backend — now picks the right pattern pair per `Package.source`.
      Neither apt nor dnf is installed on this Arch dev host, so both are unit-tested
      against real-world command-output formats via mocked `subprocess.run` rather
      than live-verified; they correctly report `is_available() == False` here and
      drop out of the registry, same graceful-degrade path Phase 3 built for Flatpak.)*
- [x] **Update profiles / pinning** — "only bump browsers & editors," ignore lists per
      backend, scheduled auto-update of a chosen safe subset.
      *(New `core/profiles.py`: `fnmatch`-based pattern matching, so a plain name is
      an exact match and `*` adds prefix/suffix/substring. New `[profiles]` config
      section (named pattern lists) and `[automation]` (`auto_update`,
      `auto_update_profile`, both opt-in/off by default). Dashboard `[P]` cycles
      configured profiles, auto-selecting matching rows and never a locked/system row
      — verified with a `"*"` catch-all profile in a headless test to confirm the
      guardrail holds even against a deliberately-adversarial pattern. `daemon.py`'s
      `_run_auto_update()` re-excludes critical/system packages a *second* time
      independent of the profile match (this path runs unattended, so it gets the
      guardrail twice), logs every run to history, and names what was auto-updated in
      the desktop notification body rather than updating silently.)*
- [ ] Optional extra backends: Snap, Homebrew. *(Deferred — user's pick; lowest-impact
      of the five options offered.)*

**Phase 6 status: DONE.** Also extracted `core/procutil.py`'s `stream_subprocess()`
once apt/dnf made a 3rd/4th verbatim copy of the subprocess-streaming loop that
`updater.py` and `flatpak.py` already duplicated — refactored those two to use it,
no behavior change. 163 tests green (up from 53 at the start of this phase — added
`test_apt.py`, `test_dnf.py`, `test_snapshot.py`, `test_snapshots_screen.py`,
`test_changelog_screen.py`, `test_profiles.py`, `test_dashboard_profiles.py`,
`test_daemon.py`, `test_config.py`, plus extensions to `test_categorizer.py`,
`test_backends.py`, `test_flatpak.py`). Verified headlessly via Textual's
`run_test()`/Pilot for every new screen and keybinding (changelog view, profile
cycling incl. the guardrail-under-adversarial-profile case, and the full
arm/cancel/confirm rollback flow). `v0.2`/`v0.3` tagging and the AUR push (still
blocked on Arch-side account registration since Phase 4) are release-process steps
left for the user — not code changes.

Critical files: `archbooster/core/categorizer.py`, `procutil.py` (new),
`profiles.py` (new), `snapshot.py` (new), `config.py`, `daemon.py`,
`backends/{base,pacman,flatpak,apt,dnf}.py` (`apt`/`dnf` new), `backends/registry.py`,
`screens/{dashboard,progress,settings}.py`, `screens/{changelog,snapshots}.py` (new),
`app.py`.

---

## Must-have vs. standout (summary)

| Must-have (v0.2, Phases 0–5) | Standout (v0.3+, Phase 6) |
|---|---|
| LICENSE, working installer (pipx), no `--noconfirm` default | Snapshot + rollback |
| Finished dashboard + progress + guardrail | Changelog / diff viewer |
| **Flatpak backend (= cross-distro)** | apt/dnf native backends |
| Unified multi-source view | Update profiles / pinning |
| Desktop notifications | Snap / brew backends |
| pipx + binary + AUR distribution | |

**Do we need more features to stand out?** Not *more* — the differentiator is already
latent: **unification + the safety guardrail + rollback.** Those are the things no
single command (`flatpak update`, `yay -Sua`) can do. Build depth on that, not breadth.

---

## Verification (how we prove each phase works)

- **Guardrail / logic** (no distro needed): `pytest` over `categorizer.classify`,
  `is_system`, `scanner._parse_line`, `updater._build_command` (assert system pkgs are
  filtered and `-y` never appears in selective updates).
- **Arch path**: on this machine, `archbooster --scan` and the TUI update a real
  app-layer package (e.g. a `-bin`), confirm a locked system row can't be selected.
- **Cross-distro proof (the key test)**: spin up a **Fedora and an Ubuntu container/VM
  with only Flatpak** installed; `archbooster --scan` must list Flatpak updates and
  `flatpak update` must run — proving "all Linux," and that the pacman backend degrades
  cleanly instead of showing a misleading empty list.
- **Distribution smoke tests**: `pipx install archbooster` on Ubuntu + Fedora; run the
  PyInstaller binary on a box with no Python; install the AUR package on Arch — each
  launches the TUI and completes one update.
- **Daemon/notify**: trigger the systemd user timer, confirm the (fixed) `ExecStart`
  runs and a `notify-send` desktop notification appears.
