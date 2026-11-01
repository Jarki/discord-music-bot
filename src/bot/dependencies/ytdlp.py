import asyncio
import os
import shutil
import tempfile
import threading
from itertools import islice
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urljoin, urlsplit

import discord
import yt_dlp
from yt_dlp.downloader import FFmpegFD, get_suitable_downloader
from yt_dlp.networking._requests import RequestsRH

from src.bot.dependencies.media_proxy import (
    MediaProxyScope,
    create_media_proxy_scope,
    validate_media_url,
)
from src.bot.models import PlaylistTrack, SearchResult, Track


def _proxy_options(scope: MediaProxyScope) -> dict[str, Any]:
    proxy_url = scope.proxy_url
    return {
        "format": "bestaudio/best",
        "extract_flat": "in_playlist",
        "playlistend": 100,
        "restrictfilenames": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "no_warnings": True,
        "check_formats": False,
        "default_search": "ytsearch5",
        "allowed_extractors": ["youtube", "youtube:search", "youtube:tab"],
        "proxy": proxy_url,
    }


class _PinnedRequestsRH(RequestsRH):  # type: ignore[misc]
    def _get_proxies(self, _request: Any) -> dict[str, str]:
        return self.proxies

    def _create_instance(self, *args: Any, **kwargs: Any) -> Any:
        session = super()._create_instance(*args, **kwargs)

        def validate_redirect(
            response: Any, *_hook_args: Any, **_hook_kwargs: Any
        ) -> None:
            location = response.headers.get("Location")
            if location is None:
                return
            if any(ord(character) < 32 or ord(character) == 127 for character in location):
                raise ValueError("Redirect contains control characters")
            parsed = urlsplit(location)
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("Redirect contains credentials")
            validate_media_url(urljoin(response.url, location), resolve=False)

        session.hooks["response"].append(validate_redirect)
        return session


class _RestrictedYoutubeDL(yt_dlp.YoutubeDL):  # type: ignore[misc]
    def __init__(
        self, params: dict[str, Any], scope: MediaProxyScope
    ) -> None:
        self._scope = scope
        super().__init__(params)

    def urlopen(self, request: Any) -> Any:
        raw_url = request if isinstance(request, str) else request.url
        validate_media_url(raw_url, resolve=False)
        return super().urlopen(request)

    def cancel(self) -> None:
        self._scope.cancel()

    def close(self) -> None:
        self._scope.close()
        super().close()

    def build_request_director(
        self, handlers: Any, preferences: Any = None
    ) -> Any:
        return super().build_request_director([_PinnedRequestsRH], preferences)

    def process_info(self, info_dict: dict[str, Any]) -> None:
        downloader = get_suitable_downloader(info_dict, self.params)
        if downloader is FFmpegFD:
            raise ValueError("External FFmpeg media downloading is not allowed")
        super().process_info(info_dict)


def _extract_info(
    value: str, downloader: _RestrictedYoutubeDL | None = None
) -> dict[str, Any]:
    owned = downloader is None
    if downloader is None:
        scope = create_media_proxy_scope()
        downloader = _RestrictedYoutubeDL(_proxy_options(scope), scope)
    try:
        data = downloader.extract_info(value, download=False, process=True)
    finally:
        if owned:
            downloader.close()
    if not isinstance(data, dict):
        raise ValueError("No YouTube metadata found")
    return data


def _validate_input(value: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Media input contains control characters")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return validate_media_url(value, resolve=False)
    if value.startswith(("/", "\\", ".")) or ":" in value:
        raise ValueError("Pseudo-protocols and local paths are not supported")
    return f"ytsearch5:{value}"


def _stable_youtube_url(entry: dict[str, Any], fallback: str | None = None) -> str:
    candidate = entry.get("webpage_url") or entry.get("url") or fallback
    if not isinstance(candidate, str):
        raise ValueError("No YouTube page URL found")
    return validate_media_url(candidate, resolve=False)


class _PipeFFmpegAudio(discord.FFmpegPCMAudio):
    def __init__(
        self,
        source: BinaryIO,
        cancelled: threading.Event,
        errors: list[BaseException],
        transports: list[_RestrictedYoutubeDL],
    ) -> None:
        self._cancelled = cancelled
        self._errors = errors
        self._input = source
        self._transports = transports
        args = [
            "-protocol_whitelist",
            "pipe",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-loglevel",
            "warning",
            "-vn",
            "pipe:1",
        ]
        discord.FFmpegAudio.__init__(
            self, "pipe:0", args=args, stdin=source
        )

    def read(self) -> bytes:
        data = super().read()
        if not data and self._errors:
            raise self._errors[0]
        return data

    def cleanup(self) -> None:
        self._cancelled.set()
        for downloader in tuple(self._transports):
            downloader.cancel()
            downloader.close()
        super().cleanup()
        self._input.close()


def _stream_worker(
    downloader: _RestrictedYoutubeDL,
    info: dict[str, Any],
    output: BinaryIO,
    cancelled: threading.Event,
    directory: Path,
    errors: list[BaseException],
    transports: list[_RestrictedYoutubeDL],
) -> None:
    try:
        from src.bot.dependencies.live_hls import stream_live_hls, stream_native

        try:
            protocol = info.get("protocol")
            if info.get("is_live") and protocol in {"m3u8", "m3u8_native"}:
                stream_live_hls(downloader, info, output, cancelled, directory)
            else:
                stream_native(downloader, info, output, cancelled, directory)
        finally:
            downloader.cancel()
            downloader.close()
            transports.remove(downloader)
    except BaseException as error:
        errors.append(error)
        cancelled.set()
    finally:
        output.close()
        shutil.rmtree(directory, ignore_errors=True)

def _ffmpeg_headers_option(headers: Mapping[str, str] | None) -> str:
    if not headers:
        return ""

    lines: list[str] = []
    for name, value in headers.items():
        if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            raise ValueError("HTTP header names and values cannot contain CR or LF")
        lines.append(f"{name}: {value}")

    header_block = "\r\n".join(lines) + "\r\n"
    return f" -headers {shlex.quote(header_block)}"


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.FFmpegPCMAudio, *, volume: float = 0.5) -> None:
        super().__init__(source, volume)

    @classmethod
    async def stream_from_url(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> "YTDLSource":
        """Stream yt-dlp's restricted transport into network-disabled FFmpeg."""
        validate_media_url(url, resolve=False)
        loop = loop or asyncio.get_event_loop()
        scope = create_media_proxy_scope()
        downloader = _RestrictedYoutubeDL(_proxy_options(scope), scope)
        try:
            info = await loop.run_in_executor(None, _extract_info, url, downloader)
        except BaseException:
            downloader.cancel()
            downloader.close()
            raise
        directory: Path | None = None
        source: BinaryIO | None = None
        output: BinaryIO | None = None
        cancelled = threading.Event()
        errors: list[BaseException] = []
        transports = [downloader]
        worker_started = False
        try:
            directory = Path(tempfile.mkdtemp(prefix="loud-bot-media-"))
            read_fd, write_fd = os.pipe()
            try:
                source = os.fdopen(read_fd, "rb", buffering=0)
                read_fd = -1
                output = os.fdopen(write_fd, "wb", buffering=0)
                write_fd = -1
            finally:
                if read_fd >= 0:
                    os.close(read_fd)
                if write_fd >= 0:
                    os.close(write_fd)
            worker = threading.Thread(
                target=_stream_worker,
                args=(
                    downloader,
                    info,
                    output,
                    cancelled,
                    directory,
                    errors,
                    transports,
                ),
                name="youtube-media-stream",
                daemon=True,
            )
            worker.start()
            worker_started = True
            return cls(_PipeFFmpegAudio(source, cancelled, errors, transports))
        except BaseException:
            cancelled.set()
            downloader.cancel()
            if source is not None:
                source.close()
            if output is not None and not worker_started:
                output.close()
            if directory is not None and not worker_started:
                shutil.rmtree(directory, ignore_errors=True)
            if not worker_started:
                downloader.close()
            raise

    @classmethod
    async def get_tracks_info(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> Track | list[PlaylistTrack] | list[SearchResult]:
        """Load and validate YouTube queue metadata."""
        url = _validate_input(url)
        loop = loop or asyncio.get_event_loop()
        scope = create_media_proxy_scope()
        downloader = _RestrictedYoutubeDL(_proxy_options(scope), scope)
        try:
            data = await loop.run_in_executor(None, _extract_info, url, downloader)
        finally:
            downloader.cancel()
            downloader.close()

        if data.get("extractor") == "youtube:search":
            entries = data.get("entries")
            if entries is None:
                raise ValueError("No entries found in YouTube search data")
            results = [
                SearchResult(
                    title=entry.get("title") or "Unknown Title",
                    url=_stable_youtube_url(entry),
                    author_name=entry.get("uploader"),
                    duration=int(entry.get("duration") or 0),
                )
                for entry in islice(entries, 5)
                if isinstance(entry, dict)
                and (entry.get("webpage_url") or entry.get("url"))
            ]
            return results

        if data.get("extractor") not in {"youtube", "youtube:tab"}:
            raise ValueError("Only YouTube extractors are supported")
        if "entries" in data:
            return [
                PlaylistTrack(yt_url=_stable_youtube_url(entry))
                for entry in islice(data["entries"], 100)
                if isinstance(entry, dict)
                and (entry.get("webpage_url") or entry.get("url"))
            ]

        return Track(
            type="youtube",
            title=data.get("title") or "Unknown Title",
            url=_stable_youtube_url(data, url),
            thumbnail_url=data.get("thumbnail"),
            author_name=data.get("uploader"),
            duration=int(data.get("duration") or 0),
        )
