#!/usr/bin/env bash
# ArchBooster installer
# Sets up: Python package, systemd user service, PATH entry

set -e

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RESET="\033[0m"

echo -e "${BOLD}⚡ ArchBooster installer${RESET}\n"

# 1. Install Python dependencies
echo -e "${GREEN}→ Installing Python dependencies...${RESET}"
pip install --user textual

# 2. Install the package itself (editable for now)
echo -e "${GREEN}→ Installing archbooster...${RESET}"
pip install --user -e .

# 3. Copy systemd user units
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"
echo -e "${GREEN}→ Installing systemd user units...${RESET}"
cp systemd/archbooster.service "$SYSTEMD_DIR/"
cp systemd/archbooster.timer   "$SYSTEMD_DIR/"

# 4. Enable and start the timer
systemctl --user daemon-reload
systemctl --user enable --now archbooster.timer

echo ""
echo -e "${BOLD}✅ Done!${RESET}"
echo -e "   Run ${YELLOW}archbooster${RESET}         to open the TUI"
echo -e "   Run ${YELLOW}archbooster --scan${RESET}  to check updates in terminal"
echo -e "   The background daemon will check every 4 hours."
