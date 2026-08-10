"""Tests for the live line-streaming helper used by the progress screen."""
import asyncio

from archbooster.screens.progress import stream_lines


def test_stream_lines_yields_lines_in_order():
    def gen():
        yield "a\n"
        yield "b\n"
        yield "c\n"

    async def collect():
        return [line async for line in stream_lines(gen)]

    assert asyncio.run(collect()) == ["a\n", "b\n", "c\n"]


def test_stream_lines_reraises_generator_exception():
    def boom():
        yield "ok\n"
        raise RuntimeError("kaboom")

    async def collect():
        out = []
        try:
            async for line in stream_lines(boom):
                out.append(line)
        except RuntimeError as exc:
            out.append(f"raised:{exc}")
        return out

    result = asyncio.run(collect())
    assert result[0] == "ok\n"          # line delivered before the failure
    assert result[-1] == "raised:kaboom"  # exception surfaced on the async side


# ---- failure detection -------------------------------------------------- #
# `_write_line` used to mark a run failed on any line containing "error:".
# pacman prints those and recovers (a mirror 404 the next mirror serves fine),
# so completed updates were logged as failures. Only the exit code decides.

class _FakeLog:
    def __init__(self):
        self.lines = []

    def write(self, line):
        self.lines.append(line)


def _screen():
    from archbooster.core.scanner import Package
    from archbooster.screens.progress import ProgressScreen

    return ProgressScreen([Package(
        name="brave-bin", current="1", new="2", source="AUR", priority="normal",
    )])


def test_recoverable_error_line_does_not_fail_the_run():
    log = _FakeLog()
    line = ("error: failed retrieving file 'core.db' from mirror.example : "
            "The requested URL returned error: 404\n")
    assert _screen()._write_line(log, line) is False
    assert "error" in log.lines[0]          # still shown, still red


def test_nonzero_exit_fails_the_run():
    from archbooster.core.procutil import STATUS_FAIL_PREFIX

    log = _FakeLog()
    assert _screen()._write_line(log, f"{STATUS_FAIL_PREFIX}1\n") is True


def test_successful_exit_does_not_fail_the_run():
    from archbooster.core.procutil import STATUS_OK

    assert _screen()._write_line(_FakeLog(), STATUS_OK) is False
