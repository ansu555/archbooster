"""
Reads and writes the update history log.
Stored at ~/.local/share/archbooster/history.json
"""
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path.home() / ".local" / "share" / "archbooster" / "history.json"


@dataclass
class HistoryEntry:
    timestamp: str
    package:   str
    old_ver:   str
    new_ver:   str
    status:    str   # "success" | "failed" | "skipped"


class History:
    def load(self) -> list[HistoryEntry]:
        if not HISTORY_FILE.exists():
            return []
        data = json.loads(HISTORY_FILE.read_text())
        return [HistoryEntry(**e) for e in data]

    def record(self, package: str, old_ver: str,
               new_ver: str, status: str) -> None:
        entries = self.load()
        entries.append(HistoryEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            package=package,
            old_ver=old_ver,
            new_ver=new_ver,
            status=status,
        ))
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(
            json.dumps([asdict(e) for e in entries], indent=2)
        )
