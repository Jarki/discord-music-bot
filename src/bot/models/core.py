"""Queue management for bot with support for multiple playback modes."""

import uuid
from enum import Enum

from pydantic import BaseModel, Field


class QueueMode(str, Enum):
    """Queue playback modes (mutually exclusive)."""

    NO_REPEAT = "no_repeat"
    REPEAT_QUEUE = "repeat_queue"
    REPEAT_SINGLE = "repeat_single"
    SHUFFLE = "shuffle"


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
