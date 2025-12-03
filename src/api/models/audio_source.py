"""Pydantic model for audio source discovery with window titles."""

from typing import Annotated

from pydantic import BaseModel, Field


class AudioSource(BaseModel):
    """Represents an audio source with window information.

    Combines sink-input data from PulseAudio/PipeWire with window
    title information from Hyprland, matched by process ID.
    """

    sink_input_id: Annotated[
        int, Field(description="The sink-input index used for routing audio")
    ]
    pid: Annotated[int, Field(description="Process ID of the application")]
    application_name: Annotated[
        str, Field(description="Name of the application (e.g., 'Firefox', 'Spotify')")
    ]
    window_title: Annotated[
        str | None,
        Field(description="Window title from Hyprland (None if no match found)"),
    ]
