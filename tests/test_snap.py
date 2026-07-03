"""Tests for the snap backend: refresh-list parsing, availability detection,
and command building. Snap has no system layer, so unlike PacmanBackend there
is no is_system guardrail to test here."""
import archbooster.core.backends.snap as snap
from archbooster.core.backends.snap import SnapBackend
from archbooster.core.scanner import Package


# --------------------------------------------------------------------------- #
# metadata / availability
# --------------------------------------------------------------------------- #

def test_metadata_has_no_system_layer():
    b = SnapBackend()
    assert b.name == "snap"
    assert b.sources == ("snap",)
    assert b.has_system_layer is False


def test_is_available_true_when_snap_present(monkeypatch):
    monkeypatch.setattr(
        snap.shutil, "which",
        lambda name: "/usr/bin/snap" if name == "snap" else None,
    )
    assert SnapBackend().is_available() is True


def test_is_available_false_without_snap(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", lambda name: None)
    assert SnapBackend().is_available() is False


def test_owns_snap_packages_only():
    b = SnapBackend()
    assert b.owns(Package(name="firefox", current="?", new="2",
                           source="snap", priority="normal")) is True
    assert b.owns(Package(name="firefox", current="?", new="2",
                           source="Flatpak", priority="normal")) is False


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #

def test_parse_line_full():
    pkg = SnapBackend()._parse_line("firefox   118.0.2-2   3358   257MB  mozilla✓    -")
    assert pkg == Package(name="firefox", current="?", new="118.0.2-2",
                           source="snap", priority="normal")


def test_parse_line_skips_header_row():
    assert SnapBackend()._parse_line("Name    Version    Rev    Size   Publisher   Notes") is None


def test_parse_line_skips_up_to_date_message():
    assert SnapBackend()._parse_line("All snaps up to date.") is None


def test_parse_line_skips_malformed_lines():
    assert SnapBackend()._parse_line("") is None
    assert SnapBackend()._parse_line("just-one-field") is None


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #

def test_scan_returns_empty_when_snap_missing(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", lambda name: None)
    assert SnapBackend().scan() == []


def test_scan_parses_subprocess_output_and_skips_header(monkeypatch):
    monkeypatch.setattr(
        snap.shutil, "which",
        lambda name: "/usr/bin/snap" if name == "snap" else None,
    )

    class FakeResult:
        stdout = (
            "Name      Version         Rev    Size   Publisher   Notes\n"
            "core20    20231123        2318   63MB   canonical✓  base\n"
            "firefox   118.0.2-2       3358   257MB  mozilla✓    -\n"
        )

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    pkgs = SnapBackend().scan()
    assert [p.name for p in pkgs] == ["core20", "firefox"]
    assert all(p.source == "snap" for p in pkgs)


def test_scan_returns_empty_when_up_to_date(monkeypatch):
    monkeypatch.setattr(
        snap.shutil, "which",
        lambda name: "/usr/bin/snap" if name == "snap" else None,
    )

    class FakeResult:
        stdout = "All snaps up to date.\n"

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    assert SnapBackend().scan() == []


def test_scan_returns_empty_on_timeout(monkeypatch):
    monkeypatch.setattr(
        snap.shutil, "which",
        lambda name: "/usr/bin/snap" if name == "snap" else None,
    )

    def raise_timeout(*a, **k):
        raise snap.subprocess.TimeoutExpired(cmd="snap", timeout=60)

    monkeypatch.setattr(snap.subprocess, "run", raise_timeout)
    assert SnapBackend().scan() == []


# --------------------------------------------------------------------------- #
# update / full_upgrade
# --------------------------------------------------------------------------- #

def test_update_with_no_names_yields_nothing():
    assert list(SnapBackend().update([])) == []


def test_update_streams_the_built_command(monkeypatch):
    b = SnapBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.update(["firefox", "core20"]))
    assert out == ["ran\n"]
    assert captured["cmd"] == ["sudo", "snap", "refresh", "firefox", "core20"]


def test_full_upgrade_streams_the_built_command(monkeypatch):
    b = SnapBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "full\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.full_upgrade())
    assert out == ["full\n"]
    assert captured["cmd"] == ["sudo", "snap", "refresh"]
