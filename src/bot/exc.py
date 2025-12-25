class QueueEndError(Exception):
    """Raised when trying to add an item to a full queue."""

    pass


class NoVoiceChannelError(Exception):
    """Raised when the bot is not connected to a voice channel."""

    pass
