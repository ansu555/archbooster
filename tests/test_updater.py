"""Tests for command building, the confirm flag, and the system-layer guard."""
import archbooster.core.updater as up
from archbooster.core.updater import Updater


def _only_yay(monkeypatch):
    """Pretend only `yay` is installed, regardless of the test host."""
    monkeypatch.setattr(
        up.shutil, "which",
        lambda name: "/usr/bin/yay" if name == "yay" else None,
    )


def test_noconfirm_toggles_with_confirm_flag():
    assert Updater(confirm=False)._noconfirm() == ["--noconfirm"]
    assert Updater(confirm=True)._noconfirm() == []


def test_build_command_confirm_false_appends_noconfirm(monkeypatch):
    _only_yay(monkeypatch)
    cmd = Updater(confirm=False)._build_command(["firefox"])
    assert cmd == ["yay", "-S", "--needed", "--noconfirm", "firefox"]


def test_build_command_confirm_true_is_interactive(monkeypatch):
    _only_yay(monkeypatch)
    cmd = Updater(confirm=True)._build_command(["firefox"])
    assert cmd == ["yay", "-S", "--needed", "firefox"]
    assert "--noconfirm" not in cmd


def test_selective_update_never_syncs_the_whole_system(monkeypatch):
    # `-S` without `-y` is the guardrail against accidental full syncs.
    _only_yay(monkeypatch)
    cmd = Updater()._build_command(["firefox"])
    assert "-y" not in cmd and "-Syu" not in cmd


def test_full_upgrade_uses_syu(monkeypatch):
    _only_yay(monkeypatch)
    assert Updater(confirm=False)._build_full_upgrade_command() == ["yay", "-Syu", "--noconfirm"]


def test_run_filters_out_system_packages(monkeypatch):
    """A mixed selection must strip system-layer packages before updating."""
    u = Updater(confirm=False)
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(u, "_stream", fake_stream)
    monkeypatch.setattr(u, "_build_command", lambda names: ["yay", "-S", *names])

    out = list(u.run(["linux", "firefox"]))

    assert any("Skipping system packages" in line for line in out)
    assert captured["cmd"] == ["yay", "-S", "firefox"]  # linux was dropped


def test_run_with_only_system_packages_does_nothing(monkeypatch):
    u = Updater(confirm=False)
    # If a command were built/streamed here, that would be the bug.
    monkeypatch.setattr(u, "_stream", lambda cmd: (_ for _ in ()).throw(
        AssertionError("must not run a command for system-only selection")))
    out = list(u.run(["linux", "nvidia"]))
    assert any("Nothing to update" in line for line in out)
