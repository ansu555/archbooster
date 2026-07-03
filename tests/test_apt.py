"""Tests for the apt backend: update-list parsing, availability detection,
command building, and its own (Debian-shaped) system-layer guardrail."""
import archbooster.core.backends.apt as apt
from archbooster.core.backends.apt import AptBackend
from archbooster.core.scanner import Package


# --------------------------------------------------------------------------- #
# metadata / availability
# --------------------------------------------------------------------------- #

def test_metadata_has_system_layer():
    b = AptBackend()
    assert b.name == "apt"
    assert b.sources == ("apt",)
    assert b.has_system_layer is True


def test_is_available_true_when_apt_present(monkeypatch):
    monkeypatch.setattr(
        apt.shutil, "which",
        lambda name: "/usr/bin/apt" if name == "apt" else None,
    )
    assert AptBackend().is_available() is True


def test_is_available_false_without_apt(monkeypatch):
    monkeypatch.setattr(apt.shutil, "which", lambda name: None)
    assert AptBackend().is_available() is False


def test_owns_apt_packages_only():
    b = AptBackend()
    assert b.owns(Package(name="firefox", current="1", new="2",
                           source="apt", priority="normal")) is True
    assert b.owns(Package(name="firefox", current="1", new="2",
                           source="AUR", priority="normal")) is False


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #

def test_parse_line_with_upgradable_from():
    pkg = AptBackend()._parse_line(
        "firefox/jammy-updates,jammy-security 120.0+build2-0ubuntu0.22.04.1 amd64 "
        "[upgradable from: 119.0+build1-0ubuntu0.22.04.1]"
    )
    assert pkg == Package(
        name="firefox", current="119.0+build1-0ubuntu0.22.04.1",
        new="120.0+build2-0ubuntu0.22.04.1", source="apt", priority="normal",
    )


def test_parse_line_without_upgradable_from_uses_placeholder():
    pkg = AptBackend()._parse_line("libc6/jammy-updates 2.35-0ubuntu3.6 amd64")
    assert pkg.current == "?"
    assert pkg.new == "2.35-0ubuntu3.6"


def test_parse_line_malformed_returns_none():
    assert AptBackend()._parse_line("not a valid apt line") is None
    assert AptBackend()._parse_line("") is None


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #

def test_scan_returns_empty_when_apt_missing(monkeypatch):
    monkeypatch.setattr(apt.shutil, "which", lambda name: None)
    assert AptBackend().scan() == []


def test_scan_parses_subprocess_output_and_skips_header(monkeypatch):
    monkeypatch.setattr(
        apt.shutil, "which",
        lambda name: "/usr/bin/apt" if name == "apt" else None,
    )

    class FakeResult:
        stdout = (
            "Listing... Done\n"
            "firefox/jammy-updates 120.0 amd64 [upgradable from: 119.0]\n"
            "libc6/jammy-updates 2.35-0ubuntu3.6 amd64 [upgradable from: 2.35-0ubuntu3.4]\n"
        )

    monkeypatch.setattr(apt.subprocess, "run", lambda *a, **k: FakeResult())
    pkgs = AptBackend().scan()
    assert [p.name for p in pkgs] == ["firefox", "libc6"]
    assert all(p.source == "apt" for p in pkgs)


def test_scan_returns_empty_on_timeout(monkeypatch):
    monkeypatch.setattr(
        apt.shutil, "which",
        lambda name: "/usr/bin/apt" if name == "apt" else None,
    )

    def raise_timeout(*a, **k):
        raise apt.subprocess.TimeoutExpired(cmd="apt", timeout=60)

    monkeypatch.setattr(apt.subprocess, "run", raise_timeout)
    assert AptBackend().scan() == []


# --------------------------------------------------------------------------- #
# update / full_upgrade / guardrail
# --------------------------------------------------------------------------- #

def test_build_update_command_is_selective_and_noninteractive():
    cmd = AptBackend()._build_update_command(["firefox", "vlc"])
    assert cmd == ["sudo", "apt-get", "install", "--only-upgrade", "-y", "firefox", "vlc"]


def test_build_full_upgrade_command():
    assert AptBackend()._build_full_upgrade_command() == \
        ["sudo", "apt-get", "upgrade", "-y"]


def test_confirm_true_omits_yes_flag():
    b = AptBackend(confirm=True)
    assert "-y" not in b._build_update_command(["firefox"])
    assert "-y" not in b._build_full_upgrade_command()


def test_update_with_no_names_yields_nothing():
    assert list(AptBackend().update([])) == []


def test_update_blocks_system_packages(monkeypatch):
    b = AptBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.update(["linux-image-generic", "firefox"]))

    assert any("Skipping system packages" in line for line in out)
    assert captured["cmd"] == ["sudo", "apt-get", "install", "--only-upgrade", "-y", "firefox"]


def test_update_with_only_system_packages_does_nothing(monkeypatch):
    b = AptBackend()
    monkeypatch.setattr(b, "_stream", lambda cmd: (_ for _ in ()).throw(
        AssertionError("must not run a command for system-only selection")))
    out = list(b.update(["linux-image-generic", "systemd"]))
    assert any("Nothing to update" in line for line in out)


def test_full_upgrade_streams_the_built_command(monkeypatch):
    b = AptBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "full\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.full_upgrade())
    assert out == ["full\n"]
    assert captured["cmd"] == ["sudo", "apt-get", "upgrade", "-y"]
