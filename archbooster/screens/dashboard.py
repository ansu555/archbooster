"""
DashboardScreen — the main update checklist (Phase 2, reworked in Phase 7).

Phase 7 (apps-first) additions:
  * Selection is persisted in a set keyed by (source, name), so it survives
    filter changes and re-renders instead of living only inside row widgets.
  * [TAB] cycles a package-type filter (apps / cli / drivers / kernel /
    system / fonts-themes), [S] cycles a source (package-manager) filter.
  * [U] preset selects user-facing apps only.
  * The list is never blank: up-to-date packages are shown (capped) below the
    pending updates, so "no updates" reads as "here's your system, healthy"
    instead of an empty room.
  * [ENTER] routes through the batched apps-first update path
    (`-Syu --ignore=<held>`), passing the full pending list so the progress
    screen can compute holds.

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
from archbooster.core.desktopdb import gui_package_names
from archbooster.core.profiles import matches_profile
from archbooster.core.scanner import Package


PRIORITY_COLOR = {
    "critical": "red",
    "normal":   "yellow",
    "optional": "green",
}

# Display order for source groups — mirrors how a mixed system is actually
# laid out: pacman's two layers first, then app-only backends like Flatpak,
# then the other native distro backends, then the remaining app-only stores.
SOURCE_ORDER = {
    "official": 0, "AUR": 1, "Flatpak": 2, "apt": 3, "dnf": 4, "snap": 5, "brew": 6,
}

# Package-type filter cycle ([TAB]) — user vocabulary, matching
# categorizer.display_category. None = no filter.
CATEGORY_LABELS = {
    "apps":         "Apps",
    "cli":          "CLI & libraries",
    "drivers":      "Drivers & firmware",
    "kernel":       "Kernel",
    "system":       "Core system",
    "fonts-themes": "Fonts & themes",
}
CATEGORY_CYCLE = list(CATEGORY_LABELS)

# Up-to-date rows are plain Labels (1 widget each), but a big Arch install
# still has 1000+ packages — mounting them all would make the TUI crawl.
# Cap the section; the CLI (`archbooster --scan --all`) has the full list.
UPTODATE_CAP = 400


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
        # A locked row is a system-layer package. It can never be selected for
        # the apps-first update — it is always held back (`--ignore`) and only
        # moves via a full upgrade [F].
        self.locked = locked
        self._selected = selected and not locked
        if locked:
            self.add_class("locked")

    def compose(self) -> ComposeResult:
        color = PRIORITY_COLOR[self.pkg.priority]
        # Held directly rather than looked up by a `#chk-{name}` id — package
        # names aren't valid Textual identifiers (Flatpak ids like
        # "org.gimp.GIMP" contain dots).
        self._check_label = Label(self._check_glyph(), classes="row-check")
        yield self._check_label
        name = f"[{color}]●[/{color}] {self.pkg.name}"
        if self.pkg.category:
            name += f"  [dim]({CATEGORY_LABELS.get(self.pkg.category, self.pkg.category)})[/dim]"
        if self.locked:
            name += "  [dim](held · Full upgrade only)[/dim]"
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
        self._check_label.update(self._check_glyph())


class UpToDateRow(Label):
    """One installed-and-current package — a single lightweight widget, not a
    4-label PackageRow, because there can be over a thousand of these."""

    DEFAULT_CSS = """
    UpToDateRow {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(self, pkg: Package) -> None:
        super().__init__(
            f" [green]✓[/green]  {pkg.name}  [dim]{pkg.current[:20]} · {pkg.source}[/dim]"
        )


class SummaryBar(Static):
    DEFAULT_CSS = """
    SummaryBar {
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """
    def update_counts(self, packages: list, uptodate: int = 0,
                      filter_desc: str = "") -> None:
        critical = sum(1 for p in packages if p.priority == "critical")
        normal   = sum(1 for p in packages if p.priority == "normal")
        optional = sum(1 for p in packages if p.priority == "optional")
        parts = []
        if normal:   parts.append(f"[yellow]● {normal} app[/yellow]")
        if optional: parts.append(f"[green]● {optional} optional[/green]")
        if critical:
            parts.append(f"[red]● {critical} system held[/red] [dim](press F for full upgrade)[/dim]")
        if not parts:
            parts.append("[green]✓ All packages up to date[/green]")
        if uptodate:
            parts.append(f"[dim]· {uptodate} up to date[/dim]")
        if filter_desc:
            parts.append(f"[bold]· Filter: {filter_desc}[/bold]")
        self.update("   ".join(parts))


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
                "[R] to rescan, [TAB]/[M] to filter the list[/dim]"
            )
            return
        col = "green" if selected > 0 else "red"
        self.update(
            f"[{col}]Selected: {selected}/{total}[/{col}]"
            f"   [dim][SPACE] Toggle  [U] Apps only  [A] All  [N] None  "
            f"[ENTER] Update  [F] Full upgrade  [TAB] Type  [M] Source  "
            f"[R] Rescan  [C] Changelog  [P] Profile[/dim]"
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


class SourceHeader(Static):
    """Section divider grouping the rows below it by backend (Official/AUR/
    Flatpak), so a mixed system reads as one unified list instead of an
    undifferentiated pile of packages."""

    DEFAULT_CSS = """
    SourceHeader {
        height: 1;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
        text-style: bold;
    }
    """

    def __init__(self, source: str) -> None:
        super().__init__(f"── {source} ──")


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
        Binding("a",     "select_all",   "All",       show=False),
        Binding("n",     "select_none",  "None",      show=False),
        Binding("i",     "invert",       "Invert",    show=False),
        Binding("u",     "select_apps",  "Apps only", show=False),
        Binding("enter", "update",       "Update apps",  show=False),
        Binding("f",     "full_upgrade", "Full upgrade", show=False),
        Binding("r",     "rescan",       "Rescan",       show=False),
        Binding("c",     "show_changelog", "Changelog",  show=False),
        Binding("p",     "cycle_profile",  "Profile",    show=False),
        Binding("tab",   "cycle_category", "Type filter",   show=False),
        # `s` is Settings at app level, so the source/package-manager filter
        # rides on `m` (as in "manager").
        Binding("m",     "cycle_source",   "Source filter", show=False),
        Binding("j",     "cursor_down", "",       show=False),
        Binding("k",     "cursor_up",   "",       show=False),
        Binding("space", "toggle_row",  "Toggle", show=False),
        Binding("down",  "cursor_down", "",       show=False),
        Binding("up",    "cursor_up",   "",       show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._packages:  list[Package] = []   # pending updates
        self._installed: list[Package] = []   # up-to-date inventory
        # Selection lives here, not in the row widgets, so it survives filter
        # re-renders; keyed (source, name) since the same name can exist in
        # two backends (e.g. an "openssl" formula in brew and in pacman).
        self._selected: set[tuple[str, str]] = set()
        self._cursor: int = 0
        self._category_filter: str | None = None
        self._source_filter:   str | None = None
        self._profile_patterns: dict[str, list[str]] = {}
        self._active_profile_idx: int = -1  # -1 = no profile filter active
        # Missing-tooling toasts fire on the first scan only — [r] re-scans
        # often, and repeating the same advisory every time is nagging.
        self._advised: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield SummaryBar(id="summary-bar")
        yield ColumnHeader()
        yield PackageList(id="pkg-list")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._start_scan()

    # ---- scanning --------------------------------------------------- #

    def _start_scan(self, force: bool = False) -> None:
        pkg_list = self.query_one("#pkg-list", PackageList)
        pkg_list.remove_children()
        pkg_list.mount(Label("  Scanning for updates…"))
        self.query_one("#status-bar", StatusBar).update_status(0, 0)
        self.run_worker(self._do_scan(force=force), exclusive=True)

    async def _do_scan(self, force: bool = False) -> None:
        from archbooster.core.config import load_config
        cfg = load_config()
        self._profile_patterns = cfg.profiles
        self._active_profile_idx = -1

        def _scan() -> tuple[list[Package], list[Package]]:
            registry = BackendRegistry()
            gui = gui_package_names()
            found = [p for p in registry.scan(force=force)
                     if p.name not in cfg.ignored]
            found = categorize(
                found,
                extra_critical=cfg.extra_critical,
                extra_optional=cfg.extra_optional,
                gui_packages=gui,
            )
            pending_keys = {(p.source, p.name) for p in found}
            installed = [
                p for p in registry.list_installed()
                if p.name not in cfg.ignored
                and (p.source, p.name) not in pending_keys
            ]
            installed = categorize(
                installed,
                extra_critical=cfg.extra_critical,
                extra_optional=cfg.extra_optional,
                gui_packages=gui,
            )
            return found, installed

        packages, installed = await asyncio.get_event_loop().run_in_executor(None, _scan)
        # Group by source (Official / AUR / Flatpak) so a mixed system reads
        # as one unified list; within each group, app layer first (actionable),
        # system layer last (held / full-upgrade only).
        order = {"normal": 0, "optional": 1, "critical": 2}
        packages.sort(
            key=lambda p: (SOURCE_ORDER.get(p.source, 99), order[p.priority], p.name)
        )
        installed.sort(key=lambda p: (SOURCE_ORDER.get(p.source, 99), p.name))
        self._packages  = packages
        self._installed = installed
        # Default selection: the whole safe (non-system) layer — one [ENTER]
        # is the one command. [U] narrows it to user-facing apps only.
        self._selected = {
            (p.source, p.name) for p in packages if p.priority != "critical"
        }
        self._render_list()
        self._notify_advisories()

    def _notify_advisories(self) -> None:
        """Toast any missing optional tooling once per scan.

        The scan still works without it — this is the difference between a
        fresh package list and a possibly-stale one, so it warns rather than
        blocks, and never repeats within a session.
        """
        if self._advised:
            return
        self._advised = True
        from archbooster.core.preflight import advisories

        for advisory in advisories():
            self.notify(
                f"{advisory.tool} not found — {advisory.impact}. "
                f"Fix: {advisory.fix}",
                severity="warning",
                timeout=12,
            )

    # ---- rendering --------------------------------------------------- #

    def _visible(self, packages: list[Package]) -> list[Package]:
        result = packages
        if self._category_filter:
            result = [p for p in result if p.category == self._category_filter]
        if self._source_filter:
            result = [p for p in result if p.source == self._source_filter]
        return result

    def _filter_desc(self) -> str:
        parts = []
        if self._category_filter:
            parts.append(CATEGORY_LABELS.get(self._category_filter, self._category_filter))
        if self._source_filter:
            parts.append(self._source_filter)
        return " · ".join(parts)

    def _render_list(self) -> None:
        pkg_list = self.query_one("#pkg-list", PackageList)
        pkg_list.remove_children()

        updates   = self._visible(self._packages)
        uptodate  = self._visible(self._installed)

        if not updates and not uptodate:
            hint = " matching this filter" if self._filter_desc() else ""
            pkg_list.mount(Label(f"  [dim]No packages{hint}.[/dim]"))
        last_source = None
        for pkg in updates:
            if pkg.source != last_source:
                pkg_list.mount(SourceHeader(pkg.source))
                last_source = pkg.source
            locked = pkg.priority == "critical"
            pkg_list.mount(PackageRow(
                pkg,
                selected=(pkg.source, pkg.name) in self._selected,
                locked=locked,
            ))
        if uptodate:
            pkg_list.mount(SourceHeader(f"Up to date ({len(uptodate)})"))
            for pkg in uptodate[:UPTODATE_CAP]:
                pkg_list.mount(UpToDateRow(pkg))
            if len(uptodate) > UPTODATE_CAP:
                pkg_list.mount(Label(
                    f"  [dim]… and {len(uptodate) - UPTODATE_CAP} more — "
                    f"run `archbooster --scan --all` for the full list[/dim]"
                ))

        self._cursor = 0
        self._highlight_cursor()
        self._refresh_status()
        self.query_one("#summary-bar", SummaryBar).update_counts(
            self._packages, uptodate=len(self._installed),
            filter_desc=self._filter_desc(),
        )

    # ---- cursor / rows ----------------------------------------------- #

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

    # ---- selection ---------------------------------------------------- #

    def _sync_selection(self, row) -> None:
        key = (row.pkg.source, row.pkg.name)
        if row.selected:
            self._selected.add(key)
        else:
            self._selected.discard(key)

    def action_toggle_row(self) -> None:
        rows = self._rows()
        if rows:
            row = rows[self._cursor]
            row.toggle()
            self._sync_selection(row)
            self._refresh_status()

    def action_select_all(self) -> None:
        for row in self._rows():
            row.select(True)
            self._sync_selection(row)
        self._refresh_status()

    def action_select_none(self) -> None:
        for row in self._rows():
            row.select(False)
            self._sync_selection(row)
        self._refresh_status()

    def action_invert(self) -> None:
        for row in self._rows():
            row.toggle()
            self._sync_selection(row)
        self._refresh_status()

    def action_select_apps(self) -> None:
        """[U] preset — the literal 'user-facing apps only' selection. Applies
        to all pending updates, not just the currently visible (filtered) rows."""
        self._selected = {
            (p.source, p.name) for p in self._packages
            if p.priority != "critical" and p.category == "apps"
        }
        for row in self._rows():
            row.select((row.pkg.source, row.pkg.name) in self._selected)
        self.notify(f"Selected {len(self._selected)} user-facing app(s)",
                    severity="information")
        self._refresh_status()

    # ---- filters ------------------------------------------------------ #

    def _present_categories(self) -> list[str]:
        present = {p.category for p in self._packages} | {p.category for p in self._installed}
        return [c for c in CATEGORY_CYCLE if c in present]

    def _present_sources(self) -> list[str]:
        present = {p.source for p in self._packages} | {p.source for p in self._installed}
        return sorted(present, key=lambda s: SOURCE_ORDER.get(s, 99))

    @staticmethod
    def _cycle(current, options):
        """None → options[0] → options[1] → … → None."""
        if not options:
            return None
        if current not in options:
            return options[0]
        idx = options.index(current) + 1
        return options[idx] if idx < len(options) else None

    def action_cycle_category(self) -> None:
        self._category_filter = self._cycle(self._category_filter, self._present_categories())
        label = CATEGORY_LABELS.get(self._category_filter, "All types")
        self.notify(f"Type filter: {label if self._category_filter else 'All types'}",
                    severity="information")
        self._render_list()

    def action_cycle_source(self) -> None:
        self._source_filter = self._cycle(self._source_filter, self._present_sources())
        self.notify(f"Source filter: {self._source_filter or 'All sources'}",
                    severity="information")
        self._render_list()

    # ---- actions ------------------------------------------------------ #

    def action_rescan(self) -> None:
        self._start_scan(force=True)

    def refresh_packages(self) -> None:
        self._start_scan()

    def action_update(self) -> None:
        # Selection is taken from the persisted set (hidden-but-selected rows
        # still count) and re-filtered against the system layer, so this can
        # only ever be an app-layer, hold-the-system update.
        selected = [
            p for p in self._packages
            if (p.source, p.name) in self._selected and p.priority != "critical"
        ]
        if not selected:
            self.notify("No app packages selected!", severity="warning")
            return
        from archbooster.screens.progress import ProgressScreen
        self.app.push_screen(ProgressScreen(selected, pending=self._packages))

    def action_cycle_profile(self) -> None:
        """Cycle through configured [profiles] entries, auto-selecting the
        packages each one matches (never a system package). Cycling past the
        last profile clears the filter back to "everything selected"."""
        names = list(self._profile_patterns.keys())
        if not names:
            self.notify(
                "No profiles configured — add a [profiles] entry in config.toml",
                severity="warning",
            )
            return
        self._active_profile_idx += 1
        if self._active_profile_idx >= len(names):
            self._active_profile_idx = -1
            self._selected = {
                (p.source, p.name) for p in self._packages if p.priority != "critical"
            }
            self.notify("Profile filter cleared — all apps selected", severity="information")
        else:
            name = names[self._active_profile_idx]
            patterns = self._profile_patterns[name]
            self._selected = {
                (p.source, p.name) for p in self._packages
                if p.priority != "critical" and matches_profile(p.name, patterns)
            }
            self.notify(f"Profile: {name}", severity="information")
        for row in self._rows():
            row.select((row.pkg.source, row.pkg.name) in self._selected)
        self._refresh_status()

    def action_show_changelog(self) -> None:
        rows = self._rows()
        if not rows:
            return
        pkg = rows[self._cursor].pkg
        backend = BackendRegistry().backend_for(pkg)
        from archbooster.screens.changelog import ChangelogScreen
        self.app.push_screen(ChangelogScreen(pkg, backend))

    def action_full_upgrade(self) -> None:
        system_pkgs = [p for p in self._packages if p.priority == "critical"]
        if not system_pkgs:
            self.notify("No system updates pending.", severity="information")
            return
        from archbooster.screens.progress import ProgressScreen
        self.app.push_screen(ProgressScreen(system_pkgs, full_upgrade=True))

    def _refresh_status(self) -> None:
        # Counter over the whole app layer (not just visible rows), since the
        # selection set is global across filters.
        selectable = [p for p in self._packages if p.priority != "critical"]
        selected   = sum(
            1 for p in selectable if (p.source, p.name) in self._selected
        )
        self.query_one("#status-bar", StatusBar).update_status(selected, len(selectable))
