"""
SnapshotsScreen — lists filesystem snapshots (snapper/timeshift) and lets the
user roll back to one. This is the other half of Phase 6's "killer feature":
a full system upgrade takes a snapshot automatically (see
`core.snapshot.SnapshotManager` wired into `ProgressScreen`); this screen is
the manual undo button.

Rollback reverts host state and is hard to reverse — it always requires an
explicit second keypress (`R` to arm, `Y` to confirm) rather than firing on a
single keystroke, and the confirmation is a screen-native label, not an OS
dialog (OS-level modals block the whole TUI process).
"""
from __future__ import annotations
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, DataTable

from archbooster.core.config import load_config
from archbooster.core.snapshot import SnapshotManager


class SnapshotsScreen(Screen):

    DEFAULT_CSS = """
    SnapshotsScreen { layout: vertical; }
    DataTable      { height: 1fr; }
    #empty         { height: 3; content-align: center middle; color: $text-muted; }
    #snap-status   {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        border-top: solid $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back",       "Back",          show=True),
        Binding("q",      "go_back",       "Back",          show=False),
        Binding("r",      "arm_rollback",  "Rollback",      show=True),
        Binding("y",      "confirm_rollback", "Confirm",    show=False),
        Binding("j",      "cursor_down",   "",              show=False),
        Binding("k",      "cursor_up",     "",              show=False),
        Binding("down",   "cursor_down",   "",              show=False),
        Binding("up",     "cursor_up",     "",              show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        cfg = load_config()
        self._manager = SnapshotManager(cfg.snapshot_backend)
        self._snapshots: list = []
        self._armed = False

    def compose(self) -> ComposeResult:
        yield Header()
        if not self._manager.is_available():
            yield Label(
                "No snapshot tool found (install snapper or timeshift to enable "
                "pre-upgrade snapshots and rollback).",
                id="empty",
            )
        else:
            yield DataTable(id="snapshot-table")
        yield Label("", id="snap-status")
        yield Footer()

    def on_mount(self) -> None:
        if not self._manager.is_available():
            return
        table = self.query_one("#snapshot-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("ID", "Date", "Description", "Backend")
        self._snapshots = self._manager.list()
        if not self._snapshots:
            self._set_status("No snapshots found yet.")
            return
        for snap in self._snapshots:
            table.add_row(snap.id, snap.date, snap.description, snap.backend)
        self._set_status(
            f"{len(self._snapshots)} snapshot(s)   [dim][R] Rollback selected  [Y] Confirm[/dim]"
        )

    def on_key(self, event: events.Key) -> None:
        # While a rollback is armed, any key other than 'y' cancels it instead
        # of doing whatever it would normally do (including navigating away) —
        # a rollback confirmation should never be one accidental keystroke away.
        if self._armed and event.key != "y":
            self._armed = False
            self._set_status("Rollback cancelled.")
            event.stop()
            event.prevent_default()

    def action_cursor_down(self) -> None:
        try:
            self.query_one("#snapshot-table", DataTable).action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        try:
            self.query_one("#snapshot-table", DataTable).action_cursor_up()
        except Exception:
            pass

    def action_arm_rollback(self) -> None:
        if not self._snapshots:
            return
        self._armed = True
        snap = self._selected_snapshot()
        if snap is None:
            return
        self._set_status(
            f"[yellow]Roll back to {snap.id} ({snap.description or 'no description'})? "
            f"Press [Y] to confirm, any other key to cancel.[/yellow]"
        )

    def action_confirm_rollback(self) -> None:
        if not self._armed:
            return
        self._armed = False
        snap = self._selected_snapshot()
        if snap is None:
            return
        self._set_status(f"[yellow]Rolling back to {snap.id}...[/yellow]")
        self.run_worker(self._do_rollback(snap.id), exclusive=True)

    async def _do_rollback(self, snapshot_id: str) -> None:
        import asyncio
        lines = await asyncio.get_event_loop().run_in_executor(
            None, lambda: list(self._manager.rollback(snapshot_id))
        )
        output = "".join(lines).strip()
        self._set_status(f"[green]Done.[/green] {output[-200:]}")

    def _selected_snapshot(self):
        try:
            table = self.query_one("#snapshot-table", DataTable)
        except Exception:
            return None
        if not self._snapshots:
            return None
        row = min(table.cursor_row, len(self._snapshots) - 1)
        return self._snapshots[row]

    def _set_status(self, text: str) -> None:
        self.query_one("#snap-status", Label).update(text)

    def action_go_back(self) -> None:
        # If a rollback is armed, on_key() already intercepted this keypress
        # to cancel it instead — this only runs when nothing was armed.
        self.app.pop_screen()
