"""Voice-channel authorization regressions for music commands."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_mock import MockerFixture

from src.bot.client import Music
from src.bot.models.core import SearchResult, Track


class TextChannel:
    """Runtime stand-in used by the context decorator's channel check."""


class Response:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.messages: list[str] = []
        self.done = False

    async def send_message(self, content: str, **kwargs: Any) -> None:
        self.events.append("respond")
        self.messages.append(content)
        self.done = True

    async def defer(self, **kwargs: Any) -> None:
        self.events.append("defer")
        self.done = True

    def is_done(self) -> bool:
        return self.done


def interaction(
    mocker: MockerFixture,
    *,
    bot_channel: Any = None,
    author_channel: Any = None,
    events: list[str] | None = None,
) -> SimpleNamespace:
    events = events if events is not None else []
    voice_client = None
    if bot_channel is not None:
        voice_client = SimpleNamespace(
            channel=bot_channel,
            is_connected=lambda: True,
            disconnect=mocker.AsyncMock(
                side_effect=lambda **_: events.append("disconnect")
            ),
        )
    return SimpleNamespace(
        guild=SimpleNamespace(id=123, voice_client=voice_client),
        user=SimpleNamespace(
            voice=(
                SimpleNamespace(channel=author_channel)
                if author_channel is not None
                else None
            )
        ),
        channel=TextChannel(),
        response=Response(events),
        followup=SimpleNamespace(send=mocker.AsyncMock()),
        edit_original_response=mocker.AsyncMock(),
        delete_original_response=mocker.AsyncMock(),
    )


def music_with_player(mocker: MockerFixture, player: Any) -> Music:
    music = Music(mocker.Mock())
    manager = SimpleNamespace(
        get_or_create_player=mocker.Mock(return_value=player),
        get_player=mocker.Mock(return_value=player),
        remove_player=mocker.Mock(),
    )
    music.player_manager = manager
    return music


@pytest.fixture(autouse=True)
def context_types(mocker: MockerFixture) -> None:
    mocker.patch("src.bot.client.discord.TextChannel", TextChannel)
    mocker.patch(
        "src.bot.client.MusicPlayerContext",
        side_effect=lambda **values: SimpleNamespace(**values),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["clear", "pause"])
async def test_outsider_cannot_mutate_active_session(
    mocker: MockerFixture, command: str
) -> None:
    bot_channel = object()
    request = interaction(mocker, bot_channel=bot_channel, author_channel=object())
    player = mocker.Mock()
    music = music_with_player(mocker, player)

    await getattr(Music, command).callback(music, request)

    assert request.response.messages == [
        "❌ You must be in the bot's voice channel to use this command."
    ]
    player.clear_queue.assert_not_called()
    player.pause.assert_not_called()


@pytest.mark.asyncio
async def test_outsider_cannot_leave_active_session(mocker: MockerFixture) -> None:
    request = interaction(mocker, bot_channel=object(), author_channel=object())
    player = mocker.Mock()
    music = music_with_player(mocker, player)

    await Music.leave.callback(music, request)

    request.guild.voice_client.disconnect.assert_not_awaited()
    player.clear_queue.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["queue", "current"])
async def test_read_only_commands_neither_join_nor_require_voice(
    mocker: MockerFixture, command: str
) -> None:
    request = interaction(mocker)
    player = mocker.Mock(current_track=None)
    player.get_all.return_value = []
    music = music_with_player(mocker, player)

    await getattr(Music, command).callback(music, request)

    assert request.response.done
    assert request.guild.voice_client is None


@pytest.mark.asyncio
async def test_disconnected_voice_client_is_treated_as_absent(
    mocker: MockerFixture,
) -> None:
    request = interaction(mocker, bot_channel=object(), author_channel=object())
    request.guild.voice_client.is_connected = lambda: False
    music = music_with_player(mocker, mocker.Mock())

    await Music.clear.callback(music, request)

    assert request.response.messages == [
        "❌ The bot is not connected to a voice channel."
    ]


@pytest.mark.asyncio
async def test_join_acknowledges_before_connect(mocker: MockerFixture) -> None:
    events: list[str] = []
    voice_client = SimpleNamespace(channel=None, is_connected=lambda: True)

    async def connect() -> Any:
        events.append("connect")
        return voice_client

    channel = SimpleNamespace(connect=connect)
    voice_client.channel = channel
    request = interaction(mocker, author_channel=channel, events=events)
    music = music_with_player(mocker, mocker.Mock())

    await Music.join.callback(music, request)

    assert events == ["defer", "connect"]
    request.edit_original_response.assert_awaited_once_with(
        content="Joined voice channel!"
    )


@pytest.mark.asyncio
async def test_join_never_moves_active_bot(mocker: MockerFixture) -> None:
    request = interaction(mocker, bot_channel=object(), author_channel=object())
    request.guild.voice_client.move_to = mocker.AsyncMock()
    music = music_with_player(mocker, mocker.Mock())

    await Music.join.callback(music, request)

    request.guild.voice_client.move_to.assert_not_awaited()


@pytest.mark.asyncio
async def test_play_autojoins_disconnected_after_acknowledgement(
    mocker: MockerFixture,
) -> None:
    events: list[str] = []
    voice_client = SimpleNamespace(channel=None, is_connected=lambda: True)

    async def connect() -> Any:
        events.append("connect")
        return voice_client

    channel = SimpleNamespace(connect=connect)
    voice_client.channel = channel
    request = interaction(mocker, author_channel=channel, events=events)
    music = music_with_player(mocker, mocker.Mock())
    mocker.patch(
        "src.bot.client.YTDLSource.get_tracks_info",
        return_value=[],
    )

    await Music.play.callback(music, request, "query")

    assert events == ["defer", "connect"]


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["join", "play"])
async def test_retained_disconnected_client_is_torn_down_before_reconnect(
    mocker: MockerFixture, command: str
) -> None:
    events: list[str] = []
    channel = SimpleNamespace()

    async def connect() -> Any:
        events.append("connect")
        return SimpleNamespace(channel=channel, is_connected=lambda: True)

    channel.connect = connect
    request = interaction(
        mocker, bot_channel=object(), author_channel=channel, events=events
    )
    request.guild.voice_client.is_connected = lambda: False
    music = music_with_player(mocker, mocker.Mock())
    mocker.patch("src.bot.client.YTDLSource.get_tracks_info", return_value=[])

    await getattr(Music, command).callback(
        music, request, *(("query",) if command == "play" else ())
    )

    assert events[:3] == ["defer", "disconnect", "connect"]


@pytest.mark.asyncio
async def test_leave_disconnected_does_not_join(mocker: MockerFixture) -> None:
    channel = SimpleNamespace(connect=mocker.AsyncMock())
    request = interaction(mocker, author_channel=channel)
    music = music_with_player(mocker, mocker.Mock())

    await Music.leave.callback(music, request)

    channel.connect.assert_not_awaited()
    assert request.response.messages == ["Not in a voice channel."]


@pytest.mark.asyncio
async def test_leave_acknowledges_and_clears_before_disconnect(
    mocker: MockerFixture,
) -> None:
    events: list[str] = []
    channel = object()
    request = interaction(
        mocker, bot_channel=channel, author_channel=channel, events=events
    )
    player = mocker.Mock()
    player.clear_queue.side_effect = lambda: events.append("clear")
    music = music_with_player(mocker, player)

    await Music.leave.callback(music, request)

    assert events == ["defer", "clear", "disconnect"]
    request.edit_original_response.assert_awaited_once_with(
        content="Left voice channel!"
    )
    music.player_manager.remove_player.assert_called_once_with("123")


@pytest.mark.asyncio
async def test_stale_search_result_cannot_queue_after_leave_and_reconnect(
    mocker: MockerFixture,
) -> None:
    stale_player = mocker.Mock()
    stale_player.add_track = mocker.AsyncMock()
    replacement_player = mocker.Mock()
    manager = SimpleNamespace(
        get_player=mocker.Mock(return_value=replacement_player),
    )
    context = SimpleNamespace(
        guild_id="123",
        player=stale_player,
        player_manager=manager,
        interaction=SimpleNamespace(followup=SimpleNamespace(send=mocker.AsyncMock())),
    )
    music = Music(mocker.Mock())
    track = mocker.Mock()

    result = await music._queue_track_and_play_maybe(context, track)

    assert result is None
    stale_player.add_track.assert_not_awaited()
    context.interaction.followup.send.assert_awaited_once_with(
        content="Playback request expired after leaving the voice channel.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_disconnected_leave_invalidates_suspended_search_after_reconnect(
    mocker: MockerFixture,
) -> None:
    release = asyncio.Event()
    old_player = mocker.Mock()
    old_player.add_track = mocker.AsyncMock()
    music = music_with_player(mocker, old_player)
    manager = music.player_manager
    manager.remove_player.side_effect = lambda _: manager.get_player.configure_mock(
        return_value=None
    )
    channel = object()
    request = interaction(mocker, bot_channel=channel, author_channel=channel)
    request.guild.voice_client.is_connected = lambda: False
    context = SimpleNamespace(
        guild_id="123",
        player=old_player,
        player_manager=manager,
        interaction=SimpleNamespace(
            followup=SimpleNamespace(send=mocker.AsyncMock()),
            channel=TextChannel(),
        ),
        author=mocker.Mock(),
    )
    track = Track(type="youtube", title="result", url="https://example.test")

    async def suspended_extract(*args: Any, **kwargs: Any) -> Track:
        await release.wait()
        return track

    mocker.patch(
        "src.bot.client.YTDLSource.get_tracks_info",
        side_effect=suspended_extract,
    )
    pending = asyncio.create_task(
        music._handle_search_result_selection(
            context,
            SearchResult(title="result", url="https://example.test"),
        )
    )
    await asyncio.sleep(0)

    await Music.leave.callback(music, request)
    replacement = mocker.Mock()
    manager.get_player.return_value = replacement
    release.set()
    await pending

    old_player.add_track.assert_not_awaited()
    replacement.add_track.assert_not_called()


@pytest.mark.asyncio
async def test_skip_does_not_mutate_replacement_session_after_defer(
    mocker: MockerFixture,
) -> None:
    defer_started = asyncio.Event()
    resume_defer = asyncio.Event()
    channel = object()
    request = interaction(mocker, bot_channel=channel, author_channel=channel)

    async def suspended_defer(**_: Any) -> None:
        defer_started.set()
        await resume_defer.wait()
        request.response.done = True

    request.response.defer = mocker.AsyncMock(side_effect=suspended_defer)
    old_player = SimpleNamespace(
        is_playing=mocker.Mock(return_value=True),
        is_paused=False,
        skip_tracks=mocker.AsyncMock(),
    )
    queued_track = object()
    replacement_track = object()
    replacement_player = SimpleNamespace(
        queue=[queued_track],
        current_track=replacement_track,
        skip_tracks=mocker.AsyncMock(),
    )
    music = music_with_player(mocker, old_player)
    manager = music.player_manager

    pending = asyncio.create_task(Music.skip.callback(music, request, 1))
    await defer_started.wait()
    manager.get_player.return_value = replacement_player
    resume_defer.set()
    await pending

    old_player.skip_tracks.assert_not_awaited()
    replacement_player.skip_tracks.assert_not_awaited()
    assert replacement_player.queue == [queued_track]
    assert replacement_player.current_track is replacement_track
    request.delete_original_response.assert_awaited_once_with()
    request.followup.send.assert_awaited_once_with(
        "Skip request expired after leaving the voice channel.",
        ephemeral=True,
    )
