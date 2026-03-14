"""
HistoryScreen — shows all past updates grouped by date (Phase 2).
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, DataTable
from archbooster.core.history import History
from datetime import datetime


class HistoryScreen(Screen):

    DEFAULT_CSS = """
    HistoryScreen { layout: vertical; }
    DataTable     { height: 1fr; }
    #empty        { height: 3; content-align: center middle; color: $text-muted; }
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("q",      "app.pop_screen", "Back", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        entries = History().load()
        if not entries:
            yield Label("No update history yet. Update some packages first!", id="empty")
        else:
            table = DataTable(id="history-table")
            yield table
        yield Footer()

    def on_mount(self) -> None:
        entries = History().load()
        if not entries:
            return
        table = self.query_one("#history-table", DataTable)
        table.add_columns("Time", "Package", "From", "To", "Status")
        for e in reversed(entries):
            # Format timestamp nicely
            try:
                dt   = datetime.fromisoformat(e.timestamp)
                time = dt.strftime("%b %d  %H:%M")
            except Exception:
                time = e.timestamp

            status_label = (
                "[green]✅ success[/green]" if e.status == "success"
                else "[red]❌ failed[/red]"   if e.status == "failed"
                else "[dim]skipped[/dim]"
            )
            table.add_row(time, e.package, e.old_ver, e.new_ver, status_label)