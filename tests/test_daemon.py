"""Tests for the daemon's opt-in auto-update: profile matching, the
critical/system hard-exclusion, and success/failure history recording."""
import archbooster.core.history as historymod
import archbooster.daemon as daemon
from archbooster.core.config import Config
from archbooster.core.scanner import Package


def _pkg(name: str, priority: str = "normal") -> Package:
    return Package(name=name, current="1", new="2", source="official", priority=priority)


class FakeRegistry:
    def __init__(self, lines=None):
        self._lines = lines if lines is not None else ["ok\n"]
        self.updated_with: list | None = None

    def update(self, packages):
        self.updated_with = list(packages)
        yield from self._lines


def _cfg(**overrides) -> Config:
    cfg = Config()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_auto_update_disabled_by_default_is_a_noop():
    cfg = _cfg(auto_update=False, auto_update_profile="browsers",
               profiles={"browsers": ["firefox"]})
    registry = FakeRegistry()
    result = daemon._run_auto_update(cfg, registry, [_pkg("firefox")])
    assert result == []
    assert registry.updated_with is None


def test_auto_update_enabled_without_profile_name_is_a_noop():
    cfg = _cfg(auto_update=True, auto_update_profile="",
               profiles={"browsers": ["firefox"]})
    registry = FakeRegistry()
    result = daemon._run_auto_update(cfg, registry, [_pkg("firefox")])
    assert result == []
    assert registry.updated_with is None


def test_auto_update_profile_not_defined_is_a_noop():
    cfg = _cfg(auto_update=True, auto_update_profile="ghost", profiles={})
    registry = FakeRegistry()
    result = daemon._run_auto_update(cfg, registry, [_pkg("firefox")])
    assert result == []
    assert registry.updated_with is None


def test_auto_update_matches_only_profile_patterns(monkeypatch, tmp_path):
    monkeypatch.setattr(historymod, "HISTORY_FILE", tmp_path / "history.json")
    cfg = _cfg(auto_update=True, auto_update_profile="browsers",
               profiles={"browsers": ["firefox", "*chrom*"]})
    packages = [_pkg("firefox"), _pkg("vlc"), _pkg("chromium")]
    registry = FakeRegistry()

    result = daemon._run_auto_update(cfg, registry, packages)

    assert {p.name for p in result} == {"firefox", "chromium"}
    assert {p.name for p in registry.updated_with} == {"firefox", "chromium"}


def test_auto_update_never_touches_critical_packages_even_if_matched(monkeypatch, tmp_path):
    monkeypatch.setattr(historymod, "HISTORY_FILE", tmp_path / "history.json")
    # Wildcard profile that would match everything, including a critical pkg —
    # the hard exclusion must still keep it out.
    cfg = _cfg(auto_update=True, auto_update_profile="everything",
               profiles={"everything": ["*"]})
    packages = [_pkg("firefox"), _pkg("linux", priority="critical")]
    registry = FakeRegistry()

    result = daemon._run_auto_update(cfg, registry, packages)

    assert "linux" not in {p.name for p in result}
    assert "linux" not in {p.name for p in registry.updated_with}
    assert "firefox" in {p.name for p in registry.updated_with}


def test_auto_update_records_history_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(historymod, "HISTORY_FILE", tmp_path / "history.json")
    cfg = _cfg(auto_update=True, auto_update_profile="browsers",
               profiles={"browsers": ["firefox"]})
    registry = FakeRegistry(lines=["Update complete.\n"])

    daemon._run_auto_update(cfg, registry, [_pkg("firefox")])

    entries = historymod.History().load()
    assert len(entries) == 1
    assert entries[0].package == "firefox"
    assert entries[0].status == "success"


def test_auto_update_records_failure_and_reports_no_packages(monkeypatch, tmp_path):
    monkeypatch.setattr(historymod, "HISTORY_FILE", tmp_path / "history.json")
    cfg = _cfg(auto_update=True, auto_update_profile="browsers",
               profiles={"browsers": ["firefox"]})
    registry = FakeRegistry(lines=["error: something broke\n"])

    result = daemon._run_auto_update(cfg, registry, [_pkg("firefox")])

    assert result == []  # a failed batch is never reported as "auto-updated"
    entries = historymod.History().load()
    assert entries[0].status == "failed"


def test_run_daemon_skips_auto_update_call_when_no_updates(monkeypatch):
    class EmptyRegistry:
        def __init__(self, confirm=False):
            pass

        def scan(self, force=False):
            return []

    monkeypatch.setattr(daemon, "BackendRegistry", EmptyRegistry)
    called = {"auto": False}
    monkeypatch.setattr(
        daemon, "_run_auto_update",
        lambda *a, **k: called.__setitem__("auto", True) or [],
    )
    daemon.run_daemon()
    assert called["auto"] is False
