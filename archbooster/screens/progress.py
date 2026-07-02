"""
ProgressScreen — live update output (Phase 2).
Compatible with Textual 0.50+
"""
from __future__ import annotations
import asyncio
import re
from collections.abc import AsyncIterator, Callable, Iterator

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

from archbooster.core.scanner import Package
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.history import History
from archbooster.core.config import load_config
from archbooster.core.sudo_auth import authenticate, is_sudo_cached

STATUS_PENDING = "[dim]⏳ Pending[/dim]"
STATUS_RUNNING = "[yellow]🔄 Updating…[/yellow]"
STATUS_DONE    = "[green]✅ Done[/green]"
STATUS_FAILED  = "[red]❌ Failed[/red]"

# Strip ANSI escape codes from pacman/yay output
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')


def safe_log(log: RichLog, line: str, color: str | None = None) -> None:
    """Write a line to RichLog safely — escapes Rich markup characters."""
    # Remove ANSI codes first
    clean = ANSI_ESCAPE.sub('', line)
    # Escape brackets so Rich doesn't treat file paths as markup tags
    clean = clean.replace('[', '\\[').replace(']', '\\]')
    if color:
        log.write(f"[{color}]{clean}[/{color}]")
    else:
        log.write(clean)


async def stream_lines(
    gen_factory: Callable[[], Iterator[str]],
) -> AsyncIterator[str]:
    """Run a blocking line-generator in a thread, yielding each line as it
    arrives — so the TUI shows update output live instead of all at once after
    the command finishes.

    `gen_factory` is a zero-arg callable returning the blocking iterator (e.g.
    ``lambda: backend.update(["firefox"])`` or a bound ``registry.full_upgrade``).
    Any exception raised while iterating is re-raised on the async side so the
    caller's error handling still applies.
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    done = object()

    def _pump() -> None:
        try:
            for line in gen_factory():
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as exc:  # surfaced to the async side below
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, done)

    loop.run_in_executor(None, _pump)
    while True:
        item = await queue.get()
        if item is done:
            break
        if isinstance(item, BaseException):
            raise item
        yield item


class PackageStatusRow(Static):
    DEFAULT_CSS = """
    PackageStatusRow {
        height: 1;
        padding: 0 2;
        layout: horizontal;
    }
    .ps-name   { width: 1fr; }
    .ps-status { width: 20; }
    """
    def __init__(self, pkg: Package) -> None:
        super().__init__()
        self.pkg = pkg

    def compose(self) -> ComposeResult:
        yield Label(self.pkg.name,  classes="ps-name")
        yield Label(STATUS_PENDING, classes="ps-status", id=f"ps-{self.pkg.name}")

    def set_status(self, status: str) -> None:
        try:
            self.query_one(f"#ps-{self.pkg.name}", Label).update(status)
        except Exception:
            pass


class ProgressScreen(Screen):

    DEFAULT_CSS = """
    ProgressScreen { layout: vertical; }
    #pkg-status-list {
        height: auto;
        max-height: 12;
        border-bottom: solid $surface;
        padding: 1 0;
    }
    #log-header {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        background: $surface;
    }
    #live-log  { height: 1fr; padding: 0 1; }
    #done-bar  {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        border-top: solid $surface;
    }
    #sudo-prompt {
        display: none;
        height: auto;
        padding: 1 2;
        border: solid $warning;
        background: $surface;
        layout: vertical;
    }
    #sudo-prompt.visible { display: block; }
    #sudo-prompt Input { width: 1fr; }
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
    ]

    def __init__(self, packages: list[Package], full_upgrade: bool = False) -> None:
        super().__init__()
        self._packages     = packages
        self._full_upgrade = full_upgrade
        self._history      = History()
        self._completed    = 0
        self._failed       = 0
        self._sudo_authenticated = asyncio.Event()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("Sudo password required to update packages:", id="sudo-prompt-label"),
            Input(placeholder="Password", password=True, id="sudo-password-input"),
            Button("Submit", variant="primary", id="sudo-submit-btn"),
            id="sudo-prompt",
        )
        yield Container(
            *[PackageStatusRow(pkg) for pkg in self._packages],
            id="pkg-status-list",
        )
        yield Label("── Live output ─────────────────────────────────", id="log-header")
        yield RichLog(highlight=False, markup=True, id="live-log")
        yield Label(
            (
                "Full system upgrade (pacman -Syu)…  "
                if self._full_upgrade
                else f"Updating {len(self._packages)} package(s)…  "
            )
            + "Press [ESC] to go back after done.",
            id="done-bar"
        )
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._run_updates(), exclusive=True)

    async def _run_updates(self) -> None:
        log      = self.query_one("#live-log", RichLog)
        registry = BackendRegistry(confirm=load_config().confirm)

        # Pre-flight: ensure sudo is cached so yay/pacman can run without TTY
        cached = await asyncio.get_event_loop().run_in_executor(None, is_sudo_cached)
        if not cached:
            prompt = self.query_one("#sudo-prompt", Container)
            prompt.add_class("visible")
            self.query_one("#sudo-password-input", Input).focus()
            await self._sudo_authenticated.wait()
            prompt.remove_class("visible")

        if self._full_upgrade:
            await self._run_full_upgrade(log, registry)
        else:
            await self._run_selective(log, registry)

        self._finish()

    def _write_line(self, log: RichLog, line: str) -> bool:
        """Write one output line to the log with severity colouring.

        Returns True if the line signals an error, so the caller can mark the
        package failed.
        """
        line = line.rstrip()
        if not line:
            return False
        low = line.lower()
        if "error:" in low or line.startswith("error"):
            safe_log(log, line, "red")
            return True
        if "warning:" in low or line.startswith("warning"):
            safe_log(log, line, "yellow")
        elif line.startswith("::") or line.startswith("==>"):
            safe_log(log, line, "cyan")
        elif "[archbooster] Done" in line:
            safe_log(log, line, "green")
        else:
            safe_log(log, line)
        return False

    async def _run_selective(self, log: RichLog, registry: BackendRegistry) -> None:
        for pkg in self._packages:
            self._set_pkg_status(pkg.name, STATUS_RUNNING)
            # Section header — safe markup, no user content
            log.write(f"\n[bold cyan]── {pkg.name} ──────────────────[/bold cyan]")

            backend = registry.backend_for(pkg)
            success = True
            if backend is None:
                safe_log(log, f"No backend owns {pkg.name} ({pkg.source}); skipped.", "red")
                success = False
            else:
                try:
                    # Route to the owning backend; stream its output line-by-line.
                    async for line in stream_lines(
                        lambda b=backend, p=pkg: b.update([p.name])
                    ):
                        if self._write_line(log, line):
                            success = False
                except Exception as e:
                    safe_log(log, f"Exception: {e}", "red")
                    success = False

            self._history.record(
                package=pkg.name,
                old_ver=pkg.current,
                new_ver=pkg.new,
                status="success" if success else "failed",
            )

            if success:
                self._completed += 1
                self._set_pkg_status(pkg.name, STATUS_DONE)
            else:
                self._failed += 1
                self._set_pkg_status(pkg.name, STATUS_FAILED)

    async def _run_full_upgrade(self, log: RichLog, registry: BackendRegistry) -> None:
        """Stream a single full `-Syu` — the correct path for the system layer."""
        for pkg in self._packages:
            self._set_pkg_status(pkg.name, STATUS_RUNNING)
        log.write("\n[bold cyan]── Full system upgrade (pacman -Syu) ──────────────[/bold cyan]")

        success = True
        try:
            async for line in stream_lines(registry.full_upgrade):
                if self._write_line(log, line):
                    success = False
        except Exception as e:
            safe_log(log, f"Exception: {e}", "red")
            success = False

        # A -Syu updates everything; record the pending system packages we showed.
        for pkg in self._packages:
            self._history.record(
                package=pkg.name,
                old_ver=pkg.current,
                new_ver=pkg.new,
                status="success" if success else "failed",
            )
            if success:
                self._completed += 1
                self._set_pkg_status(pkg.name, STATUS_DONE)
            else:
                self._failed += 1
                self._set_pkg_status(pkg.name, STATUS_FAILED)

    async def _try_sudo_auth(self, password: str) -> None:
        if not password:
            return
        ok = await asyncio.get_event_loop().run_in_executor(
            None, lambda: authenticate(password)
        )
        if ok:
            self.query_one("#sudo-prompt", Container).remove_class("visible")
            self._sudo_authenticated.set()
        else:
            self.notify("Wrong password. Try again.", severity="error")
            self.query_one("#sudo-password-input", Input).focus()

    def _on_sudo_submit(self) -> None:
        inp = self.query_one("#sudo-password-input", Input)
        password = inp.value
        inp.value = ""
        self.run_worker(self._try_sudo_auth(password))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "sudo-password-input":
            self._on_sudo_submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sudo-submit-btn":
            self._on_sudo_submit()

    def _set_pkg_status(self, name: str, status: str) -> None:
        for row in self.query(PackageStatusRow):
            if row.pkg.name == name:
                row.set_status(status)
                break

    def _finish(self) -> None:
        done_bar = self.query_one("#done-bar", Label)
        if self._failed == 0:
            done_bar.update(
                f"[green]✅ All {self._completed} package(s) updated![/green]"
                "   Press [ESC] to go back."
            )
        else:
            done_bar.update(
                f"[green]✅ {self._completed} done[/green]  "
                f"[red]❌ {self._failed} failed[/red]"
                "   Press [ESC] to go back."
            )
        self.app.notify(f"{self._completed} package(s) updated.", severity="information")

    def action_go_back(self) -> None:
        self.app.pop_screen()
        if hasattr(self.app.screen, "refresh_packages"):
            self.app.screen.refresh_packages()