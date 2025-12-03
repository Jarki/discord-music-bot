"""Discovery service for orchestrating audio source discovery and routing."""

import logging

from src.api.dependencies.hyprctl_service import HyprctlService
from src.api.dependencies.pactl_service import PactlService
from src.api.models.audio_source import AudioSource
from src.shared.dependencies.virtual_sink import SinkManager

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Orchestrates audio source discovery and routing.

    Coordinates between HyprctlService (window titles), PactlService (audio
    sink-inputs), and SinkManager (audio routing) to discover audio sources
    with window information and route them to the virtual sink.
    """

    def __init__(
        self,
        hyprctl_service: HyprctlService,
        pactl_service: PactlService,
        sink_manager: SinkManager,
    ) -> None:
        """Initialize the discovery service.

        Args:
            hyprctl_service: Service for querying Hyprland window information
            pactl_service: Service for querying PulseAudio/PipeWire sink-inputs
            sink_manager: Manager for virtual sink operations
        """
        self.hyprctl_service = hyprctl_service
        self.pactl_service = pactl_service
        self.sink_manager = sink_manager

    def discover_sources(self) -> list[AudioSource]:
        """Discover all audio sources with window titles.

        Fetches sink-inputs from pactl and matches them with window titles
        from hyprctl by process ID. If hyprctl fails or a PID has no matching
        window, window_title will be None.

        Returns:
            List of AudioSource models with matched window information

        Raises:
            RuntimeError: If pactl service fails (can't discover without audio data)
        """
        # Get sink-inputs from pactl - this is essential, so raise if it fails
        try:
            sink_inputs = self.pactl_service.get_sink_inputs()
        except Exception as e:
            error_msg = f"Failed to get sink-inputs from pactl: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        # Try to get window titles from hyprctl, but continue if it fails
        pid_to_title: dict[int, str] = {}
        try:
            clients = self.hyprctl_service.get_clients()
            pid_to_title = {client.pid: client.title for client in clients}
        except Exception as e:
            # Log warning but continue with empty mapping
            logger.warning(f"Failed to get window titles from hyprctl: {e}")

        # Match sink-inputs with window titles by PID
        audio_sources = []
        for sink_input in sink_inputs:
            window_title = pid_to_title.get(sink_input.pid)
            audio_source = AudioSource(
                sink_input_id=sink_input.sink_input_id,
                pid=sink_input.pid,
                application_name=sink_input.application_name,
                window_title=window_title,
            )
            audio_sources.append(audio_source)

        return audio_sources

    def select_source(self, sink_input_id: int) -> None:
        """Route the selected audio source to the virtual sink.

        Args:
            sink_input_id: The sink-input ID to route

        Raises:
            RuntimeError: If routing fails
            subprocess.CalledProcessError: If pactl command fails
        """
        # Route the sink-input to the virtual sink
        # The sink_manager will raise appropriate exceptions if routing fails
        self.sink_manager.route_sink_input(sink_input_id=sink_input_id)
