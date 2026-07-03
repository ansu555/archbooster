# ⚡ ArchBooster

**Update your apps, leave the OS alone.**

A selective update manager for Linux, built with Python + Textual. ArchBooster
gives you one unified, checkbox-driven view across every package source on
your machine — official repos, AUR, and **Flatpak** — categorizes updates by
risk, and refuses to let a partial system upgrade slip through by accident.

Runs on **Arch (+ Arch-based) via pacman/AUR, and on any distro with Flatpak
— Fedora, Ubuntu, openSUSE, Debian, and beyond.**

---

## Why this, when `flatpak update` and `yay -Sua` already exist?

Each package manager already has its own "update everything" command. What
none of them gives you:

- **One list across all of them.** pacman, AUR, and Flatpak updates in a
  single screen instead of three terminals.
- **A safety guardrail.** ArchBooster knows the difference between an
  **app** (Firefox, a Flatpak, an AUR `-bin` package) and the **system**
  (kernel, mesa/nvidia drivers, glibc, systemd). Cherry-picking individual
  packages is safe for apps — but a *partial* upgrade of the system layer is
  exactly how a rolling-release install breaks. ArchBooster locks
  system-layer packages out of selective updates entirely; they can only be
  bumped together via a full `-Syu`.
- **Categorization, history, and a background check** — updates are sorted
  🔴 critical / 🟡 normal / 🟢 optional, every run is logged, and a systemd
  timer can check on a schedule and notify you without auto-updating anything.

That combination — unification + the app/system guardrail — is the thing no
single command does.

---

## Features

- Unified scan across **pacman + AUR (yay/paru) + Flatpak**, grouped by source
- 🔴 Critical / 🟡 Normal / 🟢 Optional categorization (configurable overrides)
- Select individual packages to update — never forced, system packages locked
- Live streaming output during update (real pacman/yay/flatpak output)
- Update history log
- Background daemon via systemd timer (checks every N hours) with a desktop
  notification (`notify-send`) when updates are found — no auto-updates
- Graceful degrade: on a non-Arch box with only Flatpak installed, the pacman
  backend just reports unavailable and you get a clean Flatpak-only list

---

## Requirements

- Python 3.11+
- At least one supported backend:
  - **Arch / Arch-based**: `pacman-contrib` (for `checkupdates`) and
    `yay` or `paru` for AUR — `sudo pacman -S pacman-contrib`
  - **Any distro**: `flatpak`, with at least one remote added (e.g. Flathub)
- Optional: `notify-send` (`libnotify`) for desktop notifications from the
  background daemon — installed by default on almost every desktop distro
- Optional: `systemd` user services, for the background timer

---

## Install

Three ways to get it, pick whichever fits:

| Method | Command | Best for |
|---|---|---|
| **pipx** (PyPI) | `pipx install archbooster` | Any distro with Python 3.11+ |
| **Static binary** | Download `archbooster-linux-x86_64` from [Releases](https://github.com/ansu555/archbooster/releases) | Zero-Python install, quick try |
| **AUR** | `yay -S archbooster` *(source)* or `archbooster-bin` *(prebuilt)* | Arch / Arch-based — **pending**, see note below |

```bash
# pipx (recommended)
pipx install archbooster

# from source, with the bundled installer (also sets up the systemd timer)
git clone https://github.com/ansu555/archbooster
cd archbooster
bash install.sh

# static binary
curl -LO https://github.com/ansu555/archbooster/releases/latest/download/archbooster-linux-x86_64
chmod +x archbooster-linux-x86_64
./archbooster-linux-x86_64
```

> Installing pipx first, if needed: `sudo pacman -S python-pipx` /
> `sudo apt install pipx` / `sudo dnf install pipx`.

> **AUR note:** the `PKGBUILD`s are ready in `packaging/aur/`, but new-account
> registration on `aur.archlinux.org` is currently closed on Arch's side, so
> the packages aren't pushed yet. Use pipx or the binary until that reopens.

---

## Usage

| Command                    | Action                              |
|-----------------------------|--------------------------------------|
| `archbooster`               | Open the full TUI dashboard         |
| `archbooster --scan`        | Print available updates and exit    |
| `archbooster --daemon`      | Run one background check (systemd)  |

### Keybindings (inside TUI)

| Key      | Action                        |
|----------|-------------------------------|
| `A`      | Select all packages           |
| `N`      | Deselect all                  |
| `I`      | Invert selection               |
| `Enter`  | Update selected (app layer)   |
| `F`      | Full system upgrade (`-Syu`)  |
| `R`      | Re-scan for updates           |
| `H`      | Open history                  |
| `S`      | Open settings                 |
| `Q`      | Quit                          |

![ArchBooster dashboard](docs/screenshot.svg)

---

## Config

Auto-created at `~/.config/archbooster/config.toml` on first run:

```toml
[general]
aur_helper     = "yay"   # or "paru"
check_interval = 4       # hours between background daemon scans
confirm        = false   # false: run pacman/yay/flatpak non-interactively
                          #        (your selection in the TUI is the
                          #        confirmation).
                          # true:  also show the package manager's own
                          #        prompts (best from a plain terminal).
notify         = true    # desktop notification (notify-send) when the
                          # background daemon finds updates. No-ops quietly
                          # if notify-send isn't installed.

[categories]
extra_critical = []      # extra package name prefixes to force "critical"
extra_optional = []      # extra package name prefixes to force "optional"

[ignore]
packages = []            # packages to hide from the update list entirely
```

See [`docs/config.md`](docs/config.md) for a field-by-field reference.

---

## Project Structure

```
archbooster/
├── main.py                     # Entry point + CLI flags
├── app.py                      # Textual app root + screen router
├── daemon.py                   # Background check loop (systemd) + notify
├── core/
│   ├── scanner.py              # Package dataclass + line parsing
│   ├── categorizer.py          # critical / normal / optional + guardrail
│   ├── updater.py               # runs yay/pacman, streams output
│   ├── notify.py                # notify-send wrapper
│   ├── history.py               # read/write history.json
│   ├── config.py                # load/write config.toml
│   └── backends/
│       ├── base.py              # Backend interface
│       ├── pacman.py            # official repos + AUR
│       ├── flatpak.py           # Flatpak — the cross-distro path
│       └── registry.py          # auto-detects installed backends
├── screens/
│   ├── dashboard.py             # Main checklist UI, grouped by source
│   ├── progress.py              # Live update output
│   ├── history.py                # Past updates log
│   └── settings.py               # Settings editor
├── systemd/
│   ├── archbooster.service       # Systemd user service
│   └── archbooster.timer         # Systemd timer (every N hours)
├── packaging/                    # PyInstaller binary + AUR PKGBUILDs
└── install.sh                    # One-shot pipx-based installer
```

---

## Roadmap

- [x] Phase 0 — Release hardening (license, pipx installer, config-driven
      confirm, tests + CI)
- [x] Phase 2 — Full Textual dashboard + `Backend` abstraction
- [x] Phase 3 — Flatpak backend (cross-distro milestone)
- [x] Phase 4 — Packaging: pipx/PyPI, static binary, AUR `PKGBUILD`s, release CI
- [x] Phase 5 — Desktop notifications, docs, **v0.2 public release**
- [ ] Phase 6+ — Changelog/diff viewer, snapshot + rollback, apt/dnf backends,
      update profiles — see [the roadmap doc](docs/ROADMAP.md) for the
      full list

---

## License

MIT — see [`LICENSE`](LICENSE).
