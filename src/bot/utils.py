from src.bot.models import Track


def tracks_to_pages(tracks: list[Track], songs_per_page: int = 10) -> list[str]:
    """Split a list of tracks into pages.

    Args:
        tracks: List of tracks to split
        songs_per_page: Number of tracks per page

    Returns:
        List of pages, each containing a list of tracks
    """
    lines = [f"{i}: {track.title}" for i, track in enumerate(tracks, start=1)]
    return [
        "\n".join(lines[i : i + songs_per_page])
        for i in range(0, len(lines), songs_per_page)
    ]
