"""
ChangelogScreen — "what actually changed before you update" (Phase 6). Shows
whatever `Backend.changelog(pkg)` can produce for the focused dashboard row:
an AUR PKGBUILD diff, a Flatpak OSTree commit log, or an explicit
"not available" message for backends/packages that have nothing to show.
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static

from archbooster.core.backends.base import Backend
from archbooster.core.scanner import Package


class ChangelogScreen(Screen):

    DEFAULT_CSS = """
    ChangelogScreen { layout: vertical; }
    #changelog-header {
        height: 1;
        padding: 0 2;
        background: $surface;
        color: $text-muted;
    }
    #changelog-body {
        height: 1fr;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("q",      "app.pop_screen", "Back", show=False),
    ]

    def __init__(self, package: Package, backend: Backend | None) -> None:
        super().__init__()
        self._package = package
        self._backend = backend

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(
            f"[bold]{self._package.name}[/bold]  "
            f"{self._package.current} → {self._package.new}  "
            f"[dim]({self._package.source})[/dim]",
            id="changelog-header",
        )
        yield VerticalScroll(Static("Loading…", id="changelog-body"))
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._load(), exclusive=True)

    async def _load(self) -> None:
        import asyncio
        body = self.query_one("#changelog-body", Static)
        if self._backend is None:
            body.update("[dim]No backend available for this package.[/dim]")
            return
        text = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._backend.changelog(self._package)
        )
        if not text:
            body.update(
                "[dim]No changelog available for this package/backend.[/dim]"
            )
            return
        # Escape Rich markup characters — a PKGBUILD/log can contain brackets.
        safe = text.replace("[", "\\[").replace("]", "\\]")
        body.update(safe)
