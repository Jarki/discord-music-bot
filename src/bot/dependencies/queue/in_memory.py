import random

from src.bot.models import QueueMode, QueueModel, Track


class InMemoryQueueManager:
    """In-memory queue management with support for multiple queues."""

    MAX_QUEUE_SIZE = 256

    def __init__(self) -> None:
        """Initialize the queue manager with empty storage."""
        self._queues: dict[str, QueueModel] = {}

    def queue_item(self, queue_id: str, track: Track) -> Track:
        if queue_id not in self._queues:
            self._queues[queue_id] = QueueModel(queue_id=queue_id)

        queue = self._queues[queue_id]

        # Check capacity
        if len(queue.items) >= self.MAX_QUEUE_SIZE:
            raise RuntimeError("Queue is at maximum capacity")

        # Create and append entry
        queue.items.append(track)

        # If in shuffle mode and shuffle_order exists, append new index
        if queue.mode == QueueMode.SHUFFLE and queue.shuffle_order:
            queue.shuffle_order.append(len(queue.items) - 1)

        return track

    def remove_item(self, queue_id: str, item_id: str) -> None:
        """Remove specific item from queue.

        Args:
            queue_id: Identifier for the queue
            item_id: ID of the item to remove

        Raises:
            RuntimeError: If queue or item not found
        """
        if queue_id not in self._queues:
            raise RuntimeError(f"Queue not found: {queue_id}")

        queue = self._queues[queue_id]

        # Find item index
        item_index = None
        for i, track in enumerate(queue.items):
            if track.track_id == item_id:
                item_index = i
                break

        if item_index is None:
            raise RuntimeError(f"Item not found: {item_id}")

        # Remove item
        queue.items.pop(item_index)

        # Adjust cursor
        if queue.cursor >= item_index:
            queue.cursor -= 1
            if queue.cursor < -1:
                queue.cursor = -1

        # Adjust shuffle_order if in shuffle mode
        if queue.mode == QueueMode.SHUFFLE and queue.shuffle_order:
            # Remove the deleted index and adjust remaining indices
            new_shuffle_order = []
            for idx in queue.shuffle_order:
                if idx < item_index:
                    new_shuffle_order.append(idx)
                elif idx > item_index:
                    new_shuffle_order.append(idx - 1)
                # Skip idx == item_index (it's being removed)
            queue.shuffle_order = new_shuffle_order

    def get_item(self, queue_id: str, item_id: str) -> Track:
        """Get specific item by ID.

        Args:
            queue_id: Identifier for the queue
            item_id: ID of the item to retrieve

        Returns:
            The queue entry with matching item_id

        Raises:
            RuntimeError: If queue or item not found
        """
        if queue_id not in self._queues:
            raise RuntimeError(f"Queue not found: {queue_id}")

        queue = self._queues[queue_id]

        for track in queue.items:
            if track.track_id == item_id:
                return track

        raise RuntimeError(f"Item not found: {item_id}")

    def find_items(self, queue_id: str, title: str) -> list[Track]:
        """Find all items matching title (case-insensitive partial match).

        Args:
            queue_id: Identifier for the queue
            title: Title search string

        Returns:
            List of all matching queue entries (empty if queue doesn't exist)
        """
        if queue_id not in self._queues:
            return []

        queue = self._queues[queue_id]
        title_lower = title.lower()

        return [track for track in queue.items if title_lower in track.title.lower()]

    def reset_queue(self, queue_id: str) -> None:
        """Clear all items from queue (idempotent).

        Args:
            queue_id: Identifier for the queue
        """
        if queue_id not in self._queues:
            return  # Idempotent - safe to call on non-existent queue

        queue = self._queues[queue_id]
        queue.items = []
        queue.cursor = -1
        queue.shuffle_order = []

    def get_all_items(self, queue_id: str) -> list[Track]:
        """Get all items in queue.

        Args:
            queue_id: Identifier for the queue

        Returns:
            List of all queue entries (empty if queue doesn't exist)
        """
        if queue_id not in self._queues:
            return []

        return self._queues[queue_id].items.copy()

    def get_next(self, queue_id: str) -> Track:
        """Advance cursor and return next item.

        Behavior depends on current mode:
        - NO_REPEAT: Advance cursor, raise error at end
        - REPEAT_QUEUE: Advance cursor with wraparound
        - REPEAT_SINGLE: Return same item without advancing
        - SHUFFLE: Navigate through shuffle_order with wraparound

        Args:
            queue_id: Identifier for the queue

        Returns:
            The next queue entry based on current mode

        Raises:
            RuntimeError: If queue not found, empty queue, or no next item
                         (NO_REPEAT mode only)
        """
        if queue_id not in self._queues:
            raise RuntimeError(f"Queue not found: {queue_id}")

        queue = self._queues[queue_id]

        if not queue.items:
            raise RuntimeError("Cannot navigate empty queue")

        if queue.mode == QueueMode.NO_REPEAT:
            if queue.cursor >= len(queue.items) - 1:
                raise RuntimeError("No next item available")
            queue.cursor += 1
            return queue.items[queue.cursor]

        elif queue.mode == QueueMode.REPEAT_QUEUE:
            queue.cursor += 1
            if queue.cursor >= len(queue.items):
                queue.cursor = 0
            return queue.items[queue.cursor]

        elif queue.mode == QueueMode.REPEAT_SINGLE:
            if queue.cursor == -1 and len(queue.items) > 0:
                queue.cursor = 0
            if 0 <= queue.cursor < len(queue.items):
                return queue.items[queue.cursor]
            raise RuntimeError("No item to repeat")

        elif queue.mode == QueueMode.SHUFFLE:
            # Initialize shuffle_order if not present
            if not queue.shuffle_order:
                queue.shuffle_order = list(range(len(queue.items)))
                random.shuffle(queue.shuffle_order)

            queue.cursor += 1
            if queue.cursor >= len(queue.shuffle_order):
                queue.cursor = 0

            actual_index = queue.shuffle_order[queue.cursor]
            return queue.items[actual_index]

        raise RuntimeError(f"Unknown queue mode: {queue.mode}")

    def get_prev(self, queue_id: str) -> Track:
        """Move cursor back and return previous item.

        Behavior depends on current mode:
        - NO_REPEAT: Move cursor back, raise error at start
        - REPEAT_QUEUE: Move cursor back with wraparound
        - REPEAT_SINGLE: Return same item without moving
        - SHUFFLE: Navigate backwards through shuffle_order with wraparound

        Args:
            queue_id: Identifier for the queue

        Returns:
            The previous queue entry based on current mode

        Raises:
            RuntimeError: If queue not found, empty queue, or no previous item
                         (NO_REPEAT mode only)
        """
        if queue_id not in self._queues:
            raise RuntimeError(f"Queue not found: {queue_id}")

        queue = self._queues[queue_id]

        if not queue.items:
            raise RuntimeError("Cannot navigate empty queue")

        if queue.mode == QueueMode.NO_REPEAT:
            if queue.cursor <= 0:
                raise RuntimeError("No previous item available")
            queue.cursor -= 1
            return queue.items[queue.cursor]

        elif queue.mode == QueueMode.REPEAT_QUEUE:
            queue.cursor -= 1
            if queue.cursor < 0:
                queue.cursor = len(queue.items) - 1
            return queue.items[queue.cursor]

        elif queue.mode == QueueMode.REPEAT_SINGLE:
            if queue.cursor == -1 and len(queue.items) > 0:
                queue.cursor = 0
            if 0 <= queue.cursor < len(queue.items):
                return queue.items[queue.cursor]
            raise RuntimeError("No item to repeat")

        elif queue.mode == QueueMode.SHUFFLE:
            if not queue.shuffle_order:
                raise RuntimeError("Cannot go back, shuffle not initialized")

            if queue.cursor <= 0:
                queue.cursor = len(queue.shuffle_order) - 1
            else:
                queue.cursor -= 1

            actual_index = queue.shuffle_order[queue.cursor]
            return queue.items[actual_index]

        raise RuntimeError(f"Unknown queue mode: {queue.mode}")

    def set_mode(self, queue_id: str, mode: QueueMode) -> None:
        """Set queue playback mode.

        When switching to SHUFFLE mode, creates a new shuffled order.
        When switching from SHUFFLE, clears the shuffle order.

        Args:
            queue_id: Identifier for the queue
            mode: The playback mode to set

        Raises:
            RuntimeError: If queue not found
        """
        if queue_id not in self._queues:
            raise RuntimeError(f"Queue not found: {queue_id}")

        queue = self._queues[queue_id]

        if queue.mode == mode:
            return  # No-op if already in this mode

        queue.mode = mode

        if mode == QueueMode.SHUFFLE:
            # Create new shuffle order
            queue.shuffle_order = list(range(len(queue.items)))
            random.shuffle(queue.shuffle_order)
            queue.cursor = -1
        else:
            # Clear shuffle order when leaving shuffle mode
            queue.shuffle_order = []

    def get_current_position(self, queue_id: str) -> int:
        """Get current cursor position.

        Args:
            queue_id: Identifier for the queue

        Returns:
            The current cursor position (-1 if before start)

        Raises:
            RuntimeError: If queue not found
        """
        if queue_id not in self._queues:
            raise RuntimeError(f"Queue not found: {queue_id}")

        return self._queues[queue_id].cursor
