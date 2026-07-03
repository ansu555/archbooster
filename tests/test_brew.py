"""Tests for the Homebrew backend: outdated-list parsing (formulae + casks),
availability detection, and command building. Homebrew has no system layer,
so unlike PacmanBackend there is no is_system guardrail to test here, and
unlike pacman/apt/dnf its commands never run under sudo."""
import archbooster.core.backends.brew as brew
from archbooster.core.backends.brew import BrewBackend
from archbooster.core.scanner import Package


# --------------------------------------------------------------------------- #
# metadata / availability
# --------------------------------------------------------------------------- #

def test_metadata_has_no_system_layer():
    b = BrewBackend()
    assert b.name == "brew"
    assert b.sources == ("brew",)
    assert b.has_system_layer is False


def test_is_available_true_when_brew_present(monkeypatch):
    monkeypatch.setattr(
        brew.shutil, "which",
        lambda name: "/home/linuxbrew/.linuxbrew/bin/brew" if name == "brew" else None,
    )
    assert BrewBackend().is_available() is True


def test_is_available_false_without_brew(monkeypatch):
    monkeypatch.setattr(brew.shutil, "which", lambda name: None)
    assert BrewBackend().is_available() is False


def test_owns_brew_packages_only():
    b = BrewBackend()
    assert b.owns(Package(name="git", current="1", new="2",
                           source="brew", priority="normal")) is True
    assert b.owns(Package(name="git", current="1", new="2",
                           source="apt", priority="normal")) is False


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #

def test_parse_line_full():
    pkg = BrewBackend()._parse_line("git (2.39.0) < 2.42.0")
    assert pkg == Package(name="git", current="2.39.0", new="2.42.0",
                           source="brew", priority="normal")


def test_parse_line_malformed_returns_none():
    assert BrewBackend()._parse_line("not a valid brew line") is None
    assert BrewBackend()._parse_line("") is None


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #

def test_scan_returns_empty_when_brew_missing(monkeypatch):
    monkeypatch.setattr(brew.shutil, "which", lambda name: None)
    assert BrewBackend().scan() == []


def test_scan_merges_formulae_and_casks(monkeypatch):
    monkeypatch.setattr(
        brew.shutil, "which",
        lambda name: "/usr/bin/brew" if name == "brew" else None,
    )

    def fake_run(cmd, **kwargs):
        class R:
            pass
        r = R()
        if "--cask" in cmd:
            r.stdout = "spotify (1.2.0) < 1.2.1\n"
        else:
            r.stdout = "git (2.39.0) < 2.42.0\nwget (1.21.3) < 1.21.4\n"
        return r

    monkeypatch.setattr(brew.subprocess, "run", fake_run)
    pkgs = BrewBackend().scan()
    assert {p.name for p in pkgs} == {"git", "wget", "spotify"}
    assert all(p.source == "brew" for p in pkgs)


def test_scan_tolerates_cask_call_timing_out(monkeypatch):
    monkeypatch.setattr(
        brew.shutil, "which",
        lambda name: "/usr/bin/brew" if name == "brew" else None,
    )

    def fake_run(cmd, **kwargs):
        if "--cask" in cmd:
            raise brew.subprocess.TimeoutExpired(cmd="brew", timeout=60)
        class R:
            stdout = "git (2.39.0) < 2.42.0\n"
        return R()

    monkeypatch.setattr(brew.subprocess, "run", fake_run)
    pkgs = BrewBackend().scan()
    assert [p.name for p in pkgs] == ["git"]


# --------------------------------------------------------------------------- #
# update / full_upgrade
# --------------------------------------------------------------------------- #

def test_update_with_no_names_yields_nothing():
    assert list(BrewBackend().update([])) == []


def test_update_streams_the_built_command_without_sudo(monkeypatch):
    b = BrewBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.update(["git", "wget"]))
    assert out == ["ran\n"]
    assert captured["cmd"] == ["brew", "upgrade", "git", "wget"]
    assert "sudo" not in captured["cmd"]


def test_full_upgrade_streams_the_built_command(monkeypatch):
    b = BrewBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "full\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.full_upgrade())
    assert out == ["full\n"]
    assert captured["cmd"] == ["brew", "upgrade"]
