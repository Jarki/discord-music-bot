import asyncio
import subprocess
from typing import Any

import discord
import yt_dlp

from src.bot.models import PlaylistTrack, SearchResult, Track

ytdl_format_options: dict[str, Any] = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "extract_flat": "in_playlist",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch5",
    "source_address": "0.0.0.0",  # bind to ipv4 since ipv6 addresses cause issues sometimes
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)  # type: ignore


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source: discord.FFmpegPCMAudio, *, volume: float = 0.5) -> None:
        super().__init__(source, volume)

    @classmethod
    async def stream_from_url(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> YTDLSource:
        """Resolve a fresh media URL immediately before starting playback."""
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=False, process=True)
        )
        stream_url = data.get("url")
        if not stream_url:
            raise ValueError("No media URL found in YouTube DL data")

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn",
            "stderr": subprocess.PIPE,
        }

        return cls(discord.FFmpegPCMAudio(stream_url, **ffmpeg_options))

    @classmethod
    async def get_tracks_info(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> Track | list[PlaylistTrack] | list[SearchResult]:
        """Load queue metadata while retaining stable track/page URLs."""
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=False, process=True)
        )

        if data.get("extractor") == "youtube:search":
            # Search results
            results = []
            if "entries" not in data:
                raise ValueError("No entries found in YouTube search data")
            entries: list[dict] = data["entries"]

            for entry in entries:
                track_url = entry.get("webpage_url") or entry.get("url")
                if track_url is None:
                    continue

                sr = SearchResult(
                    title=entry.get("title") or "Unknown Title",
                    url=track_url,
                    author_name=entry.get("uploader"),
                    duration=int(entry.get("duration") or 0),
                )
                results.append(sr)
            if len(results) == 1:
                return results[0]
            return results

        if "entries" in data:
            # Playlist
            tracks = []
            for entry in data["entries"]:
                track_url = entry.get("webpage_url") or entry.get("url")
                if track_url is None:
                    continue

                pt = PlaylistTrack(yt_url=track_url)
                tracks.append(pt)
            return tracks

        playable = Track(
            type=str(data.get("extractor")) or "unknown",
            title=data.get("title") or "Unknown Title",
            url=data.get("webpage_url") or url,
            thumbnail_url=data.get("thumbnail"),
            author_name=data.get("uploader"),
            duration=int(data.get("duration") or 0),
        )
        return playable
