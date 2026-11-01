"""Behavioral coverage for forwarding extractor HTTP headers to FFmpeg."""

import shlex
from io import BytesIO

import discord
import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.ytdlp import YTDLSource

pytestmark = pytest.mark.asyncio


def _audio_source() -> discord.PCMAudio:
    return discord.PCMAudio(BytesIO(b"\x02\x00" * 1920))


async def test_stream_forwards_http_headers_as_ffmpeg_input_options(
    mocker: MockerFixture,
) -> None:
    stream_url = "https://media.example/audio"
    headers = {
        "User-Agent": 'Media Client\'s "quoted"',
        "Referer": "https://example.com/a page",
        "X-Consumer-Token": "token with spaces",
    }
    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info",
        return_value={"url": stream_url, "http_headers": headers},
    )
    ffmpeg = mocker.patch(
        "src.bot.dependencies.ytdlp.discord.FFmpegPCMAudio",
        return_value=_audio_source(),
    )

    source = await YTDLSource.stream_from_url("https://example.com/watch")
    try:
        ffmpeg.assert_called_once()
        args, kwargs = ffmpeg.call_args
        assert args == (stream_url,)
        tokens = shlex.split(kwargs["before_options"])
        header_option = tokens[tokens.index("-headers") + 1]
        parsed_headers = dict(
            line.split(": ", maxsplit=1) for line in header_option.splitlines()
        )
        assert parsed_headers["X-Consumer-Token"] == "token with spaces"
        assert parsed_headers["User-Agent"] == 'Media Client\'s "quoted"'
        assert parsed_headers["Referer"] == "https://example.com/a page"
        assert kwargs["options"] == "-vn"
    finally:
        source.cleanup()


async def test_stream_without_http_headers_remains_playable(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info",
        return_value={"url": "https://media.example/audio"},
    )
    ffmpeg = mocker.patch(
        "src.bot.dependencies.ytdlp.discord.FFmpegPCMAudio",
        return_value=_audio_source(),
    )

    source = await YTDLSource.stream_from_url("https://example.com/watch")
    try:
        tokens = shlex.split(ffmpeg.call_args.kwargs["before_options"])
        assert "-headers" not in tokens
        assert "-reconnect" in tokens
    finally:
        source.cleanup()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("X-Header\r\nInjected", "safe"),
        ("X-Header", "safe\r\nInjected: value"),
        ("X-Header\nInjected", "safe"),
        ("X-Header", "safe\nInjected: value"),
    ],
)
async def test_stream_rejects_header_crlf_injection(
    mocker: MockerFixture, name: str, value: str
) -> None:
    mocker.patch(
        "src.bot.dependencies.ytdlp.ytdl.extract_info",
        return_value={
            "url": "https://media.example/audio",
            "http_headers": {name: value},
        },
    )
    ffmpeg = mocker.patch("src.bot.dependencies.ytdlp.discord.FFmpegPCMAudio")

    with pytest.raises(ValueError, match="cannot contain CR or LF"):
        await YTDLSource.stream_from_url("https://example.com/watch")

    ffmpeg.assert_not_called()
