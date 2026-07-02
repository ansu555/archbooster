"""
DashboardScreen — the main update checklist (Phase 2).
Compatible with Textual 0.50+
"""
from __future__ import annotations
import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, Static

from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.categorizer import categorize
from archbooster.core.scanner import Package


PRIORITY_COLOR = {
    "critical": "red",
    "normal":   "yellow",
    "optional": "green",
}


class PackageRow(Static):
    DEFAULT_CSS = """
    PackageRow {
        height: 1;
        padding: 0 1;
        layout: horizontal;
    }
    PackageRow:hover { background: $boost; }
    PackageRow.focused-row { background: $accent 20%; }
    PackageRow.locked { color: $text-muted; }
    .row-check   { width: 3;   color: $success; }
    .row-name    { width: 1fr; }
    .row-version { width: 30;  color: $text-muted; }
    .row-source  { width: 10;  color: $text-muted; }
    """

    def __init__(self, pkg: Package, selected: bool = True,
                 locked: bool = False) -> None:
        super().__init__()
        self.pkg = pkg
        # A locked row is a system-layer package. It can never be selected for a
        # partial (cherry-pick) update — it may only go through a full -Syu.
        self.locked = locked
        self._selected = selected and not locked
        if locked:
            self.add_class("locked")

    def compose(self) -> ComposeResult:
        color = PRIORITY_COLOR[self.pkg.priority]
        yield Label(self._check_glyph(), classes="row-check",
                    id=f"chk-{self.pkg.name}")
        name = f"[{color}]●[/{color}] {self.pkg.name}"
        if self.locked:
            name += "  [dim](system · Full upgrade only)[/dim]"
        yield Label(name, classes="row-name")
        yield Label(f"{self.pkg.current[:13]} → {self.pkg.new[:13]}", classes="row-version")
        yield Label(self.pkg.source, classes="row-source")

    def toggle(self) -> None:
        if self.locked:
            return
        self._selected = not self._selected
        self._refresh_check()

    def select(self, val: bool) -> None:
        if self.locked:
            return
        self._selected = val
        self._refresh_check()

    @property
    def selected(self) -> bool:
        return self._selected and not self.locked

    def _check_glyph(self) -> str:
        if self.locked:
            return "🔒"
        return "✓" if self._selected else " "

    def _refresh_check(self) -> None:
        try:
            self.query_one(f"#chk-{self.pkg.name}", Label).update(self._check_glyph())
        except Exception:
            pass


class SummaryBar(Static):
    DEFAULT_CSS = """
    SummaryBar {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """
    def update_counts(self, packages: list) -> None:
        critical = sum(1 for p in packages if p.priority == "critical")
        normal   = sum(1 for p in packages if p.priority == "normal")
        optional = sum(1 for p in packages if p.priority == "optional")
        parts = []
        if normal:   parts.append(f"[yellow]● {normal} app[/yellow]")
        if optional: parts.append(f"[green]● {optional} optional[/green]")
        if critical:
            parts.append(f"[red]● {critical} system[/red] [dim](press F for full upgrade)[/dim]")
        self.update("   ".join(parts) if parts else "[dim]All packages up to date[/dim]")


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        padding: 0 1;
        border-top: solid $surface;
        color: $text-muted;
    }
    """
    def update_status(self, selected: int, total: int) -> None:
        if total == 0:
            self.update(
                "[dim]No app updates — press [F] for full system upgrade, "
                "[R] to rescan[/dim]"
            )
            return
        col = "green" if selected > 0 else "red"
        self.update(
            f"[{col}]Selected: {selected}/{total}[/{col}]"
            f"   [dim][SPACE] Toggle  [A] All  [N] None  [I] Invert  "
            f"[ENTER] Update apps  [F] Full upgrade  [R] Rescan[/dim]"
        )


class ColumnHeader(Static):
    DEFAULT_CSS = """
    ColumnHeader {
        height: 1;
        padding: 0 1;
        background: $surface;
        layout: horizontal;
        color: $text-muted;
    }
    .col-check   { width: 3; }
    .col-name    { width: 1fr; }
    .col-version { width: 30; }
    .col-source  { width: 10; }
    """
    def compose(self) -> ComposeResult:
        yield Label("✓",       classes="col-check")
        yield Label("Package", classes="col-name")
        yield Label("Version", classes="col-version")
        yield Label("Source",  classes="col-source")


class PackageList(Container):
    DEFAULT_CSS = """
    PackageList {
        overflow-y: auto;
        height: 1fr;
    }
    """


class DashboardScreen(Screen):

    DEFAULT_CSS = """
    DashboardScreen { layout: vertical; }
    """

    BINDINGS = [
        Binding("a",     "select_all",  "All",    show=False),
        Binding("n",     "select_none", "None",   show=False),
        Binding("i",     "invert",       "Invert",       show=False),
        Binding("enter", "update",       "Update apps",  show=False),
        Binding("f",     "full_upgrade", "Full upgrade", show=False),
        Binding("r",     "rescan",       "Rescan",       show=False),
        Binding("j",     "cursor_down", "",       show=False),
        Binding("k",     "cursor_up",   "",       show=False),
        Binding("space", "toggle_row",  "Toggle", show=False),
        Binding("down",  "cursor_down", "",       show=False),
        Binding("up",    "cursor_up",   "",       show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._packages: list = []
        self._cursor: int = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield SummaryBar(id="summary-bar")
        yield ColumnHeader()
        yield PackageList(id="pkg-list")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._start_scan()

    def _start_scan(self, force: bool = False) -> None:
        pkg_list = self.query_one("#pkg-list", PackageList)
        pkg_list.remove_children()
        pkg_list.mount(Label("  Scanning for updates…"))
        self.query_one("#status-bar", StatusBar).update_status(0, 0)
        self.run_worker(self._do_scan(force=force), exclusive=True)

    async def _do_scan(self, force: bool = False) -> None:
        from archbooster.core.config import load_config
        cfg = load_config()

        def _scan() -> list:
            found = [p for p in BackendRegistry().scan(force=force)
                     if p.name not in cfg.ignored]
            return categorize(
                found,
                extra_critical=cfg.extra_critical,
                extra_optional=cfg.extra_optional,
            )
        packages = await asyncio.get_event_loop().run_in_executor(None, _scan)
        # App layer first (actionable), system layer last (locked / full-upgrade only).
        order = {"normal": 0, "optional": 1, "critical": 2}
        packages.sort(key=lambda p: (order[p.priority], p.name))
        self._render_packages(packages)

    def _render_packages(self, packages: list) -> None:
        self._packages = packages
        pkg_list = self.query_one("#pkg-list", PackageList)
        pkg_list.remove_children()
        if not packages:
            pkg_list.mount(Label("  [green]✓[/green]  All packages are up to date!"))
            self.query_one("#summary-bar", SummaryBar).update_counts([])
            self.query_one("#status-bar",  StatusBar).update_status(0, 0)
            return
        for pkg in packages:
            locked = pkg.priority == "critical"
            pkg_list.mount(PackageRow(pkg, selected=not locked, locked=locked))
        self._cursor = 0
        self._highlight_cursor()
        self._refresh_status()
        self.query_one("#summary-bar", SummaryBar).update_counts(packages)

    def _rows(self) -> list:
        return list(self.query(PackageRow))

    def _highlight_cursor(self) -> None:
        rows = self._rows()
        for i, row in enumerate(rows):
            row.set_class(i == self._cursor, "focused-row")
        if rows:
            rows[self._cursor].scroll_visible()

    def action_cursor_down(self) -> None:
        rows = self._rows()
        if rows:
            self._cursor = min(self._cursor + 1, len(rows) - 1)
            self._highlight_cursor()

    def action_cursor_up(self) -> None:
        rows = self._rows()
        if rows:
            self._cursor = max(self._cursor - 1, 0)
            self._highlight_cursor()

    def action_toggle_row(self) -> None:
        rows = self._rows()
        if rows:
            rows[self._cursor].toggle()
            self._refresh_status()

    def action_select_all(self) -> None:
        for row in self._rows(): row.select(True)
        self._refresh_status()

    def action_select_none(self) -> None:
        for row in self._rows(): row.select(False)
        self._refresh_status()

    def action_invert(self) -> None:
        for row in self._rows(): row.toggle()
        self._refresh_status()

    def action_rescan(self) -> None:
        self._start_scan(force=True)

    def refresh_packages(self) -> None:
        self._start_scan()

    def action_update(self) -> None:
        # r.selected already excludes locked (system) rows — this can only ever
        # be an app-layer, partial-upgrade-safe update.
        selected = [r.pkg for r in self._rows() if r.selected]
        if not selected:
            self.notify("No app packages selected!", severity="warning")
            return
        from archbooster.screens.progress import ProgressScreen
        self.app.push_screen(ProgressScreen(selected))

    def action_full_upgrade(self) -> None:
        system_pkgs = [r.pkg for r in self._rows() if r.locked]
        if not system_pkgs:
            self.notify("No system updates pending.", severity="information")
            return
        from archbooster.screens.progress import ProgressScreen
        self.app.push_screen(ProgressScreen(system_pkgs, full_upgrade=True))

    def _refresh_status(self) -> None:
        # Only app-layer rows are selectable, so the counter reflects those.
        selectable = [r for r in self._rows() if not r.locked]
        selected   = sum(1 for r in selectable if r.selected)
        self.query_one("#status-bar", StatusBar).update_status(selected, len(selectable))