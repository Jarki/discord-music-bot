from typing import Protocol

from src.bot.models import QueueMode, Track


class QueueProtocol(Protocol):
    """Protocol defining the queue interface."""

    def queue_item(self, queue_id: str, track: Track) -> Track:
        """Add item to queue. Returns the queue entry."""
        ...

    def remove_item(self, queue_id: str, item_id: str) -> None:
        """Remove specific item from queue."""
        ...

    def get_item(self, queue_id: str, item_id: str) -> Track:
        """Get specific item by ID."""
        ...

    def find_items(self, queue_id: str, title: str) -> list[Track]:
        """Find all items matching title (partial or exact)."""
        ...

    def reset_queue(self, queue_id: str) -> None:
        """Clear all items from queue."""
        ...

    def get_all_items(self, queue_id: str) -> list[Track]:
        """Get all items in queue."""
        ...

    def get_next(self, queue_id: str, force_skip: bool = False) -> Track:
        """Advance cursor and return next item."""
        ...

    def get_prev(self, queue_id: str) -> Track:
        """Move cursor back and return previous item."""
        ...

    def set_mode(self, queue_id: str, mode: QueueMode) -> None:
        """Set queue playback mode."""
        ...

    def get_current_position(self, queue_id: str) -> int:
        """Get current cursor position."""
        ...
