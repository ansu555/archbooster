"""Tests for the Flatpak backend: update-list parsing, availability
detection, and command building. Flatpak has no system layer, so unlike
PacmanBackend there is no is_system guardrail to test here."""
import archbooster.core.backends.flatpak as fp
from archbooster.core.backends.flatpak import FlatpakBackend
from archbooster.core.scanner import Package


# --------------------------------------------------------------------------- #
# metadata / availability
# --------------------------------------------------------------------------- #

def test_metadata_has_no_system_layer():
    b = FlatpakBackend()
    assert b.name == "flatpak"
    assert b.sources == ("Flatpak",)
    assert b.has_system_layer is False


def test_is_available_true_when_flatpak_present(monkeypatch):
    monkeypatch.setattr(
        fp.shutil, "which",
        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None,
    )
    assert FlatpakBackend().is_available() is True


def test_is_available_false_without_flatpak(monkeypatch):
    monkeypatch.setattr(fp.shutil, "which", lambda name: None)
    assert FlatpakBackend().is_available() is False


def test_owns_flatpak_packages_only():
    b = FlatpakBackend()
    assert b.owns(Package(name="org.gimp.GIMP", current="1", new="2",
                           source="Flatpak", priority="normal")) is True
    assert b.owns(Package(name="firefox", current="1", new="2",
                           source="AUR", priority="normal")) is False


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #

def test_parse_line_full():
    pkg = FlatpakBackend()._parse_line("org.gimp.GIMP\t2.10.36")
    assert pkg == Package(name="org.gimp.GIMP", current="?", new="2.10.36",
                           source="Flatpak", priority="normal")


def test_parse_line_missing_version_uses_placeholder():
    pkg = FlatpakBackend()._parse_line("org.gimp.GIMP\t")
    assert pkg.new == "?"


def test_parse_line_single_field_uses_placeholder():
    # Malformed / truncated line must not raise.
    pkg = FlatpakBackend()._parse_line("org.gimp.GIMP")
    assert pkg.name == "org.gimp.GIMP"
    assert pkg.new == "?"


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #

def test_scan_returns_empty_when_flatpak_missing(monkeypatch):
    monkeypatch.setattr(fp.shutil, "which", lambda name: None)
    assert FlatpakBackend().scan() == []


def test_scan_parses_subprocess_output(monkeypatch):
    monkeypatch.setattr(
        fp.shutil, "which",
        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None,
    )

    class FakeResult:
        stdout = "org.gimp.GIMP\t2.10.36\norg.mozilla.firefox\t120.0\n"

    monkeypatch.setattr(fp.subprocess, "run", lambda *a, **k: FakeResult())
    pkgs = FlatpakBackend().scan()
    assert [p.name for p in pkgs] == ["org.gimp.GIMP", "org.mozilla.firefox"]
    assert all(p.source == "Flatpak" for p in pkgs)


def test_scan_returns_empty_on_timeout(monkeypatch):
    monkeypatch.setattr(
        fp.shutil, "which",
        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None,
    )

    def raise_timeout(*a, **k):
        raise fp.subprocess.TimeoutExpired(cmd="flatpak", timeout=60)

    monkeypatch.setattr(fp.subprocess, "run", raise_timeout)
    assert FlatpakBackend().scan() == []


# --------------------------------------------------------------------------- #
# update / full_upgrade
# --------------------------------------------------------------------------- #

def test_build_update_command_is_selective_and_noninteractive():
    cmd = FlatpakBackend()._build_update_command(
        ["org.gimp.GIMP", "org.mozilla.firefox"])
    assert cmd == ["flatpak", "update", "-y",
                   "org.gimp.GIMP", "org.mozilla.firefox"]


def test_build_full_upgrade_command_updates_everything():
    assert FlatpakBackend()._build_full_upgrade_command() == \
        ["flatpak", "update", "-y"]


def test_confirm_true_omits_yes_flag():
    b = FlatpakBackend(confirm=True)
    assert "-y" not in b._build_update_command(["org.gimp.GIMP"])
    assert "-y" not in b._build_full_upgrade_command()


def test_confirm_false_is_default_and_noninteractive():
    b = FlatpakBackend()
    assert b.confirm is False
    assert "-y" in b._build_full_upgrade_command()


def test_update_with_no_names_yields_nothing():
    assert list(FlatpakBackend().update([])) == []


def test_update_streams_the_built_command(monkeypatch):
    b = FlatpakBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "ran\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.update(["org.gimp.GIMP"]))
    assert out == ["ran\n"]
    assert captured["cmd"] == ["flatpak", "update", "-y", "org.gimp.GIMP"]


def test_full_upgrade_streams_the_built_command(monkeypatch):
    b = FlatpakBackend()
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "full\n"

    monkeypatch.setattr(b, "_stream", fake_stream)
    out = list(b.full_upgrade())
    assert out == ["full\n"]
    assert captured["cmd"] == ["flatpak", "update", "-y"]


# --------------------------------------------------------------------------- #
# changelog
# --------------------------------------------------------------------------- #

def _gimp_pkg() -> Package:
    return Package(name="org.gimp.GIMP", current="2.10.34", new="2.10.36",
                   source="Flatpak", priority="normal")


def test_changelog_none_without_flatpak(monkeypatch):
    monkeypatch.setattr(fp.shutil, "which", lambda name: None)
    assert FlatpakBackend().changelog(_gimp_pkg()) is None


def test_changelog_tries_remotes_until_one_has_a_log(monkeypatch):
    monkeypatch.setattr(
        fp.shutil, "which",
        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None,
    )

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = ""
        if cmd[:2] == ["flatpak", "remotes"]:
            r = R(); r.stdout = "flathub\nfedora\n"; return r
        if cmd[:3] == ["flatpak", "remote-info", "--log"] and cmd[3] == "flathub":
            r = R(); r.returncode = 1; r.stdout = ""; return r
        if cmd[:3] == ["flatpak", "remote-info", "--log"] and cmd[3] == "fedora":
            r = R(); r.stdout = "commit abc123\n    Fixed a crash\n"; return r
        return R()

    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    log = FlatpakBackend().changelog(_gimp_pkg())
    assert log == "commit abc123\n    Fixed a crash"
    # Tried flathub first (empty/failed), then fell through to fedora.
    assert calls[1][3] == "flathub"
    assert calls[2][3] == "fedora"


def test_changelog_returns_none_when_no_remote_has_a_log(monkeypatch):
    monkeypatch.setattr(
        fp.shutil, "which",
        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None,
    )

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1
            stdout = "flathub\n" if cmd[:2] == ["flatpak", "remotes"] else ""
        return R()

    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    assert FlatpakBackend().changelog(_gimp_pkg()) is None


def test_changelog_returns_none_on_remotes_timeout(monkeypatch):
    monkeypatch.setattr(
        fp.shutil, "which",
        lambda name: "/usr/bin/flatpak" if name == "flatpak" else None,
    )

    def raise_timeout(*a, **k):
        raise fp.subprocess.TimeoutExpired(cmd="flatpak", timeout=15)

    monkeypatch.setattr(fp.subprocess, "run", raise_timeout)
    assert FlatpakBackend().changelog(_gimp_pkg()) is None
