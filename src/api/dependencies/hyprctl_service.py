"""Service for querying Hyprland window information via hyprctl."""

import json
import subprocess
from typing import Any

from src.api.models.hyprctl import HyprlandClient


class HyprctlService:
    """Service for interacting with Hyprland via hyprctl command."""

    def __init__(self, timeout: int = 5) -> None:
        """Initialize the service.

        Args:
            timeout: Command timeout in seconds (default: 5)
        """
        self.timeout = timeout

    def get_clients(self) -> list[HyprlandClient]:
        """Get list of Hyprland window clients.

        Returns:
            List of HyprlandClient models containing pid and title.

        Raises:
            RuntimeError: If command fails, JSON is invalid, or fields are missing.
            FileNotFoundError: If hyprctl command is not found.
            subprocess.TimeoutExpired: If command times out.
        """
        try:
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"hyprctl command failed: {e}") from e

        try:
            clients_data: list[dict[str, Any]] = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse hyprctl JSON output: {e}") from e

        clients = []
        for client_data in clients_data:
            try:
                # Extract only pid and title fields
                client = HyprlandClient(
                    pid=client_data["pid"],
                    title=client_data["title"],
                )
                clients.append(client)
            except KeyError as e:
                raise RuntimeError(
                    f"Missing required field in hyprctl output: {e}"
                ) from e

        return clients
