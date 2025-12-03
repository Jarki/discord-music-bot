"""Audio source discovery and routing endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_discovery_service
from src.api.dependencies.discovery_service import DiscoveryService

router = APIRouter()


@router.get("/audio-sources")
async def list_audio_sources(
    discovery_service: DiscoveryService = Depends(get_discovery_service),
) -> dict[str, Any]:
    """List available audio sources (applications playing audio).

    Args:
        discovery_service: DiscoveryService dependency (injected)

    Returns:
        List of audio sources with metadata (sink-input ID, application name, window title)

    Raises:
        HTTPException: If audio source discovery fails
    """
    try:
        sources = discovery_service.discover_sources()
        return {"sources": [source.model_dump() for source in sources]}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/audio-sources/{sink_input_id}/select")
async def select_audio_source(
    sink_input_id: int,
    discovery_service: DiscoveryService = Depends(get_discovery_service),
) -> dict[str, Any]:
    """Route the selected audio source to the virtual sink.

    Args:
        sink_input_id: The sink-input ID to route (from pactl list sink-inputs)
        discovery_service: DiscoveryService dependency (injected)

    Returns:
        Success message with selected source info

    Raises:
        HTTPException: If sink_input_id is invalid or routing fails
    """
    if sink_input_id < 0:
        raise HTTPException(status_code=400, detail="Invalid sink_input_id")

    try:
        discovery_service.select_source(sink_input_id)
        return {
            "success": True,
            "sink_input_id": sink_input_id,
            "message": "Audio source routed to virtual sink",
        }
    except RuntimeError as e:
        # Could be invalid sink_input_id or routing failure
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status information about the API
    """
    return {"status": "healthy", "service": "loud-bot-api"}
