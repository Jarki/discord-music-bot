import threading
from collections.abc import Callable, Iterable, Sized
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

from yt_dlp.downloader.dash import DashSegmentsFD
from yt_dlp.downloader.hls import HlsFD
from yt_dlp.networking import Request
from yt_dlp.utils import parse_m3u8_attributes, urljoin

from src.bot.dependencies.media_proxy import validate_media_url


@dataclass(frozen=True)
class _Segment:
    sequence: int
    url: str
    tags: tuple[str, ...]
    key: str | None
    init_map: str | None
    init_map_key: str | None


def _write_all(output: BinaryIO, data: bytes) -> int:
    view = memoryview(data)
    total = 0
    while total < len(view):
        written = output.write(view[total:])
        if written is None or written <= 0:
            raise BrokenPipeError("Media output accepted no data")
        total += written
    return total


class _OutputProxy:
    def __init__(self, output: BinaryIO) -> None:
        self._output = output
        self.bytes_written = 0

    def write(self, data: bytes) -> int:
        written = _write_all(self._output, data)
        self.bytes_written += written
        return written

    def flush(self) -> None:
        self._output.flush()

    def close(self) -> None:
        # FragmentFD owns its destination stream.  The pipe is owned by its caller.
        self.flush()


class _PipeHlsFD(HlsFD):  # type: ignore[misc]
    def __init__(
        self,
        ydl: Any,
        params: dict[str, Any],
        sentinel: str,
        output: BinaryIO,
    ) -> None:
        super().__init__(ydl, params)
        self._sentinel = sentinel
        self._output_proxy = _OutputProxy(output)

    @classmethod
    def can_download(
        cls,
        manifest: str,
        info_dict: dict[str, Any],
        allow_unplayable_formats: bool = False,
    ) -> bool:
        # stream_live_hls performs the native capability check before constructing us.
        # Returning True here prevents HlsFD from silently delegating to FFmpeg.
        return True

    def sanitize_open(self, filename: str, open_mode: str) -> tuple[Any, str]:
        if filename == self._sentinel and open_mode in {"wb", "ab"}:
            return self._output_proxy, filename
        return super().sanitize_open(filename, open_mode)

    def filesize_or_none(self, filename: str, *args: Any, **kwargs: Any) -> int:
        if filename == self._sentinel:
            return self._output_proxy.bytes_written
        return super().filesize_or_none(filename, *args, **kwargs)


class _PipeDashFD(DashSegmentsFD):  # type: ignore[misc]
    def __init__(
        self,
        ydl: Any,
        params: dict[str, Any],
        sentinel: str,
        output: BinaryIO,
    ) -> None:
        super().__init__(ydl, params)
        self._sentinel = sentinel
        self._output_proxy = _OutputProxy(output)

    def sanitize_open(self, filename: str, open_mode: str) -> tuple[Any, str]:
        if filename == self._sentinel and open_mode in {"wb", "ab"}:
            return self._output_proxy, filename
        return super().sanitize_open(filename, open_mode)

    def filesize_or_none(self, filename: str, *args: Any, **kwargs: Any) -> int:
        if filename == self._sentinel:
            return self._output_proxy.bytes_written
        return super().filesize_or_none(filename, *args, **kwargs)


def _validate_manifest_controls(manifest: str) -> None:
    if any(
        character not in "\r\n"
        and (ord(character) < 32 or ord(character) == 127)
        for character in manifest
    ):
        raise ValueError("HLS manifest URL contains control characters")


def _validated_join(base_url: str | None, raw_url: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in raw_url):
        raise ValueError("Media URL contains control characters")
    parsed = urlsplit(raw_url)
    if parsed.scheme or parsed.netloc:
        validate_media_url(raw_url, resolve=False)
    resolved = urljoin(base_url, raw_url) if base_url is not None else raw_url
    return validate_media_url(resolved, resolve=False)


def _fetch_manifest(
    downloader: Any, url: str, headers: dict[str, str]
) -> tuple[str, str]:
    url = _validated_join(None, url)
    response = downloader.urlopen(Request(url, headers=headers))
    try:
        final_url = _validated_join(None, response.url)
        return response.read().decode("utf-8", "replace"), final_url
    finally:
        response.close()


def _select_media_url(manifest: str, manifest_url: str) -> str | None:
    _validate_manifest_controls(manifest)
    audio: list[tuple[bool, str]] = []
    variants: list[tuple[int, str]] = []
    lines = [line.strip() for line in manifest.splitlines() if line.strip()]
    for line in lines:
        if not line.startswith("#EXT-X-MEDIA:"):
            continue
        attributes = parse_m3u8_attributes(line.partition(":")[2])
        uri = attributes.get("URI")
        if attributes.get("TYPE") == "AUDIO" and uri:
            preferred = attributes.get("DEFAULT") == "YES" or attributes.get("AUTOSELECT") == "YES"
            audio.append((preferred, _validated_join(manifest_url, uri)))
    if audio:
        return max(audio, key=lambda item: item[0])[1]

    for index, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:") or index + 1 >= len(lines):
            continue
        uri = lines[index + 1]
        if uri.startswith("#"):
            continue
        attributes = parse_m3u8_attributes(line.partition(":")[2])
        try:
            bandwidth = int(attributes.get("AVERAGE-BANDWIDTH") or attributes.get("BANDWIDTH") or 0)
        except ValueError:
            bandwidth = 0
        variants.append((bandwidth, _validated_join(manifest_url, uri)))
    return max(variants, default=(0, ""))[1] or None


def _resolve_media_manifest(
    downloader: Any, url: str, headers: dict[str, str]
) -> tuple[str, str]:
    visited: set[str] = set()
    while True:
        if url in visited:
            raise ValueError("Cyclic HLS master playlists are not supported")
        visited.add(url)
        manifest, final_url = _fetch_manifest(downloader, url, headers)
        selected = _select_media_url(manifest, final_url)
        if selected is None:
            return manifest, final_url
        url = selected


def _parse_media_playlist(manifest: str, manifest_url: str) -> tuple[list[_Segment], float, bool]:
    _validate_manifest_controls(manifest)
    sequence = 0
    target_duration = 2.0
    active_key: str | None = None
    active_map: str | None = None
    active_map_key: str | None = None
    pending: list[str] = []
    segments: list[_Segment] = []
    byte_offset = 0

    for raw_line in manifest.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            sequence = int(line.partition(":")[2])
        elif line.startswith("#EXT-X-TARGETDURATION:"):
            target_duration = max(float(line.partition(":")[2]), 0.1)
        elif line.startswith("#EXT-X-KEY:"):
            attributes = parse_m3u8_attributes(line.partition(":")[2])
            method = attributes.get("METHOD")
            if method not in {"NONE", "AES-128"}:
                raise ValueError(f"Unsupported HLS encryption method: {method or 'unknown'}")
            if uri := attributes.get("URI"):
                attributes["URI"] = _validated_join(manifest_url, uri)
                line = "#EXT-X-KEY:" + ",".join(
                    f'{key}="{value}"' if key == "URI" else f"{key}={value}"
                    for key, value in attributes.items()
                )
            active_key = line
        elif line.startswith("#EXT-X-MAP:"):
            attributes = parse_m3u8_attributes(line.partition(":")[2])
            uri = attributes.get("URI")
            if not uri:
                raise ValueError("HLS initialization map is missing its URI")
            attributes["URI"] = _validated_join(manifest_url, uri)
            rendered = ",".join(
                f'{key}="{value}"' if key == "URI" else f"{key}={value}"
                for key, value in attributes.items()
            )
            active_map = f"#EXT-X-MAP:{rendered}"
            active_map_key = active_key
        elif line.startswith("#EXT-X-BYTERANGE:"):
            value = line.partition(":")[2]
            length_text, separator, offset_text = value.partition("@")
            offset = int(offset_text) if separator else byte_offset
            byte_offset = offset + int(length_text)
            pending.append(f"#EXT-X-BYTERANGE:{length_text}@{offset}")
        elif line.startswith("#"):
            if line.startswith(("#EXTINF:", "#EXT-X-DISCONTINUITY", "#EXT-X-PROGRAM-DATE-TIME:")):
                pending.append(line)
        else:
            segment_url = _validated_join(manifest_url, line)
            segments.append(
                _Segment(
                    sequence,
                    segment_url,
                    tuple(pending),
                    active_key,
                    active_map,
                    active_map_key,
                )
            )
            sequence += 1
            pending.clear()
    return segments, target_duration, "#EXT-X-ENDLIST" in manifest


def _snapshot(segment: _Segment, include_map: bool) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", f"#EXT-X-MEDIA-SEQUENCE:{segment.sequence}"]
    if include_map and segment.init_map:
        if segment.init_map_key:
            lines.append(segment.init_map_key)
        lines.append(segment.init_map)
    if segment.key:
        key = segment.key
        attributes = parse_m3u8_attributes(key.partition(":")[2])
        if attributes.get("METHOD") == "AES-128" and "IV" not in attributes:
            # HlsFD counts EXT-X-MAP as a fragment. Pin the media IV to its
            # playlist sequence, independently of the map's encryption state.
            key = f"{key},IV=0x{segment.sequence:032x}"
        lines.append(key)
    lines.extend(segment.tags)
    lines.extend((segment.url, "#EXT-X-ENDLIST", ""))
    return "\n".join(lines)


def stream_live_hls(
    downloader: Any,
    info: dict[str, Any],
    output: BinaryIO,
    cancelled: threading.Event,
    temp_dir: Path,
) -> None:
    """Incrementally stream a live HLS playlist through yt-dlp's native downloader."""
    if cancelled.is_set():
        return
    url = info.get("url")
    if not isinstance(url, str):
        raise ValueError("Live HLS format has no manifest URL")
    headers = info.get("http_headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("Invalid HLS HTTP headers")

    manifest, media_url = _resolve_media_manifest(downloader, url, headers)
    last_sequence: int | None = None
    emitted_map: tuple[str, str | None] | None = None
    sentinel = str(temp_dir / "live-output")
    params = {
        **downloader.params,
        "continuedl": False,
        "nopart": True,
        "_no_ytdl_file": True,
        "external_downloader": "native",
    }

    while not cancelled.is_set():
        segments, target_duration, ended = _parse_media_playlist(manifest, media_url)
        new_segments = [segment for segment in segments if last_sequence is None or segment.sequence > last_sequence]
        for segment in new_segments:
            if cancelled.is_set():
                return
            map_state = (
                (segment.init_map, segment.init_map_key)
                if segment.init_map is not None
                else None
            )
            snapshot = _snapshot(segment, map_state != emitted_map)
            finite_info = {
                **info,
                "url": media_url,
                "is_live": False,
                "protocol": "m3u8_native",
                "hls_media_playlist_data": snapshot,
                "http_headers": headers,
                "ext": info.get("ext") or "mp4",
            }
            if HlsFD._has_drm(snapshot):
                raise ValueError("DRM-protected HLS streams are not supported")
            if not HlsFD.can_download(snapshot, finite_info, False):
                raise ValueError("HLS playlist requires an unsupported external downloader")

            def stop_when_cancelled(_status: dict[str, Any]) -> None:
                if cancelled.is_set():
                    raise RuntimeError("Live HLS stream was cancelled")

            native = _PipeHlsFD(downloader, params, sentinel, output)
            native.add_progress_hook(stop_when_cancelled)
            if not native.real_download(sentinel, finite_info):
                raise RuntimeError("Native HLS fragment download failed")
            last_sequence = segment.sequence
            if map_state is not None:
                emitted_map = map_state

        if ended:
            return
        if cancelled.wait(target_duration / 2):
            return
        manifest, media_url = _resolve_media_manifest(downloader, media_url, headers)


def _validated_dash_fragments(
    source: Iterable[dict[str, Any]]
    | Callable[[dict[str, Any]], Iterable[dict[str, Any]]],
    base_url: str | None,
    *,
    lazy: bool,
) -> Iterable[dict[str, Any]] | Callable[[dict[str, Any]], Iterable[dict[str, Any]]]:
    def validate(fragment: dict[str, Any]) -> dict[str, Any]:
        raw_url = fragment.get("url") or fragment.get("path")
        if not isinstance(raw_url, str):
            raise ValueError("DASH fragment has no URL or path")
        _validated_join(base_url, raw_url)
        return fragment

    if callable(source):
        if not lazy:
            raise ValueError("Non-live DASH fragment factories are not supported")

        def validated_factory(ctx: dict[str, Any]) -> Iterable[dict[str, Any]]:
            return (validate(fragment) for fragment in source(ctx))

        return validated_factory

    if isinstance(source, Sized) or not lazy:
        return [validate(fragment) for fragment in source]
    return (validate(fragment) for fragment in source)


def _validated_dash_info(info: dict[str, Any]) -> dict[str, Any]:
    validated = dict(info)
    base_url = validated.get("fragment_base_url")
    if base_url is not None:
        if not isinstance(base_url, str):
            raise ValueError("Invalid DASH fragment base URL")
        base_url = _validated_join(None, base_url)
        validated["fragment_base_url"] = base_url
    validation_base = base_url or validated.get("url")
    fragments = validated.get("fragments")
    if fragments is None:
        raise ValueError("DASH format has no fragments")
    validated["fragments"] = _validated_dash_fragments(
        fragments,
        validation_base,
        lazy=bool(validated.get("is_live")),
    )
    if requested := validated.get("requested_formats"):
        validated["requested_formats"] = [
            _validated_dash_info({**validated, **media, "requested_formats": []})
            for media in requested
        ]
    return validated


def stream_native(
    downloader: Any,
    info: dict[str, Any],
    output: BinaryIO,
    cancelled: threading.Event,
    temp_dir: Path,
) -> None:
    """Stream an extracted native format without filesystem output or FFmpeg."""
    if cancelled.is_set():
        return
    url = info.get("url")
    protocol = info.get("protocol")
    if not isinstance(url, str):
        raise ValueError("Media format has no URL")
    allowed_protocols = {
        None,
        "http",
        "https",
        "m3u8",
        "m3u8_native",
        "http_dash_segments",
        "http_dash_segments_generator",
    }
    if protocol not in allowed_protocols:
        raise ValueError(f"Unsupported native media protocol: {protocol}")
    url = _validated_join(None, url)
    if info.get("is_live") and protocol not in {
        "http_dash_segments",
        "http_dash_segments_generator",
    }:
        raise ValueError("Live formats must use a supported live streamer")
    headers = info.get("http_headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("Invalid media HTTP headers")

    if protocol in {None, "http", "https"}:
        response = downloader.urlopen(Request(url, headers=headers))
        try:
            while not cancelled.is_set():
                chunk = response.read(65_536)
                if not chunk:
                    return
                _write_all(output, chunk)
                output.flush()
        finally:
            response.close()
        return

    params = {
        **downloader.params,
        "continuedl": False,
        "nopart": True,
        "_no_ytdl_file": True,
        "external_downloader": "native",
    }
    sentinel = str(temp_dir / "native-output")

    def stop_when_cancelled(_status: dict[str, Any]) -> None:
        if cancelled.is_set():
            raise RuntimeError("Native media stream was cancelled")

    if protocol in {"m3u8", "m3u8_native"}:
        manifest, media_url = _resolve_media_manifest(downloader, url, headers)
        _parse_media_playlist(manifest, media_url)
        finite_info = {
            **info,
            "url": media_url,
            "protocol": "m3u8_native",
            "is_live": False,
            "hls_media_playlist_data": manifest,
            "http_headers": headers,
            "ext": info.get("ext") or "mp4",
        }
        if HlsFD._has_drm(manifest):
            raise ValueError("DRM-protected HLS streams are not supported")
        if not HlsFD.can_download(manifest, finite_info, False):
            raise ValueError("HLS playlist requires an unsupported external downloader")
        native_hls = _PipeHlsFD(downloader, params, sentinel, output)
        native_hls.add_progress_hook(stop_when_cancelled)
        if not native_hls.real_download(sentinel, finite_info):
            raise RuntimeError("Native HLS download failed")
        return

    if protocol in {"http_dash_segments", "http_dash_segments_generator"}:
        # The generator protocol forces DashSegmentsFD's native fragment path,
        # preventing its optional dash_frag_urls delegation.
        finite_info = _validated_dash_info({
            **info,
            "url": url,
            "protocol": "http_dash_segments_generator",
        })
        native_dash = _PipeDashFD(downloader, params, sentinel, output)
        native_dash.add_progress_hook(stop_when_cancelled)
        if not native_dash.real_download(sentinel, finite_info):
            raise RuntimeError("Native DASH download failed")
        return

    raise ValueError(f"Unsupported native media protocol: {protocol}")
