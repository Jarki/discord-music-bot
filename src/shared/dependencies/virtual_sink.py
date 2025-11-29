"""Virtual sink management for PulseAudio/PipeWire.

This module provides classes for managing null sinks in the Linux audio system.
A null sink is a virtual audio device that applications can send audio to,
and we can record from its monitor source.
"""

import re
import subprocess


class SinkManager:
    """Manages PulseAudio/PipeWire null sink lifecycle.

    This class provides full control over sink creation, destruction, and routing.
    It's intended for use by the API server which needs to manage sink lifecycle.
    """

    def __init__(
        self, sink_name: str, sample_rate: int = 48000, channels: int = 2
    ) -> None:
        """Initialize the sink manager.

        Args:
            sink_name: Name for the null sink
            sample_rate: Audio sample rate in Hz (default: 48000)
            channels: Number of audio channels (default: 2)
        """
        self._sink_name = sink_name
        self._sample_rate = sample_rate
        self._channels = channels
        self._module_id: int | None = None

    def create(self) -> None:
        """Create the null sink.

        Raises:
            subprocess.CalledProcessError: If sink creation fails
            RuntimeError: If unable to parse module ID from output
        """
        try:
            result = subprocess.run(
                [
                    "pactl",
                    "load-module",
                    "module-null-sink",
                    f"sink_name={self._sink_name}",
                    f"rate={self._sample_rate}",
                    f"channels={self._channels}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            # Parse module ID from output like "42" or "Loaded module with index 42"
            match = re.search(r"\d+", result.stdout)
            if match:
                self._module_id = int(match.group())
            else:
                raise RuntimeError(
                    f"Failed to parse module ID from pactl output: {result.stdout}"
                )

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to create sink '{self._sink_name}': {e.stderr}"
            ) from e

    def destroy(self) -> None:
        """Destroy the null sink.

        This method is graceful and won't raise an error if the sink doesn't exist.
        """
        if self._module_id is None:
            # Sink was never created or already destroyed
            return

        try:
            # Check if module still exists
            result = subprocess.run(
                ["pactl", "list", "short", "modules"],
                check=True,
                capture_output=True,
                text=True,
            )

            # Check if our module ID is in the list
            if str(self._module_id) not in result.stdout:
                # Module already removed
                self._module_id = None
                return

            # Unload the module
            subprocess.run(
                ["pactl", "unload-module", str(self._module_id)],
                check=True,
                capture_output=True,
                text=True,
            )
            self._module_id = None

        except subprocess.CalledProcessError:
            # If anything fails, consider the sink destroyed
            self._module_id = None

    def route_sink_input(self, sink_input_id: int) -> None:
        """Route an audio source to the null sink.

        Args:
            sink_input_id: The ID of the sink input to route

        Raises:
            subprocess.CalledProcessError: If routing fails
            RuntimeError: If routing command fails
        """
        try:
            subprocess.run(
                [
                    "pactl",
                    "move-sink-input",
                    str(sink_input_id),
                    self._sink_name,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to route sink input {sink_input_id} to '{self._sink_name}': "
                f"{e.stderr}"
            ) from e

    def get_monitor_source(self) -> str:
        """Get the monitor source name for this sink.

        Returns:
            The monitor source name (e.g., "discord_capture.monitor")
        """
        return f"{self._sink_name}.monitor"

    def is_created(self) -> bool:
        """Check if the sink has been created.

        Returns:
            True if the sink has been created, False otherwise
        """
        return self._module_id is not None


class ReadOnlySink:
    """Read-only wrapper around SinkManager.

    This class prevents write operations while allowing read-only access
    to sink information. It's intended for use by the Discord bot which
    should not modify the sink.
    """

    def __init__(self, sink_manager: SinkManager) -> None:
        """Initialize the read-only sink wrapper.

        Args:
            sink_manager: The underlying SinkManager instance
        """
        self._sink_manager = sink_manager

    def get_monitor_source(self) -> str:
        """Get the monitor source name for this sink.

        Returns:
            The monitor source name (e.g., "discord_capture.monitor")
        """
        return self._sink_manager.get_monitor_source()

    def is_created(self) -> bool:
        """Check if the sink has been created.

        Returns:
            True if the sink has been created, False otherwise
        """
        return self._sink_manager.is_created()

    def create(self) -> None:
        """Attempt to create sink (not allowed in read-only mode).

        Raises:
            RuntimeError: Always, as creation is not allowed
        """
        raise RuntimeError("Cannot create sink in read-only mode")

    def destroy(self) -> None:
        """Attempt to destroy sink (not allowed in read-only mode).

        Raises:
            RuntimeError: Always, as destruction is not allowed
        """
        raise RuntimeError("Cannot destroy sink in read-only mode")

    def route_sink_input(self, sink_input_id: int) -> None:
        """Attempt to route sink input (not allowed in read-only mode).

        Args:
            sink_input_id: The ID of the sink input (ignored)

        Raises:
            RuntimeError: Always, as routing is not allowed
        """
        raise RuntimeError("Cannot route sink input in read-only mode")
