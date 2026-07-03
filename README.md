# ⚡ ArchBooster

A Driver Booster-style selective update manager for Arch Linux.
Built with Python + Textual. Supports official repos and AUR (via yay/paru).

---

## Features

- Scans all installed packages for available updates
- Categorizes them: 🔴 Critical / 🟡 Normal / 🟢 Optional
- Select individual packages to update — never forced
- Live streaming output during update (real pacman/yay output)
- Update history log
- Background daemon via systemd timer (checks every 4h, no auto-updates)

---

## Requirements

- Arch Linux
- Python 3.11+
- `pacman-contrib` (for `checkupdates`)  → `sudo pacman -S pacman-contrib`
- `yay` or `paru` (for AUR support)

---

## Install

```bash
git clone https://github.com/ansu555/archbooster
cd archbooster
bash install.sh
```

> The installer uses **pipx** (isolated venv — works on modern PEP 668 distros).
> Install pipx first if needed: `sudo pacman -S python-pipx` /
> `sudo apt install pipx` / `sudo dnf install pipx`.

---

## Usage

| Command                    | Action                              |
|----------------------------|-------------------------------------|
| `archbooster`              | Open the full TUI dashboard         |
| `archbooster --scan`       | Print available updates and exit    |
| `archbooster --daemon`     | Run one background check (systemd)  |

### Keybindings (inside TUI)

| Key      | Action                  |
|----------|-------------------------|
| `A`      | Select all packages     |
| `N`      | Deselect all            |
| `I`      | Invert selection        |
| `Enter`  | Update selected         |
| `R`      | Re-scan for updates     |
| `H`      | Open history            |
| `S`      | Open settings           |
| `Q`      | Quit                    |

---

## Config

Auto-created at `~/.config/archbooster/config.toml` on first run:

```toml
[general]
aur_helper     = "yay"   # or "paru"
check_interval = 4       # hours between background scans

[categories]
extra_critical = []      # extra package prefixes to mark critical
extra_optional = []

[ignore]
packages = []            # packages to hide from the update list
```

---

## Project Structure

```
archbooster/
├── main.py                  # Entry point + CLI flags
├── app.py                   # Textual app root + screen router
├── daemon.py                # Background check loop (systemd)
├── core/
│   ├── scanner.py           # checkupdates + yay -Qu, caching
│   ├── categorizer.py       # critical / normal / optional
│   ├── updater.py           # runs yay/pacman, streams output
│   ├── history.py           # read/write history.json
│   └── config.py            # load/write config.toml
├── screens/
│   ├── dashboard.py         # Main checklist UI
│   ├── progress.py          # Live update output
│   ├── history.py           # Past updates log
│   └── settings.py          # Settings editor
├── systemd/
│   ├── archbooster.service  # Systemd user service
│   └── archbooster.timer    # Systemd timer (every 4h)
└── install.sh               # One-shot installer
```

---

## Roadmap

- [x] Phase 1 — Core engine + project scaffold
- [ ] Phase 2 — Full Textual dashboard with checkboxes + progress screen
- [ ] Phase 3 — Desktop notifications (notify-send)
- [ ] Phase 4 — AUR PKGBUILD diff viewer
- [ ] Phase 5 — AUR package on the AUR itself
