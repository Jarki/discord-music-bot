"""Bot dependencies and services."""

from .player import Player
from .player_manager import PlayerManager
from .queue import InMemoryQueueManager, QueueProtocol
from .ytdlp import YTDLSource

__all__ = [
    "InMemoryQueueManager",
    "Player",
    "PlayerManager",
    "QueueProtocol",
    "YTDLSource",
]


def get_in_memory_queue_manager() -> InMemoryQueueManager:
    """Provides an instance of InMemoryQueueManager."""
    return InMemoryQueueManager()
