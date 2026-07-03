"""Tests for the notify-send wrapper and its wiring into the daemon."""
import archbooster.core.notify as notify_mod
import archbooster.daemon as daemon_mod
from archbooster.core.config import Config
from archbooster.core.notify import notify_send
from archbooster.core.scanner import Package


def _pkg(name: str, priority: str = "normal") -> Package:
    return Package(name=name, current="1", new="2", source="official", priority=priority)


# --------------------------------------------------------------------------- #
# notify_send
# --------------------------------------------------------------------------- #

def test_notify_send_noop_when_notify_send_missing(monkeypatch):
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: None)
    calls = []
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    result = notify_send("title", "body")

    assert result is False
    assert calls == []


def test_notify_send_builds_expected_command(monkeypatch):
    monkeypatch.setattr(notify_mod.shutil, "which", lambda name: "/usr/bin/notify-send")
    calls = []
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    result = notify_send("3 updates", "1 critical", urgency="critical")

    assert result is True
    (cmd,), kwargs = calls[0]
    assert cmd == [
        "notify-send", "--urgency", "critical",
        "--app-name", "ArchBooster", "3 updates", "1 critical",
    ]
    assert kwargs["check"] is False


# --------------------------------------------------------------------------- #
# daemon wiring
# --------------------------------------------------------------------------- #

def test_daemon_notifies_when_updates_found(monkeypatch):
    monkeypatch.setattr(daemon_mod, "load_config", lambda: Config(notify=True))
    monkeypatch.setattr(
        daemon_mod.BackendRegistry, "scan",
        lambda self, force=False: [_pkg("firefox"), _pkg("linux", "critical")],
    )
    calls = []
    monkeypatch.setattr(daemon_mod, "notify_send", lambda *a, **k: calls.append((a, k)))

    daemon_mod.run_daemon()

    assert len(calls) == 1
    args, _ = calls[0]
    assert args[0] == "2 app updates available"
    assert args[1] == "1 critical"


def test_daemon_respects_notify_false(monkeypatch):
    monkeypatch.setattr(daemon_mod, "load_config", lambda: Config(notify=False))
    monkeypatch.setattr(
        daemon_mod.BackendRegistry, "scan",
        lambda self, force=False: [_pkg("firefox")],
    )
    calls = []
    monkeypatch.setattr(daemon_mod, "notify_send", lambda *a, **k: calls.append((a, k)))

    daemon_mod.run_daemon()

    assert calls == []


def test_daemon_skips_notify_when_no_updates(monkeypatch):
    monkeypatch.setattr(daemon_mod, "load_config", lambda: Config(notify=True))
    monkeypatch.setattr(daemon_mod.BackendRegistry, "scan", lambda self, force=False: [])
    calls = []
    monkeypatch.setattr(daemon_mod, "notify_send", lambda *a, **k: calls.append((a, k)))

    daemon_mod.run_daemon()

    assert calls == []
