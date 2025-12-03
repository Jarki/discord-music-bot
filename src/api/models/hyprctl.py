"""Pydantic models for Hyprland client information."""

from typing import Annotated

from pydantic import BaseModel, Field


class HyprlandClient(BaseModel):
    """Represents a Hyprland window client."""

    pid: Annotated[int, Field(..., description="Process ID of the window")]
    title: Annotated[str, Field(..., description="Window title")]
