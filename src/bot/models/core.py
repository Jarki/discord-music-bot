"""Queue management for bot with support for multiple playback modes."""

import uuid
from enum import Enum

from discord import app_commands
from pydantic import BaseModel, Field


class QueueMode(str, Enum):
    """Queue playback modes (mutually exclusive)."""

    NO_REPEAT = "no_repeat"
    REPEAT_QUEUE = "repeat_queue"
    REPEAT_SINGLE = "repeat_single"
    SHUFFLE = "shuffle"

    @staticmethod
    def _format_name(value: str) -> str:
        """Convert snake_case to Title Case with emoji"""
        emoji_map = {
            "no_repeat": "🔁",
            "repeat_queue": "🔂",
            "repeat_single": "🔂",
            "shuffle": "🔀",
        }
        emoji = emoji_map.get(value, "")
        title = value.replace("_", " ").title()
        return f"{emoji} {title}".strip()

    @classmethod
    def choices(cls) -> list[app_commands.Choice[str]]:
        """Generate user-friendly choices automatically"""
        return [
            app_commands.Choice(name=cls._format_name(mode.value), value=mode.value)
            for mode in cls
        ]


class Track(BaseModel):
    """Represents a single item in the queue."""

    type: str
    title: str
    url: str
    track_id: str = Field(
        description="Unique identifier for this queue item",
        default_factory=lambda: str(uuid.uuid4()),
    )
    thumbnail_url: str | None = None
    author_name: str | None = None
    duration: int = 0  # Duration in seconds


class PlaylistTrack(BaseModel):
    """Represents a track within a playlist context. Data needs to be loaded"""

    yt_url: str


class SearchResult(BaseModel):
    """Represents a search result item."""

    title: str
    url: str
    author_name: str | None = None
    duration: int = 0  # Duration in seconds


class QueueModel(BaseModel):
    """Complete state of a queue including items, cursor, and mode."""

    queue_id: str
    items: list[Track] = Field(default_factory=list)
    cursor: int = Field(
        default=-1, description="Current position in queue (-1 = before start)"
    )
    mode: QueueMode = Field(default=QueueMode.NO_REPEAT)
    shuffle_order: list[int] = Field(
        default_factory=list,
        description="Shuffled indices when in shuffle mode",
    )
