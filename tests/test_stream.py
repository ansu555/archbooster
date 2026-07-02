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
