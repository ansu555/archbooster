"""Tests for the CLI commands: --scan (never blank) and --update (the one
command: app layer only, system layer always held)."""
import archbooster.core.config as cfgmod
from archbooster.core.backends.registry import BackendRegistry
from archbooster.core.config import Config
from archbooster.core.scanner import Package
from archbooster.main import _cmd_scan, _cmd_update


def _pkg(name, source="official", priority="normal", status="update"):
    new = "2" if status == "update" else "1"
    return Package(name=name, current="1", new=new, source=source,
                   priority=priority, status=status)


def _wire(monkeypatch, pending, installed, config=None):
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda: config or Config(snapshot_enabled=False))
    monkeypatch.setattr(BackendRegistry, "scan",
                        lambda self, force=False: list(pending))
    monkeypatch.setattr(BackendRegistry, "list_installed",
                        lambda self: list(installed))


# ---- --scan -------------------------------------------------------------- #

def test_scan_with_no_updates_is_never_blank(monkeypatch, capsys):
    _wire(monkeypatch, pending=[],
          installed=[_pkg("bash", status="up-to-date"),
                     _pkg("org.gimp.GIMP", source="Flatpak", status="up-to-date")])
    _cmd_scan()
    out = capsys.readouterr().out
    assert "All up to date" in out
    assert "2 package(s) checked" in out
    assert "Flatpak 1" in out and "official 1" in out


def test_scan_marks_held_system_updates(monkeypatch, capsys):
    _wire(monkeypatch,
          pending=[_pkg("firefox"), _pkg("linux", priority="critical")],
          installed=[_pkg("bash", status="up-to-date")])
    _cmd_scan()
    out = capsys.readouterr().out
    assert "firefox" in out
    assert "[system — held]" in out
    assert "2 update(s) pending" in out
    assert "1 package(s) up to date" in out


def test_scan_all_lists_the_full_inventory(monkeypatch, capsys):
    _wire(monkeypatch, pending=[],
          installed=[_pkg("bash", status="up-to-date")])
    _cmd_scan(list_all=True)
    out = capsys.readouterr().out
    assert "bash" in out and "up to date" in out


def test_scan_excludes_pending_names_from_inventory_count(monkeypatch, capsys):
    # firefox is pending AND installed — it must not be double-counted
    _wire(monkeypatch,
          pending=[_pkg("firefox")],
          installed=[_pkg("firefox", status="up-to-date"),
                     _pkg("bash", status="up-to-date")])
    _cmd_scan()
    out = capsys.readouterr().out
    assert "1 package(s) up to date" in out


# ---- --update -------------------------------------------------------------- #

def _wire_update(monkeypatch, pending, config=None):
    captured = {}

    def fake_update_apps(self, selected, pending_arg, snapshot=None):
        captured["selected"] = [p.name for p in selected]
        captured["pending"]  = [p.name for p in pending_arg]
        yield "[fake] updated\n"

    _wire(monkeypatch, pending=pending, installed=[], config=config)
    monkeypatch.setattr(BackendRegistry, "update_apps", fake_update_apps)
    return captured


def test_update_default_scope_takes_whole_safe_layer(monkeypatch, capsys):
    gimp = _pkg("org.gimp.GIMP", source="Flatpak")
    pending = [_pkg("firefox"), _pkg("ripgrep"), _pkg("linux", priority="critical"), gimp]
    captured = _wire_update(monkeypatch, pending)

    _cmd_update()

    assert sorted(captured["selected"]) == ["firefox", "org.gimp.GIMP", "ripgrep"]
    assert "linux" not in captured["selected"]
    assert "linux" in captured["pending"]        # registry needs it to hold it
    out = capsys.readouterr().out
    assert "Held back (system layer): linux" in out


def test_update_apps_scope_selects_user_facing_apps_only(monkeypatch, capsys):
    import archbooster.core.desktopdb as desktopdb
    monkeypatch.setattr(desktopdb, "gui_package_names",
                        lambda: frozenset({"firefox"}))
    pending = [_pkg("firefox"), _pkg("ripgrep"), _pkg("linux", priority="critical")]
    captured = _wire_update(monkeypatch, pending)

    _cmd_update(scope="apps")

    assert captured["selected"] == ["firefox"]


def test_update_with_nothing_pending_says_so(monkeypatch, capsys):
    _wire_update(monkeypatch, pending=[])
    _cmd_update()
    assert "Nothing to update" in capsys.readouterr().out


def test_update_with_only_system_pending_holds_everything(monkeypatch, capsys):
    captured = _wire_update(monkeypatch, pending=[_pkg("linux", priority="critical")])
    _cmd_update()
    out = capsys.readouterr().out
    assert "selected" not in captured            # update_apps never called
    assert "Held back (system layer): linux" in out
