"""Tests for the dnf backend: check-update parsing, availability detection,
command building, and its own (Fedora-shaped) system-layer guardrail."""
import archbooster.core.backends.dnf as dnf
from archbooster.core.backends.dnf import DnfBackend
from archbooster.core.scanner import Package


# --------------------------------------------------------------------------- #
# metadata / availability
# --------------------------------------------------------------------------- #

def test_metadata_has_system_layer():
    b = DnfBackend()
    assert b.name == "dnf"
    assert b.sources == ("dnf",)
    assert b.has_system_layer is True


def test_is_available_true_when_dnf_present(monkeypatch):
    monkeypatch.setattr(
        dnf.shutil, "which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )
    assert DnfBackend().is_available() is True


def test_is_available_false_without_dnf(monkeypatch):
    monkeypatch.setattr(dnf.shutil, "which", lambda name: None)
    assert DnfBackend().is_available() is False


def test_owns_dnf_packages_only():
    b = DnfBackend()
    assert b.owns(Package(name="firefox", current="?", new="2",
                           source="dnf", priority="normal")) is True
    assert b.owns(Package(name="firefox", current="?", new="2",
                           source="apt", priority="normal")) is False


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #

def test_parse_line_full():
    pkg = DnfBackend()._parse_line("firefox.x86_64    120.0-1.fc39    updates")
    assert pkg == Package(name="firefox", current="?", new="120.0-1.fc39",
                           source="dnf", priority="normal")


def test_parse_line_dotted_package_name():
    # rsplit on the last "." so a dotted package name (unusual but possible)
    # doesn't get truncated at the wrong point.
    pkg = DnfBackend()._parse_line("python3.11.x86_64   3.11.4-1.fc39   updates")
    assert pkg.name == "python3.11"


def test_parse_line_skips_section_header_and_blank():
    assert DnfBackend()._parse_line("Obsoleting Packages") is None
    assert DnfBackend()._parse_line("") is None
    assert DnfBackend()._parse_line("   ") is None


def test_parse_line_skips_malformed_lines():
    assert DnfBackend()._parse_line("Last metadata expiration check: 0:12:34 ago.") is None


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #

def test_scan_returns_empty_when_dnf_missing(monkeypatch):
    monkeypatch.setattr(dnf.shutil, "which", lambda name: None)
    assert DnfBackend().scan() == []


def test_scan_parses_subprocess_output_with_returncode_100(monkeypatch):
    monkeypatch.setattr(
        dnf.shutil, "which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    class FakeResult:
        returncode = 100  # dnf's "updates available" exit code, not an error
        stdout = (
            "Last metadata expiration check: 0:12:34 ago.\n"
            "\n"
            "firefox.x86_64          120.0-1.fc39          updates\n"
            "kernel-core.x86_64      6.5.6-300.fc39        updates\n"
        )

    monkeypatch.setattr(dnf.subprocess, "run", lambda *a, **k: FakeResult())
    pkgs = DnfBackend().scan()
    assert [p.name for p in pkgs] == ["firefox", "kernel-core"]
    assert all(p.source == "dnf" for p in pkgs)


def test_scan_returns_empty_when_no_updates(monkeypatch):
    monkeypatch.setattr(
        dnf.shutil, "which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    class FakeResult:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(dnf.subprocess, "run", lambda *a, **k: FakeResult())
    assert DnfBackend().scan() == []


def test_scan_returns_empty_on_real_error(monkeypatch):
    monkeypatch.setattr(
        dnf.shutil, "which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    class FakeResult:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(dnf.subprocess, "run", lambda *a, **k: FakeResult())
    assert DnfBackend().scan() == []


def test_scan_returns_empty_on_timeout(monkeypatch):
    monkeypatch.setattr(
        dnf.shutil, "which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    def raise_timeout(*a, **k):
        raise dnf.subprocess.TimeoutExpired(cmd="dnf", timeout=90)

    monkeypatch.setattr(dnf.subprocess, "run", raise_timeout)
    assert DnfBackend().scan() == []


# --------------------------------------------------------------------------- #
# update / full_upgrade / guardrail
# --------------------------------------------------------------------------- #

def test_build_update_command_is_selective_and_noninteractive():
    cmd = DnfBackend()._build_update_command(["firefox", "vlc"])
    assert cmd == ["sudo", "dnf", "upgrade", "-y", "firefox", "vlc"]


def test_build_full_upgrade_command():
    assert DnfBackend()._build_full_upgrade_command() == ["sudo", "dnf", "upgrade", "-y"]


def test_confirm_true_omits_yes_flag():
    b = DnfBackend(confirm=True)
    assert "-y" not in b._build_update_command(["firefox"])
    assert "-y" not in b._build_full_upgrade_command()


def test_update_with_no_names_yields_nothing():
    assert list(DnfBackend().update([])) == []


def test_update_blocks_system_packages(monkeypatch):
    b = DnfBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.update(["kernel-core", "firefox"]))

    assert any("Skipping system packages" in line for line in out)
    assert captured["cmd"] == ["sudo", "dnf", "upgrade", "-y", "firefox"]


def test_update_with_only_system_packages_does_nothing(monkeypatch):
    b = DnfBackend()
    monkeypatch.setattr(b, "_stream", lambda cmd: (_ for _ in ()).throw(
        AssertionError("must not run a command for system-only selection")))
    out = list(b.update(["kernel-core", "systemd"]))
    assert any("Nothing to update" in line for line in out)


def test_full_upgrade_streams_the_built_command(monkeypatch):
    b = DnfBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "full\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.full_upgrade())
    assert out == ["full\n"]
    assert captured["cmd"] == ["sudo", "dnf", "upgrade", "-y"]
