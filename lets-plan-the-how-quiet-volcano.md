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

Work happens in the **code repo** `~/Documents/archbooster` (this session's cwd is
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

- [x] **LICENSE** — add MIT or Apache-2.0 (`LICENSE` file + `pyproject.toml` metadata).
  ```
  Without it the repo is legally "all rights reserved."
  ```
- [x] **Fix systemd path bug** — `systemd/archbooster.service` has
  ```
  `ExecStart=/usr/bin/archbooster`, but installs land in `~/.local/bin`. Change to
  `ExecStart=%h/.local/bin/archbooster --daemon` **or** `python -m archbooster --daemon`.
  ```
- [x] **Fix PEP 668 install** — `install.sh` uses `pip install --user`, which modern
  ```
  Arch/Ubuntu/Fedora block ("externally-managed-environment"). Switch the installer
  to **pipx** (`pipx install .`), which also fixes the path bug (pipx puts a stable
  shim on PATH).
  ```
- [x] **Drop** `--noconfirm` **as the default** — `updater._build_command()` /
  ```
  `_build_full_upgrade_command()` hardcode `--noconfirm`. Make it a config flag
  (`confirm = true` default); a public tool shouldn't silently skip pacman prompts.
  ```
- [x] **Wire config into categorizer** — `classify()` already accepts
  ```
  `extra_critical`/`extra_optional`, but `daemon.py` and `dashboard.py` call
  `categorize(packages)` with no config. Pass `load_config()` values through so
  user overrides actually take effect.
  ```
- [x] **Real repo URL** in `README.md` (currently `github.com/you/archbooster`).
- [x] **Init/confirm git + push**, add a minimal `pytest` suite for
  ```
  `scanner._parse_line`, `categorizer.classify/is_system`, and `updater`
  command-building, plus a GitHub Actions CI job.
  ```

---



## Phase 2 — Finish the dashboard + introduce a thin Backend seam

The README's "Phase 2" (full dashboard) is still unchecked. Do that **and** carve out
the minimal abstraction Flatpak needs — without the big plugin refactor.

- [x] **Finish** `screens/dashboard.py` **+** `screens/progress.py`: checkbox toggle,
  ```
  select-all/none/invert (`A`/`N`/`I`), `Enter` → run selected via `Updater.run`,
  `F` → `run_full_upgrade`, live streaming into the progress screen. Rows for
  system packages stay **locked** (guardrail already in `PackageRow.locked`).
  *(Screens were already built; progress output was made genuinely live via a
  threaded `stream_lines()` generator instead of buffering `list(...)`.)*
  ```
- [x] **Extract a** `Backend` **interface** — new `archbooster/core/backends/base.py`:
  ```
  `scan() -> list[Package]`, `update(names) -> Iterator[str]`,
  `full_upgrade() -> Iterator[str]`, `is_available() -> bool`, plus a `source` tag.
  Move today's pacman/AUR logic into `backends/pacman.py` (wrapping the existing
  `Scanner`/`Updater` code — reuse, don't rewrite). Keep `is_system()` as the
  pacman backend's guardrail.
  *(Implemented as `name` + `sources` tuple + `has_system_layer` instead of a
  single `source` tag, so the registry can route by `Package.source` and pick the
  system-layer backend for full upgrades. `PacmanBackend` wraps `Scanner`/`Updater`.)*
  ```
- [x] **Backend registry** — auto-detect installed backends via `shutil.which`; the
  ```
  scanner/daemon iterate over available backends instead of hardcoding pacman.
  *(New `backends/registry.py` owns the pending.json cache + update routing; the
  dashboard, daemon, and `--scan` all now call `BackendRegistry().scan()`.)*
  ```

**Phase 2 status: DONE.** 29 tests green (added `tests/test_backends.py`,
`tests/test_stream.py`). Verified headless TUI mount + guardrail (select-all can't
select a locked system pkg). Also fixed two packaging blockers found along the way:
added `archbooster.core.backends` to `pyproject` packages, and removed the PEP 639
license classifier that was breaking the wheel build (relevant to Phase 4).

Critical files: `archbooster/core/scanner.py`, `updater.py`, `categorizer.py`,
new `archbooster/core/backends/{base,pacman}.py`, `screens/dashboard.py`, `progress.py`.

---



## Phase 3 — Flatpak backend  ← this is where "all Linux" is reached

- [ ] `archbooster/core/backends/flatpak.py`:
  ```
  - scan: `flatpak remote-ls --updates --columns=application,version` (no root).
  - update: `flatpak update <app-ids>` (selective) / `flatpak update` (all).
  - **No `is_system` needed** — every Flatpak is app-layer by definition, so the
    whole guardrail question disappears; this is why the identity fits Flatpak
    perfectly.
  ```
- [ ] **Dashboard groups by source** (Official / AUR / Flatpak) so a mixed system
  ```
  (e.g. Arch + Flatpak, or Fedora with only Flatpak) shows one unified list.
  ```
- [ ] **Graceful degrade**: on a non-Arch box with only Flatpak, pacman backend
  ```
  reports `is_available() == False` and the UI shows just Flatpak apps — fixing
  today's misleading "no updates" on non-Arch.
  ```

**Outcome:** ArchBooster now does something useful on Ubuntu/Fedora/openSUSE/Arch —
the cross-distro release milestone.

---



## Phase 4 — Packaging & distribution (pipx + binary + distro packages)

- [ ] **pyproject.toml**: add classifiers, `readme`, license metadata, `[project.urls]`;
  ```
  publish to **PyPI** → `pipx install archbooster` works everywhere.
  ```
- [ ] **Static binary**: PyInstaller (or Nuitka) single-file build in CI, attached to
  ```
  **GitHub Releases** with SHA256 checksums — zero-Python install path.
  ```
- [ ] **Distro packages**: AUR `PKGBUILD` (`archbooster` / `archbooster-bin`) for Arch;
  ```
  `.deb`/`.rpm` (or COPR/PPA) for Debian/Fedora later.
  ```
- [ ] **Release CI**: tag-triggered workflow that builds wheel + binary + checksums.

---



## Phase 5 — Notifications & polish → tag **v0.2 public release**

- [ ] **Desktop notifications** from the daemon — `daemon.py` already has the
  ```
  `# TODO (phase 2): notify-send` hook. Use `notify-send` (present on essentially
  every desktop distro) to announce "N app updates (M critical)."
  ```
- [ ] **README rewrite** for the cross-distro story + install matrix (pipx / binary / AUR).
- [ ] **Docs**: quick screenshot/GIF of the TUI, config reference, the app-vs-system
  ```
  explanation as the headline feature.
  ```
- [ ] Update the Obsidian vault index (`ArchBooster — overview.md`) to reflect
  ```
  "cross-distro via Flatpak, released."
  ```

---



## Phase 6+ — Standout features (v0.3 and beyond)

These are the differentiators that make it more than "a nicer update prompt." Pick by
impact:

- [ ] **Changelog / PKGBUILD diff viewer** (README's old Phase 4) — show what actually
  ```
  changed before you update. Strong trust feature.
  ```
- [ ] **Snapshot + rollback** — trigger snapper/timeshift/btrfs snapshot before a full
  ```
  `-Syu`; one-key rollback. This is the killer feature for the *system* layer that
  no single command gives you.
  ```
- [ ] **apt / dnf native backends** — deeper integration for Debian/Fedora (each needs
  ```
  its own system-package list for the guardrail, since `categorizer` is currently
  pacman-name-based).
  ```
- [ ] **Update profiles / pinning** — "only bump browsers & editors," ignore lists per
  ```
  backend, scheduled auto-update of a chosen safe subset.
  ```
- [ ] Optional extra backends: Snap, Homebrew.

---



## Must-have vs. standout (summary)


| Must-have (v0.2, Phases 0–5)                                | Standout (v0.3+, Phase 6) |
| ----------------------------------------------------------- | ------------------------- |
| LICENSE, working installer (pipx), no `--noconfirm` default | Snapshot + rollback       |
| Finished dashboard + progress + guardrail                   | Changelog / diff viewer   |
| **Flatpak backend (= cross-distro)**                        | apt/dnf native backends   |
| Unified multi-source view                                   | Update profiles / pinning |
| Desktop notifications                                       | Snap / brew backends      |
| pipx + binary + AUR distribution                            |                           |


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

