"""Tests for keeping sudo credentials alive across a long update.

Regression cover for the failure mode where an update did all its work and
then died at the last step: sudo's timestamp expires after 15 minutes, updates
stream with stdin=DEVNULL, and yay only needs root at the very end to
`pacman -U` what it built. Past that window the prompt read EOF, sudo aborted
with "conversation failed", and a finished update was recorded as failed.
"""
import archbooster.core.procutil as procutil
import archbooster.core.sudo_auth as sudo_auth
from archbooster.core.sudo_auth import SudoKeepalive


def _fake_sudo(monkeypatch, *, present=True, cached=True):
    monkeypatch.setattr(
        sudo_auth.shutil, "which",
        lambda name: "/usr/bin/sudo" if (present and name == "sudo") else None,
    )
    monkeypatch.setattr(sudo_auth, "is_sudo_cached", lambda: cached)


def test_keepalive_refreshes_while_the_block_runs(monkeypatch):
    _fake_sudo(monkeypatch)
    calls = []
    monkeypatch.setattr(sudo_auth, "refresh", lambda: calls.append(1) or True)

    # A tiny interval so the test observes several refreshes without sleeping.
    with SudoKeepalive(interval=0.01) as ka:
        while len(calls) < 3:
            pass
        ka.stop()

    assert len(calls) >= 3


def test_keepalive_stops_when_the_block_exits(monkeypatch):
    _fake_sudo(monkeypatch)
    monkeypatch.setattr(sudo_auth, "refresh", lambda: True)

    ka = SudoKeepalive(interval=0.01)
    with ka:
        pass
    assert ka._thread is None


def test_keepalive_gives_up_once_credentials_are_gone(monkeypatch):
    """A failed refresh must end the loop, not spin on futile sudo calls."""
    _fake_sudo(monkeypatch)
    calls = []
    monkeypatch.setattr(sudo_auth, "refresh", lambda: calls.append(1) and False)

    ka = SudoKeepalive(interval=0.001)
    with ka:
        while not calls:
            pass
        thread = ka._thread
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(calls) == 1


def test_keepalive_is_a_noop_without_cached_credentials(monkeypatch):
    """Never let the keepalive itself be what triggers a password prompt."""
    _fake_sudo(monkeypatch, cached=False)
    monkeypatch.setattr(sudo_auth, "refresh", lambda: (_ for _ in ()).throw(
        AssertionError("must not refresh when nothing is cached")))

    with SudoKeepalive(interval=0.001) as ka:
        assert ka._thread is None


def test_keepalive_is_a_noop_without_sudo(monkeypatch):
    """Flatpak-only / non-root hosts have no sudo to keep alive."""
    _fake_sudo(monkeypatch, present=False, cached=False)

    with SudoKeepalive(interval=0.001) as ka:
        assert ka._thread is None


def test_stream_subprocess_holds_sudo_open_for_the_whole_run(monkeypatch):
    """The keepalive must cover the command, not just its startup."""
    events = []

    class _Spy:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *exc):
            events.append("exit")

    monkeypatch.setattr(procutil, "SudoKeepalive", _Spy)

    lines = list(procutil.stream_subprocess(
        ["python3", "-c", "print('a'); print('b')"]
    ))

    assert events == ["enter", "exit"]
    assert "a\n" in lines and "b\n" in lines
    # The keepalive is released only after the process has been reaped.
    assert lines[-1] == procutil.STATUS_OK


def test_stream_subprocess_reports_a_nonzero_exit(monkeypatch):
    monkeypatch.setattr(procutil, "SudoKeepalive", lambda: __import__(
        "contextlib").nullcontext())
    lines = list(procutil.stream_subprocess(["python3", "-c", "raise SystemExit(3)"]))
    assert lines[-1].startswith(procutil.STATUS_FAIL_PREFIX)
    assert lines[-1].strip().endswith("3")
