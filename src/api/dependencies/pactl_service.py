"""Service for querying PulseAudio/PipeWire sink-inputs via pactl."""

import re
import subprocess

from src.api.models.pactl import SinkInput


class PactlService:
    """Service for querying PulseAudio/PipeWire sink-inputs."""

    def __init__(self, timeout: int = 5) -> None:
        """Initialize the PactlService.

        Args:
            timeout: Timeout in seconds for pactl commands (default: 5)
        """
        self.timeout = timeout

    def get_sink_inputs(self) -> list[SinkInput]:
        """Get all active sink-inputs from PulseAudio/PipeWire.

        Returns:
            List of SinkInput models representing active audio streams

        Raises:
            RuntimeError: If pactl command fails
            FileNotFoundError: If pactl is not found
            subprocess.TimeoutExpired: If command times out
        """
        try:
            result = subprocess.run(
                ["pactl", "list", "sink-inputs"],
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
            )
            return self._parse_sink_inputs(result.stdout)
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to run pactl command: {e.stderr}"
            raise RuntimeError(error_msg) from e

    def _parse_sink_inputs(self, output: str) -> list[SinkInput]:
        """Parse pactl list sink-inputs text output.

        Args:
            output: Raw text output from pactl command

        Returns:
            List of parsed SinkInput models
        """
        sink_inputs: list[SinkInput] = []
        current_id: int | None = None
        current_pid: int | None = None
        current_name: str | None = None

        for line in output.split("\n"):
            # Check for new sink-input section
            sink_input_match = re.match(r"Sink Input #(\d+)", line)
            if sink_input_match:
                # Save previous sink-input if complete
                if (
                    current_id is not None
                    and current_pid is not None
                    and current_name is not None
                ):
                    sink_inputs.append(
                        SinkInput(
                            sink_input_id=current_id,
                            pid=current_pid,
                            application_name=current_name,
                        )
                    )

                # Start new sink-input
                current_id = int(sink_input_match.group(1))
                current_pid = None
                current_name = None
                continue

            # Parse properties (only if we're in a sink-input section)
            if current_id is not None:
                # Extract PID
                pid_match = re.search(r'application\.process\.id\s*=\s*"(\d+)"', line)
                if pid_match:
                    current_pid = int(pid_match.group(1))
                    continue

                # Extract application name
                name_match = re.search(r'application\.name\s*=\s*"([^"]+)"', line)
                if name_match:
                    current_name = name_match.group(1)
                    continue

        # Don't forget the last sink-input
        if (
            current_id is not None
            and current_pid is not None
            and current_name is not None
        ):
            sink_inputs.append(
                SinkInput(
                    sink_input_id=current_id,
                    pid=current_pid,
                    application_name=current_name,
                )
            )

        return sink_inputs
