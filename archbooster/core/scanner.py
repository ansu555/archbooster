"""
Fetches available updates from:
  - checkupdates  (official repos, no root needed)
  - yay -Qu       (AUR packages)

Returns a list of Package dataclasses.
Results are cached to ~/.cache/archbooster/pending.json
for fast TUI startup after a daemon check.
"""
import json
import subprocess
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

CACHE_FILE = Path.home() / ".cache" / "archbooster" / "pending.json"
CACHE_TTL  = timedelta(hours=1)


@dataclass
class Package:
    name:     str
    current:  str
    new:      str
    source:   str    # "official" | "AUR"
    priority: str    # "critical" | "normal" | "optional"  (set by categorizer)


class Scanner:
    def fetch(self, force: bool = False) -> list[Package]:
        """Return cached results if fresh, otherwise re-scan."""
        if not force and self._cache_is_fresh():
            return self._load_cache()
        packages = self._scan_official() + self._scan_aur()
        self._save_cache(packages)
        return packages

    # ------------------------------------------------------------------ #

    def _scan_official(self) -> list[Package]:
        """Run checkupdates (pacman-contrib). Safe — no root needed."""
        if not shutil.which("checkupdates"):
            return []
        try:
            result = subprocess.run(
                ["checkupdates"],
                capture_output=True, text=True, timeout=60
            )
            # exit code 2 = no updates (not an error)
            return [self._parse_line(line, "official")
                    for line in result.stdout.strip().splitlines() if line]
        except subprocess.TimeoutExpired:
            return []

    def _scan_aur(self) -> list[Package]:
        """Run yay/paru -Qu for AUR-only updates."""
        helper = self._detect_aur_helper()
        if not helper:
            return []
        try:
            result = subprocess.run(
                [helper, "-Qu", "--aur"],
                capture_output=True, text=True, timeout=90
            )
            return [self._parse_line(line, "AUR")
                    for line in result.stdout.strip().splitlines() if line]
        except subprocess.TimeoutExpired:
            return []

    def _parse_line(self, line: str, source: str) -> Package:
        # Format: <name> <current> -> <new>
        parts = line.split()
        return Package(
            name=parts[0],
            current=parts[1] if len(parts) > 1 else "?",
            new=parts[3]     if len(parts) > 3 else "?",
            source=source,
            priority="normal",
        )

    def _detect_aur_helper(self) -> str | None:
        for h in ("yay", "paru"):
            if shutil.which(h):
                return h
        return None

    def _cache_is_fresh(self) -> bool:
        if not CACHE_FILE.exists():
            return False
        mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
        return datetime.now() - mtime < CACHE_TTL

    def _load_cache(self) -> list[Package]:
        data = json.loads(CACHE_FILE.read_text())
        return [Package(**p) for p in data]

    def _save_cache(self, packages: list[Package]) -> None:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps([asdict(p) for p in packages], indent=2))
