"""Dependencies for API routes."""

from fastapi import Depends

from src.api.dependencies.discovery_service import DiscoveryService
from src.api.dependencies.hyprctl_service import HyprctlService
from src.api.dependencies.pactl_service import PactlService
from src.api.dependencies.sink_manager import get_sink_manager
from src.shared.dependencies.virtual_sink import SinkManager

__all__ = [
    "get_discovery_service",
    "get_hyprctl_service",
    "get_pactl_service",
    "get_sink_manager",
]


def get_hyprctl_service() -> HyprctlService:
    """Create a new HyprctlService instance.

    This is a transient dependency - a new instance is created for each request.

    Returns:
        New HyprctlService instance
    """
    return HyprctlService()


def get_pactl_service() -> PactlService:
    """Create a new PactlService instance.

    This is a transient dependency - a new instance is created for each request.

    Returns:
        New PactlService instance
    """
    return PactlService()


def get_discovery_service(
    hyprctl: HyprctlService = Depends(get_hyprctl_service),
    pactl: PactlService = Depends(get_pactl_service),
    sink_manager: SinkManager = Depends(get_sink_manager),
) -> DiscoveryService:
    """Create a new DiscoveryService instance with its dependencies.

    This is a transient dependency that coordinates between multiple services.

    Args:
        hyprctl: HyprctlService dependency (injected)
        pactl: PactlService dependency (injected)
        sink_manager: SinkManager dependency (injected)

    Returns:
        New DiscoveryService instance
    """
    return DiscoveryService(
        hyprctl_service=hyprctl,
        pactl_service=pactl,
        sink_manager=sink_manager,
    )
