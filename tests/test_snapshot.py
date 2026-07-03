"""Tests for SnapshotManager: backend detection, create/list/rollback for both
snapper and timeshift, all via mocked shutil.which/subprocess (neither tool's
real state is touched)."""
import archbooster.core.snapshot as snap
from archbooster.core.snapshot import Snapshot, SnapshotManager


def _which(available: set[str]):
    return lambda name: f"/usr/bin/{name}" if name in available else None


# --------------------------------------------------------------------------- #
# detection
# --------------------------------------------------------------------------- #

def test_auto_prefers_snapper_when_both_present(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper", "timeshift"}))
    assert SnapshotManager("auto").backend == "snapper"


def test_auto_falls_back_to_timeshift(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"timeshift"}))
    assert SnapshotManager("auto").backend == "timeshift"


def test_auto_is_unavailable_when_neither_present(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which(set()))
    mgr = SnapshotManager("auto")
    assert mgr.backend is None
    assert mgr.is_available() is False


def test_backend_none_disables_regardless_of_installed_tools(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper", "timeshift"}))
    assert SnapshotManager("none").backend is None


def test_pinned_backend_not_installed_is_unavailable(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"timeshift"}))
    assert SnapshotManager("snapper").backend is None


def test_pinned_backend_installed_is_used(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper", "timeshift"}))
    assert SnapshotManager("timeshift").backend == "timeshift"


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #

def test_create_unavailable_returns_none(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which(set()))
    assert SnapshotManager().create("test") is None


def test_create_snapper_returns_printed_number(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))

    class FakeResult:
        returncode = 0
        stdout = "42\n"

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    assert SnapshotManager().create("pre-upgrade") == "42"


def test_create_snapper_failure_returns_none(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))

    class FakeResult:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    assert SnapshotManager().create("pre-upgrade") is None


def test_create_timeshift_success_returns_description(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"timeshift"}))

    class FakeResult:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    assert SnapshotManager().create("pre-upgrade") == "pre-upgrade"


def test_create_returns_none_on_timeout(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))

    def raise_timeout(*a, **k):
        raise snap.subprocess.TimeoutExpired(cmd="snapper", timeout=120)

    monkeypatch.setattr(snap.subprocess, "run", raise_timeout)
    assert SnapshotManager().create("pre-upgrade") is None


def test_create_snapper_builds_expected_command(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R:
            returncode = 0
            stdout = "7\n"
        return R()

    monkeypatch.setattr(snap.subprocess, "run", fake_run)
    SnapshotManager().create("pre-upgrade")
    assert captured["cmd"] == [
        "sudo", "snapper", "-c", "root", "create",
        "--description", "pre-upgrade", "--print-number",
    ]


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #

def test_list_unavailable_returns_empty(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which(set()))
    assert SnapshotManager().list() == []


def test_list_snapper_parses_json(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))

    class FakeResult:
        returncode = 0
        stdout = (
            '{"root": ['
            '{"number": 0, "date": "2024-01-01 00:00:00", "description": "current"},'
            '{"number": 7, "date": "2024-06-01 12:00:00", "description": "pre-upgrade"}'
            ']}'
        )

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    snaps = SnapshotManager().list()
    assert snaps == [
        Snapshot(id="0", date="2024-01-01 00:00:00", description="current", backend="snapper"),
        Snapshot(id="7", date="2024-06-01 12:00:00", description="pre-upgrade", backend="snapper"),
    ]


def test_list_snapper_invalid_json_returns_empty(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))

    class FakeResult:
        returncode = 0
        stdout = "not json"

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    assert SnapshotManager().list() == []


def test_list_snapper_nonzero_exit_returns_empty(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))

    class FakeResult:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    assert SnapshotManager().list() == []


def test_list_timeshift_parses_rows(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"timeshift"}))

    class FakeResult:
        returncode = 0
        stdout = (
            "Device : /dev/sda2\n"
            "\n"
            "Num     Name                 Tags  Description\n"
            "------------------------------------------------\n"
            "0       2024-01-01_12-00-00  O     Ondemand snapshot\n"
            "1       2024-06-01_08-30-00  D     archbooster: pre-full-upgrade\n"
        )

    monkeypatch.setattr(snap.subprocess, "run", lambda *a, **k: FakeResult())
    snaps = SnapshotManager().list()
    assert [s.id for s in snaps] == ["2024-01-01_12-00-00", "2024-06-01_08-30-00"]
    assert snaps[1].description == "archbooster: pre-full-upgrade"
    assert all(s.backend == "timeshift" for s in snaps)


# --------------------------------------------------------------------------- #
# rollback
# --------------------------------------------------------------------------- #

def test_rollback_unavailable_yields_message(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which(set()))
    out = list(SnapshotManager().rollback("7"))
    assert any("No snapshot backend available" in line for line in out)


def test_rollback_snapper_builds_expected_command(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"snapper"}))
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "rolled back\n"

    monkeypatch.setattr(snap, "stream_subprocess", fake_stream)
    out = list(SnapshotManager().rollback("7"))
    assert out == ["rolled back\n"]
    assert captured["cmd"] == ["sudo", "snapper", "-c", "root", "rollback", "7"]


def test_rollback_timeshift_builds_expected_command(monkeypatch):
    monkeypatch.setattr(snap.shutil, "which", _which({"timeshift"}))
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        yield "restored\n"

    monkeypatch.setattr(snap, "stream_subprocess", fake_stream)
    out = list(SnapshotManager().rollback("2024-06-01_08-30-00"))
    assert out == ["restored\n"]
    assert captured["cmd"] == [
        "sudo", "timeshift", "--restore",
        "--snapshot", "2024-06-01_08-30-00", "--yes",
    ]
