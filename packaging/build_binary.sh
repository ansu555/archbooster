#!/usr/bin/env bash
# Build a single-file archbooster binary with PyInstaller.
# Used by both local dev (`./packaging/build_binary.sh`) and the release CI
# workflow, so both paths produce an identical artifact.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

pip install -e ".[build]"

pyinstaller --onefile --name archbooster --collect-all textual \
    --distpath dist --workpath build/pyinstaller --specpath build \
    archbooster/main.py

./dist/archbooster --help >/dev/null
echo "Built dist/archbooster ($(du -h dist/archbooster | cut -f1))"
