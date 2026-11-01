import io
import threading
from pathlib import Path
from typing import Any

import pytest

from src.bot.dependencies import live_hls


class _Response:
    def __init__(self, url: str, body: str) -> None:
        self.url = url
        self._body = io.BytesIO(body.encode())
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self.closed = True


class _Downloader:
    def __init__(self, responses: dict[str, list[str]]) -> None:
        self.params: dict[str, Any] = {"quiet": True}
        self.responses = responses
        self.requests: list[Any] = []
        self.opened: list[_Response] = []

    def urlopen(self, request: Any) -> _Response:
        self.requests.append(request)
        url = request.url
        bodies = self.responses[url]
        body = bodies.pop(0) if len(bodies) > 1 else bodies[0]
        response = _Response(url, body)
        self.opened.append(response)
        return response


@pytest.fixture
def native_download(mocker: Any) -> Any:
    def download(instance: Any, _filename: str, info: dict[str, Any]) -> bool:
        manifest = info["hls_media_playlist_data"]
        urls = [line for line in manifest.splitlines() if line and not line.startswith("#")]
        instance._output_proxy.write(("|".join(urls) + "\n").encode())
        return True

    return mocker.patch.object(live_hls._PipeHlsFD, "real_download", autospec=True, side_effect=download)


def test_growing_sliding_playlist_deduplicates_and_honors_endlist(
    tmp_path: Path, native_download: Any
) -> None:
    first = """#EXTM3U
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:10
#EXTINF:2,
10.aac
#EXTINF:2,
11.aac
"""
    second = """#EXTM3U
#EXT-X-TARGETDURATION:2
#EXT-X-MEDIA-SEQUENCE:11
#EXTINF:2,
11.aac
#EXTINF:2,
12.aac
#EXT-X-ENDLIST
"""
    downloader = _Downloader({"https://rr1.googlevideo.com/live.m3u8": [first, second]})
    output = io.BytesIO()

    live_hls.stream_live_hls(
        downloader,
        {"url": "https://rr1.googlevideo.com/live.m3u8", "ext": "aac"},
        output,
        threading.Event(),
        tmp_path,
    )

    assert output.getvalue().splitlines() == [
        b"https://rr1.googlevideo.com/10.aac",
        b"https://rr1.googlevideo.com/11.aac",
        b"https://rr1.googlevideo.com/12.aac",
    ]
    assert len(downloader.requests) == 2
    assert native_download.call_count == 3


def test_master_prefers_audio_rendition_and_forwards_headers(
    tmp_path: Path, native_download: Any
) -> None:
    master = """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",DEFAULT=YES,URI="audio/index.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=900000,AUDIO="audio"
video/index.m3u8
"""
    media = """#EXTM3U
#EXT-X-MEDIA-SEQUENCE:4
#EXTINF:4,
segment.aac
#EXT-X-ENDLIST
"""
    downloader = _Downloader(
        {
            "https://rr1.googlevideo.com/path/master.m3u8": [master],
            "https://rr1.googlevideo.com/path/audio/index.m3u8": [media],
        }
    )
    output = io.BytesIO()

    live_hls.stream_live_hls(
        downloader,
        {
            "url": "https://rr1.googlevideo.com/path/master.m3u8",
            "http_headers": {"Referer": "https://youtube.example/"},
            "ext": "aac",
        },
        output,
        threading.Event(),
        tmp_path,
    )

    assert output.getvalue() == b"https://rr1.googlevideo.com/path/audio/segment.aac\n"
    assert [request.url for request in downloader.requests] == [
        "https://rr1.googlevideo.com/path/master.m3u8",
        "https://rr1.googlevideo.com/path/audio/index.m3u8",
    ]
    assert all(
        request.headers.get("Referer") == "https://youtube.example/"
        for request in downloader.requests
    )


def test_cancelled_wait_stops_polling_without_another_request(
    tmp_path: Path, native_download: Any
) -> None:
    playlist = """#EXTM3U
#EXT-X-TARGETDURATION:8
#EXT-X-MEDIA-SEQUENCE:1
#EXTINF:8,
one.ts
"""
    downloader = _Downloader({"https://rr1.googlevideo.com/live.m3u8": [playlist]})

    class _CancelOnWait(threading.Event):
        waits: list[float]

        def __init__(self) -> None:
            super().__init__()
            self.waits = []

        def wait(self, timeout: float | None = None) -> bool:
            assert timeout is not None
            self.waits.append(timeout)
            self.set()
            return True

    cancelled = _CancelOnWait()
    live_hls.stream_live_hls(
        downloader,
        {"url": "https://rr1.googlevideo.com/live.m3u8", "ext": "mp4"},
        io.BytesIO(),
        cancelled,
        tmp_path,
    )

    assert cancelled.waits == [4.0]
    assert len(downloader.requests) == 1


def test_snapshot_preserves_aes_sequence_map_discontinuity_and_ranges() -> None:
    playlist = """#EXTM3U
#EXT-X-MEDIA-SEQUENCE:20
#EXT-X-KEY:METHOD=AES-128,URI="key.bin"
#EXT-X-MAP:URI="init.mp4",BYTERANGE="100@0"
#EXTINF:2,
#EXT-X-BYTERANGE:10@100
media.mp4
#EXT-X-DISCONTINUITY
#EXTINF:2,
#EXT-X-BYTERANGE:12
media.mp4
#EXT-X-ENDLIST
"""
    segments, _, ended = live_hls._parse_media_playlist(
        playlist, "https://rr1.googlevideo.com/live/index.m3u8"
    )
    snapshot = live_hls._snapshot(segments[1], True)

    assert ended is True
    assert "#EXT-X-MEDIA-SEQUENCE:21" in snapshot
    assert '#EXT-X-KEY:METHOD=AES-128,URI="https://rr1.googlevideo.com/live/key.bin"' in snapshot
    assert "IV=0x00000000000000000000000000000015" in snapshot
    assert '#EXT-X-MAP:URI="https://rr1.googlevideo.com/live/init.mp4",BYTERANGE=100@0' in snapshot
    assert "#EXT-X-DISCONTINUITY" in snapshot
    assert "#EXT-X-BYTERANGE:12@110" in snapshot


def test_map_uses_declaration_key_then_restores_clear_media_state() -> None:
    playlist = """#EXTM3U
#EXT-X-MEDIA-SEQUENCE:7
#EXT-X-KEY:METHOD=AES-128,URI="map.key",IV=0x00000000000000000000000000000001
#EXT-X-MAP:URI="init.mp4"
#EXT-X-KEY:METHOD=NONE
#EXTINF:2,
clear.m4s
#EXT-X-ENDLIST
"""
    segments, _, _ = live_hls._parse_media_playlist(
        playlist, "https://rr1.googlevideo.com/live/index.m3u8"
    )

    snapshot = live_hls._snapshot(segments[0], True)
    assert snapshot.index(
        'URI="https://rr1.googlevideo.com/live/map.key"'
    ) < snapshot.index("#EXT-X-MAP:")
    assert snapshot.index("#EXT-X-MAP:") < snapshot.index("#EXT-X-KEY:METHOD=NONE")


def test_explicit_unsupported_encryption_error(tmp_path: Path) -> None:
    playlist = """#EXTM3U
#EXT-X-KEY:METHOD=SAMPLE-AES,URI="drm.key"
#EXTINF:2,
segment.ts
#EXT-X-ENDLIST
"""
    downloader = _Downloader({"https://rr1.googlevideo.com/live.m3u8": [playlist]})

    with pytest.raises(ValueError, match="Unsupported HLS encryption method: SAMPLE-AES"):
        live_hls.stream_live_hls(
            downloader,
            {"url": "https://rr1.googlevideo.com/live.m3u8", "ext": "mp4"},
            io.BytesIO(),
            threading.Event(),
            tmp_path,
        )


def test_master_cycle_is_rejected(tmp_path: Path) -> None:
    master = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1
master.m3u8
"""
    downloader = _Downloader({"https://rr1.googlevideo.com/master.m3u8": [master]})

    with pytest.raises(ValueError, match="Cyclic HLS master playlists"):
        live_hls.stream_live_hls(
            downloader,
            {"url": "https://rr1.googlevideo.com/master.m3u8"},
            io.BytesIO(),
            threading.Event(),
            tmp_path,
        )


def test_stream_native_http_uses_restricted_transport_and_caller_output(
    tmp_path: Path,
) -> None:
    downloader = _Downloader({"https://rr1.googlevideo.com/audio.webm": ["native-bytes"]})
    output = io.BytesIO()

    live_hls.stream_native(
        downloader,
        {
            "url": "https://rr1.googlevideo.com/audio.webm",
            "protocol": "https",
            "http_headers": {"Origin": "https://youtube.example"},
        },
        output,
        threading.Event(),
        tmp_path,
    )

    assert output.getvalue() == b"native-bytes"
    assert len(downloader.requests) == 1
    assert downloader.requests[0].headers.get("Origin") == "https://youtube.example"
    assert not (tmp_path / "native-output").exists()
    assert downloader.opened[0].closed is True


def test_stream_native_completes_partial_writes_and_closes_response(
    tmp_path: Path,
) -> None:
    class _PartialWriter(io.BytesIO):
        def write(self, data: bytes) -> int:
            return super().write(data[:2])

    downloader = _Downloader({"https://rr1.googlevideo.com/audio": ["abcdef"]})
    output = _PartialWriter()
    live_hls.stream_native(
        downloader,
        {"url": "https://rr1.googlevideo.com/audio", "protocol": "https"},
        output,
        threading.Event(),
        tmp_path,
    )

    assert output.getvalue() == b"abcdef"
    assert downloader.opened[0].closed is True


def test_stream_native_closes_response_when_cancelled(tmp_path: Path) -> None:
    cancelled = threading.Event()

    class _CancellingResponse(_Response):
        def read(self, size: int = -1) -> bytes:
            cancelled.set()
            return super().read(size)

    response = _CancellingResponse("https://rr1.googlevideo.com/audio", "chunk")
    downloader = _Downloader({})
    downloader.urlopen = lambda _request: response  # type: ignore[method-assign]

    live_hls.stream_native(
        downloader,
        {"url": response.url, "protocol": "http"},
        io.BytesIO(),
        cancelled,
        tmp_path,
    )

    assert response.closed is True



def test_stream_native_nonlive_hls_uses_exact_output_adapter(
    tmp_path: Path, native_download: Any
) -> None:
    playlist = """#EXTM3U
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:2,
segment.ts
#EXT-X-ENDLIST
"""
    downloader = _Downloader({"https://rr1.googlevideo.com/vod.m3u8": [playlist]})
    output = io.BytesIO()

    live_hls.stream_native(
        downloader,
        {
            "url": "https://rr1.googlevideo.com/vod.m3u8",
            "protocol": "m3u8",
            "ext": "mp4",
        },
        output,
        threading.Event(),
        tmp_path,
    )

    assert output.getvalue()
    assert native_download.call_count == 1
    assert not (tmp_path / "native-output").exists()
    assert downloader.opened[0].closed is True


def test_stream_native_dash_forces_native_generator_path(
    tmp_path: Path, mocker: Any
) -> None:
    downloader = _Downloader({})
    output = io.BytesIO()
    factory_calls = 0

    def fragments(_ctx: dict[str, Any]) -> Any:
        nonlocal factory_calls
        factory_calls += 1
        yield {"url": "https://rr1.googlevideo.com/dash/init"}


    def download(instance: Any, _filename: str, info: dict[str, Any]) -> bool:
        assert info["protocol"] == "http_dash_segments_generator"
        assert info["is_live"] is True
        fragment_source = info["fragments"]
        assert callable(fragment_source)
        assert list(fragment_source({})) == [
            {"url": "https://rr1.googlevideo.com/dash/init"}
        ]
        instance._output_proxy.write(b"dash-bytes")
        return True

    native_dash = mocker.patch.object(
        live_hls._PipeDashFD,
        "real_download",
        autospec=True,
        side_effect=download,
    )
    live_hls.stream_native(
        downloader,
        {
            "url": "https://rr1.googlevideo.com/dash/",
            "protocol": "http_dash_segments",
            "fragments": fragments,
            "is_live": True,
            "ext": "webm",
        },
        output,
        threading.Event(),
        tmp_path,
    )

    assert output.getvalue() == b"dash-bytes"
    assert native_dash.call_count == 1
    assert factory_calls == 1
    assert not (tmp_path / "native-output").exists()


def test_finite_dash_fragments_keep_sized_contract() -> None:
    info = live_hls._validated_dash_info(
        {
            "url": "https://rr1.googlevideo.com/dash/",
            "protocol": "http_dash_segments",
            "is_live": False,
            "fragments": [{"path": "init"}, {"path": "media"}],
        }
    )

    assert isinstance(info["fragments"], list)
    assert len(info["fragments"]) == 2


def test_stream_native_rejects_protocol_that_requires_external_downloader(
    tmp_path: Path,
) -> None:
    downloader = _Downloader({})

    with pytest.raises(ValueError, match="Unsupported native media protocol: rtmp"):
        live_hls.stream_native(
            downloader,
            {"url": "rtmp://example.test/live", "protocol": "rtmp"},
            io.BytesIO(),
            threading.Event(),
            tmp_path,
        )
