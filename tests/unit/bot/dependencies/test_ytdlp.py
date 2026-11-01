"""Regression coverage for the YouTube-only media security boundary."""

import selectors
import socket
from io import BytesIO
from typing import Any

import discord
import pytest
from pytest_mock import MockerFixture

from src.bot.dependencies.media_proxy import _ConnectHandler, _ProxyServer
from src.bot.dependencies.ytdlp import YTDLSource
from src.bot.models import PlaylistTrack, SearchResult, Track

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def public_dns(mocker: MockerFixture) -> None:
    mocker.patch(
        "src.bot.dependencies.media_proxy.socket.getaddrinfo",
        return_value=[
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("142.250.72.206", 443),
            )
        ],
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1/media",
        "https://user:password@youtube.com/watch?v=example",
        "file:///etc/passwd",
        "data:text/plain,media",
        "https://youtube.com/\nwatch?v=example",
        "https://evil.example/watch?v=example",
    ],
)
async def test_rejects_unsafe_input_before_extraction(
    mocker: MockerFixture, value: str
) -> None:
    extract = mocker.patch("src.bot.dependencies.ytdlp._extract_info")

    with pytest.raises(ValueError):
        await YTDLSource.get_tracks_info(value)

    extract.assert_not_called()




async def test_search_keeps_validated_youtube_page_urls(
    mocker: MockerFixture,
) -> None:
    page_url = "https://www.youtube.com/watch?v=example"
    extract = mocker.patch(
        "src.bot.dependencies.ytdlp._extract_info",
        return_value={
            "extractor": "youtube:search",
            "entries": [{"title": "Result", "webpage_url": page_url}],
        },
    )

    result = await YTDLSource.get_tracks_info("example search")

    assert isinstance(result, SearchResult)
    assert result.url == page_url
    assert extract.call_args.args[0] == "ytsearch5:example search"


async def test_rejects_malicious_playlist_entry(mocker: MockerFixture) -> None:
    mocker.patch(
        "src.bot.dependencies.ytdlp._extract_info",
        return_value={
            "extractor": "youtube:tab",
            "entries": [
                {
                    "title": "Malicious",
                    "webpage_url": "https://127.0.0.1/private",
                }
            ],
        },
    )

    with pytest.raises(ValueError):
        await YTDLSource.get_tracks_info(
            "https://www.youtube.com/playlist?list=example"
        )


async def test_youtube_video_and_playlist_are_supported(
    mocker: MockerFixture,
) -> None:
    video_url = "https://www.youtube.com/watch?v=example"
    extract = mocker.patch(
        "src.bot.dependencies.ytdlp._extract_info",
        side_effect=[
            {
                "extractor": "youtube",
                "title": "Video",
                "webpage_url": video_url,
            },
            {
                "extractor": "youtube:tab",
                "entries": [{"webpage_url": video_url}],
            },
        ],
    )

    track = await YTDLSource.get_tracks_info(video_url)
    playlist = await YTDLSource.get_tracks_info(
        "https://www.youtube.com/playlist?list=example"
    )

    assert isinstance(track, Track)
    assert track.url == video_url
    assert isinstance(playlist, list)
    assert all(isinstance(item, PlaylistTrack) for item in playlist)
    assert extract.call_count == 2


async def test_connect_proxy_rejects_untrusted_destination(
    mocker: MockerFixture,
) -> None:
    request = mocker.Mock()
    request.recv.side_effect = [
        b"CONNECT localhost:443 HTTP/1.1\r\nHost: localhost\r\n\r\n"
    ]
    handler = object.__new__(_ConnectHandler)
    handler.request = request

    handler.handle()

    request.sendall.assert_called_once_with(
        b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n"
    )


async def test_connect_header_has_absolute_deadline(mocker: MockerFixture) -> None:
    request = mocker.Mock()
    mocker.patch(
        "src.bot.dependencies.media_proxy.time.monotonic",
        side_effect=[0.0, 11.0],
    )
    handler = object.__new__(_ConnectHandler)
    handler.request = request

    handler.handle()

    request.recv.assert_not_called()


async def test_proxy_rejects_connections_before_spawning_over_cap(
    mocker: MockerFixture,
) -> None:
    server = object.__new__(_ProxyServer)
    admission = mocker.Mock()
    admission.acquire.return_value = False
    server._admission = admission
    request = mocker.Mock()
    spawn = mocker.patch("socketserver.ThreadingTCPServer.process_request")

    server.process_request(request, ("127.0.0.1", 1234))

    request.close.assert_called_once_with()
    spawn.assert_not_called()


async def test_connect_proxy_pins_vetted_numeric_address(
    mocker: MockerFixture,
) -> None:
    request = mocker.Mock()
    request.recv.side_effect = [
        b"CONNECT rr1.googlevideo.com:443 HTTP/1.1\r\n"
        b"Host: rr1.googlevideo.com\r\n"
        b"Proxy-Authorization: Basic dGVzdDp4\r\n\r\ncoalesced TLS client hello",
        b"",
    ]
    upstream = mocker.Mock()
    upstream.__enter__ = mocker.Mock(return_value=upstream)
    upstream.__exit__ = mocker.Mock(return_value=False)
    upstream.recv.return_value = b""
    scope = mocker.Mock()
    scope.register.return_value = True
    mocker.patch.dict(
        "src.bot.dependencies.media_proxy._scopes", {"test": scope}
    )
    socket_factory = mocker.patch(
        "src.bot.dependencies.media_proxy.socket.socket", return_value=upstream
    )
    selector = mocker.patch(
        "src.bot.dependencies.media_proxy.selectors.DefaultSelector"
    )
    upstream.send.side_effect = [5, len(b"coalesced TLS client hello") - 5]
    request_key = mocker.Mock(fileobj=request)
    upstream_key = mocker.Mock(fileobj=upstream)
    selector.return_value.select.side_effect = [
        [(upstream_key, selectors.EVENT_WRITE)],
        [(upstream_key, selectors.EVENT_WRITE)],
        [
            (request_key, selectors.EVENT_READ),
            (upstream_key, selectors.EVENT_READ),
        ],
    ]
    handler = object.__new__(_ConnectHandler)
    handler.request = request

    handler.handle()

    socket_factory.return_value.connect.assert_called_once_with(
        ("142.250.72.206", 443)
    )
    assert upstream.send.call_count == 2
    request.sendall.assert_called_once_with(
        b"HTTP/1.1 200 Connection Established\r\n\r\n"
    )


async def test_playback_streams_owned_pipe_into_network_disabled_ffmpeg(
    mocker: MockerFixture, tmp_path: Any
) -> None:
    page_url = "https://www.youtube.com/watch?v=example"
    directory = tmp_path / "media"
    directory.mkdir()
    mocker.patch(
        "src.bot.dependencies.ytdlp.tempfile.mkdtemp", return_value=str(directory)
    )
    mocker.patch(
        "src.bot.dependencies.ytdlp._extract_info",
        return_value={"extractor": "youtube", "protocol": "https"},
    )
    worker = mocker.patch("src.bot.dependencies.ytdlp.threading.Thread")
    audio = mocker.patch("src.bot.dependencies.ytdlp._PipeFFmpegAudio")
    audio.return_value = discord.PCMAudio(BytesIO(b"\x00" * 3840))

    await YTDLSource.stream_from_url(page_url)

    worker.assert_called_once()
    source, cancelled, errors, transports = audio.call_args.args
    assert source.readable()
    assert not cancelled.is_set()
    assert len(transports) == 1
    transports[0].close()
    assert errors == []
    worker.call_args.kwargs["args"][2].close()
