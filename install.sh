#!/usr/bin/env bash
# ArchBooster installer
# Installs the app with pipx (isolated venv, works on modern PEP 668 distros),
# then sets up the systemd user timer for background update checks.

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RESET="\033[0m"

echo -e "${BOLD}⚡ ArchBooster installer${RESET}\n"

# 1. Ensure pipx is available. `pip install --user` is blocked on modern distros
#    (PEP 668 "externally-managed-environment"), so we use pipx, which installs
#    into an isolated venv and drops a shim in ~/.local/bin.
if ! command -v pipx >/dev/null 2>&1; then
    echo -e "${YELLOW}→ pipx not found.${RESET}"
    echo "  Install it first, then re-run this script:"
    echo "    Arch:          sudo pacman -S python-pipx"
    echo "    Debian/Ubuntu: sudo apt install pipx"
    echo "    Fedora:        sudo dnf install pipx"
    echo "    Any distro:    python3 -m pip install --user pipx  (then: pipx ensurepath)"
    exit 1
fi

# 2. Install (or upgrade) archbooster from this checkout.
echo -e "${GREEN}→ Installing archbooster with pipx...${RESET}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pipx install --force "$SCRIPT_DIR"

# 3. Make sure ~/.local/bin is on PATH (idempotent).
pipx ensurepath >/dev/null 2>&1 || true

# 4. Install systemd user units (optional — only if systemd is present).
if command -v systemctl >/dev/null 2>&1; then
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    echo -e "${GREEN}→ Installing systemd user units...${RESET}"
    cp "$SCRIPT_DIR/systemd/archbooster.service" "$SYSTEMD_DIR/"
    cp "$SCRIPT_DIR/systemd/archbooster.timer"   "$SYSTEMD_DIR/"
    systemctl --user daemon-reload
    systemctl --user enable --now archbooster.timer
    echo -e "   Background checks enabled (every 4h)."
else
    echo -e "${YELLOW}→ systemd not detected; skipping the background timer.${RESET}"
fi

echo ""
echo -e "${BOLD}✅ Done!${RESET}"
echo -e "   Run ${YELLOW}archbooster${RESET}         to open the TUI"
echo -e "   Run ${YELLOW}archbooster --scan${RESET}  to check updates in the terminal"
echo -e "   (If 'archbooster' isn't found, open a new shell so PATH updates take effect.)"
