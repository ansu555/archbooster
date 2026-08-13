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


# --------------------------------------------------------------------------- #
# The core ABI layer must never reach `--ignore`.
#
# Regression guard for the bug where CRITICAL_PATTERNS conflated "never
# cherry-pick this" with "hold this back", so glibc/openssl/systemd were
# classified critical, excluded from the selection, and therefore landed in the
# hold list — producing `-Syu --ignore=glibc,openssl,systemd,...` while
# upgrading everything linked against them. That is the dangerous direction of
# a partial upgrade, not the safe one.
# --------------------------------------------------------------------------- #

def _ignore_arg(cmd):
    return next(a for a in cmd if a.startswith("--ignore="))[len("--ignore="):].split(",")


def test_core_libraries_are_stripped_from_the_ignore_list(monkeypatch):
    _only_yay(monkeypatch)
    held = ["glibc", "openssl", "systemd", "sudo", "networkmanager", "linux"]
    ignored = _ignore_arg(Updater()._build_apps_command(held))

    for lib in ("glibc", "openssl", "systemd", "sudo", "networkmanager"):
        assert lib not in ignored, f"{lib} must never be held back"
    assert "linux" in ignored, "the kernel must still be held"


def test_hold_layer_globs_survive_the_core_strip(monkeypatch):
    """"systemd-boot*" sits under the "systemd" ride-along prefix — stripping
    the core layer must not take the bootloader with it."""
    _only_yay(monkeypatch)
    ignored = _ignore_arg(Updater()._build_apps_command(["systemd", "systemd-boot"]))

    assert "systemd" not in ignored
    assert "systemd-boot" in ignored
    assert "systemd-boot*" in ignored          # from SYSTEM_HOLD_GLOBS
    assert "xorg-server*" in ignored           # shares a driver ABI with mesa/nvidia


def test_run_apps_reports_the_list_it_actually_ignores(monkeypatch):
    """The 'Holding back' line must describe the real command, not the caller's
    proposal — otherwise it claims to hold glibc while correctly upgrading it."""
    _only_yay(monkeypatch)
    u = Updater(confirm=False)
    monkeypatch.setattr(u, "_stream", lambda cmd: iter(["ran\n"]))

    out = "".join(u.run_apps(["firefox"], ["glibc", "openssl", "linux"]))

    held_line = next(l for l in out.splitlines() if "Holding back" in l)
    assert "glibc" not in held_line and "openssl" not in held_line
    assert "linux" in held_line
    assert "Core libraries upgrade with your apps" in out


def test_run_refuses_to_cherry_pick_core_libraries(monkeypatch):
    """`-S glibc` against the current sync DB is a partial upgrade too."""
    u = Updater(confirm=False)
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(u, "_stream", fake_stream)
    monkeypatch.setattr(u, "_build_command", lambda names: ["yay", "-S", *names])

    out = list(u.run(["glibc", "openssl", "firefox"]))

    assert any("Skipping system packages" in line for line in out)
    assert captured["cmd"] == ["yay", "-S", "firefox"]
