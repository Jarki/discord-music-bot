"""Pydantic models for PulseAudio/PipeWire sink-inputs."""

from typing import Annotated

from pydantic import BaseModel, Field


class SinkInput(BaseModel):
    """Represents a PulseAudio/PipeWire sink-input (application audio stream)."""

    sink_input_id: Annotated[
        int, Field(description="The sink-input index used for routing audio")
    ]
    pid: Annotated[int, Field(description="Process ID of the application")]
    application_name: Annotated[
        str, Field(description="Name of the application (e.g., 'Firefox', 'Spotify')")
    ]
