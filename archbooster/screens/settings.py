"""
SettingsScreen — view config values (Phase 2).
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label
from textual.containers import Vertical
from archbooster.core.config import load_config, CONFIG_FILE


class SettingsScreen(Screen):

    DEFAULT_CSS = """
    SettingsScreen { layout: vertical; }
    #settings-box {
        margin: 2 4;
        padding: 1 2;
        border: solid $surface;
        height: auto;
    }
    .setting-key   { color: $text-muted; margin-bottom: 1; }
    .setting-value { margin-bottom: 1; }
    #config-path   { margin-top: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("q",      "app.pop_screen", "Back", show=False),
    ]

    def compose(self) -> ComposeResult:
        cfg = load_config()
        profiles = ", ".join(cfg.profiles.keys()) or "none"
        yield Header()
        yield Vertical(
            Label(f"[dim]AUR helper      :[/dim]  {cfg.aur_helper}"),
            Label(f"[dim]Check interval  :[/dim]  {cfg.check_interval}h"),
            Label(f"[dim]Extra critical  :[/dim]  {', '.join(cfg.extra_critical) or 'none'}"),
            Label(f"[dim]Extra optional  :[/dim]  {', '.join(cfg.extra_optional) or 'none'}"),
            Label(f"[dim]Ignored pkgs    :[/dim]  {', '.join(cfg.ignored) or 'none'}"),
            Label(f"[dim]Snapshot        :[/dim]  "
                  f"{'enabled' if cfg.snapshot_enabled else 'disabled'} ({cfg.snapshot_backend})"),
            Label(f"[dim]Profiles        :[/dim]  {profiles}"),
            Label(f"[dim]Auto-update     :[/dim]  "
                  f"{'on — ' + cfg.auto_update_profile if cfg.auto_update and cfg.auto_update_profile else 'off'}"),
            Label(f"\n[dim]Config file: {CONFIG_FILE}[/dim]"),
            id="settings-box",
        )
        yield Footer()