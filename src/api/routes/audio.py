"""Audio source discovery and routing endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_sink_manager
from src.shared.dependencies.virtual_sink import SinkManager

router = APIRouter()


@router.get("/audio-sources")
async def list_audio_sources(
    sink_manager: SinkManager = Depends(get_sink_manager),
) -> dict[str, Any]:
    """List available audio sources (applications playing audio).

    Args:
        sink_manager: SinkManager dependency (injected)

    Returns:
        List of audio sources with metadata (sink-input ID, application name, window title)

    TODO: Implement in Task 5 (Discovery Service)
    """
    # Stub implementation
    return {"sources": [], "message": "Discovery service not yet implemented"}


@router.post("/audio-sources/{sink_input_id}/select")
async def select_audio_source(
    sink_input_id: int, sink_manager: SinkManager = Depends(get_sink_manager)
) -> dict[str, Any]:
    """Route the selected audio source to the virtual sink.

    Args:
        sink_input_id: The sink-input ID to route (from pactl list sink-inputs)
        sink_manager: SinkManager dependency (injected)

    Returns:
        Success message with selected source info

    Raises:
        HTTPException: If sink_input_id is invalid or routing fails

    TODO: Implement in Task 5 (Discovery Service)
    """
    # Stub implementation
    if sink_input_id < 0:
        raise HTTPException(status_code=400, detail="Invalid sink_input_id")

    return {
        "success": True,
        "sink_input_id": sink_input_id,
        "message": "Discovery service not yet implemented",
    }


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status information about the API
    """
    return {"status": "healthy", "service": "loud-bot-api"}
