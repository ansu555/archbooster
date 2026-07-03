"""
Root Textual application — owns screen routing and global keybindings.
"""
from textual.app import App
from textual.binding import Binding
from archbooster.screens.dashboard import DashboardScreen
from archbooster.screens.history import HistoryScreen
from archbooster.screens.settings import SettingsScreen
from archbooster.screens.snapshots import SnapshotsScreen


class ArchBoosterApp(App):
    TITLE = "ArchBooster"
    BINDINGS = [
        Binding("q", "quit",          "Quit",    show=True),
        Binding("h", "show_history",  "History", show=True),
        Binding("s", "show_settings", "Settings",show=True),
        Binding("b", "show_snapshots","Snapshots",show=True),
    ]

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())

    def action_show_history(self) -> None:
        self.push_screen(HistoryScreen())

    def action_show_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_show_snapshots(self) -> None:
        self.push_screen(SnapshotsScreen())