"""Unit tests for virtual sink management."""

import subprocess
from unittest.mock import Mock, patch

import pytest

from src.shared.dependencies.virtual_sink import ReadOnlySink, SinkManager


class TestSinkManager:
    """Test cases for SinkManager class."""

    def test_create_sink_success(self) -> None:
        """Test successful sink creation."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Loaded module with index 42", stderr=""
            )

            manager = SinkManager("test_sink")
            manager.create()

            # Verify correct command was called
            mock_run.assert_called_once_with(
                [
                    "pactl",
                    "load-module",
                    "module-null-sink",
                    "sink_name=test_sink",
                    "rate=48000",
                    "channels=2",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            # Verify sink is marked as created
            assert manager.is_created()

    def test_create_sink_success_numeric_output(self) -> None:
        """Test successful sink creation with numeric-only output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="42\n", stderr="")

            manager = SinkManager("test_sink")
            manager.create()

            assert manager.is_created()

    def test_create_sink_custom_parameters(self) -> None:
        """Test sink creation with custom sample rate and channels."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Loaded module with index 99", stderr=""
            )

            manager = SinkManager("custom_sink", sample_rate=44100, channels=1)
            manager.create()

            mock_run.assert_called_once_with(
                [
                    "pactl",
                    "load-module",
                    "module-null-sink",
                    "sink_name=custom_sink",
                    "rate=44100",
                    "channels=1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_create_sink_failure(self) -> None:
        """Test sink creation failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "pactl", stderr="Connection refused"
            )

            manager = SinkManager("test_sink")

            with pytest.raises(RuntimeError, match="Failed to create sink"):
                manager.create()

            # Verify sink is not marked as created
            assert not manager.is_created()

    def test_create_sink_invalid_output(self) -> None:
        """Test sink creation with unparseable output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Something went wrong", stderr=""
            )

            manager = SinkManager("test_sink")

            with pytest.raises(RuntimeError, match="Failed to parse module ID"):
                manager.create()

            assert not manager.is_created()

    def test_destroy_sink_success(self) -> None:
        """Test successful sink destruction."""
        with patch("subprocess.run") as mock_run:
            # Mock creation
            mock_run.return_value = Mock(
                returncode=0, stdout="Loaded module with index 42", stderr=""
            )

            manager = SinkManager("test_sink")
            manager.create()

            # Mock module list check and destruction
            def mock_run_side_effect(*args, **kwargs):
                cmd = args[0] if args else []
                if cmd[:3] == ["pactl", "list", "short"]:
                    return Mock(
                        returncode=0, stdout="42\tmodule-null-sink\n", stderr=""
                    )
                elif cmd[:2] == ["pactl", "unload-module"]:
                    return Mock(returncode=0, stdout="", stderr="")
                return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_run_side_effect

            manager.destroy()

            # Verify unload command was called
            unload_calls = [
                call
                for call in mock_run.call_args_list
                if call.args[0][:2] == ["pactl", "unload-module"]
            ]
            assert len(unload_calls) == 1
            assert unload_calls[0].args[0] == ["pactl", "unload-module", "42"]

            # Verify sink is no longer marked as created
            assert not manager.is_created()

    def test_destroy_nonexistent_sink(self) -> None:
        """Test destroying a sink that was never created."""
        manager = SinkManager("test_sink")

        # Should not raise an exception
        manager.destroy()

        assert not manager.is_created()

    def test_destroy_already_removed_module(self) -> None:
        """Test destroying a sink whose module was already removed externally."""
        with patch("subprocess.run") as mock_run:
            # Mock creation
            mock_run.return_value = Mock(
                returncode=0, stdout="Loaded module with index 42", stderr=""
            )

            manager = SinkManager("test_sink")
            manager.create()

            # Mock module list check - module not found
            mock_run.return_value = Mock(returncode=0, stdout="99\tmodule-other\n")

            manager.destroy()

            # Verify no unload command was called (module already gone)
            unload_calls = [
                call
                for call in mock_run.call_args_list
                if len(call.args[0]) >= 2
                and call.args[0][0:2] == ["pactl", "unload-module"]
            ]
            assert len(unload_calls) == 0

            assert not manager.is_created()

    def test_destroy_handles_errors_gracefully(self) -> None:
        """Test that destroy handles subprocess errors gracefully."""
        with patch("subprocess.run") as mock_run:
            # Mock creation
            mock_run.return_value = Mock(
                returncode=0, stdout="Loaded module with index 42", stderr=""
            )

            manager = SinkManager("test_sink")
            manager.create()

            # Mock list command failure
            mock_run.side_effect = subprocess.CalledProcessError(1, "pactl")

            # Should not raise an exception
            manager.destroy()

            assert not manager.is_created()

    def test_route_sink_input_success(self) -> None:
        """Test successful sink input routing."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            manager = SinkManager("test_sink")
            manager.route_sink_input(42)

            mock_run.assert_called_once_with(
                ["pactl", "move-sink-input", "42", "test_sink"],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_route_sink_input_failure(self) -> None:
        """Test sink input routing failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "pactl", stderr="Invalid sink input"
            )

            manager = SinkManager("test_sink")

            with pytest.raises(RuntimeError, match="Failed to route sink input"):
                manager.route_sink_input(42)

    def test_get_monitor_source(self) -> None:
        """Test getting the monitor source name."""
        manager = SinkManager("test_sink")
        assert manager.get_monitor_source() == "test_sink.monitor"

    def test_get_monitor_source_different_names(self) -> None:
        """Test monitor source name with different sink names."""
        manager1 = SinkManager("discord_capture")
        assert manager1.get_monitor_source() == "discord_capture.monitor"

        manager2 = SinkManager("my_audio")
        assert manager2.get_monitor_source() == "my_audio.monitor"

    def test_is_created_initially_false(self) -> None:
        """Test that is_created is False before creation."""
        manager = SinkManager("test_sink")
        assert not manager.is_created()


class TestReadOnlySink:
    """Test cases for ReadOnlySink class."""

    def test_get_monitor_source_delegates(self) -> None:
        """Test that get_monitor_source delegates to underlying SinkManager."""
        manager = SinkManager("test_sink")
        readonly = ReadOnlySink(manager)

        assert readonly.get_monitor_source() == "test_sink.monitor"
        assert readonly.get_monitor_source() == manager.get_monitor_source()

    def test_is_created_delegates_false(self) -> None:
        """Test that is_created delegates when sink is not created."""
        manager = SinkManager("test_sink")
        readonly = ReadOnlySink(manager)

        assert not readonly.is_created()
        assert readonly.is_created() == manager.is_created()

    def test_is_created_delegates_true(self) -> None:
        """Test that is_created delegates when sink is created."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Loaded module with index 42", stderr=""
            )

            manager = SinkManager("test_sink")
            manager.create()
            readonly = ReadOnlySink(manager)

            assert readonly.is_created()
            assert readonly.is_created() == manager.is_created()

    def test_create_raises_error(self) -> None:
        """Test that create raises RuntimeError."""
        manager = SinkManager("test_sink")
        readonly = ReadOnlySink(manager)

        with pytest.raises(RuntimeError, match="Cannot create sink in read-only mode"):
            readonly.create()

    def test_destroy_raises_error(self) -> None:
        """Test that destroy raises RuntimeError."""
        manager = SinkManager("test_sink")
        readonly = ReadOnlySink(manager)

        with pytest.raises(RuntimeError, match="Cannot destroy sink in read-only mode"):
            readonly.destroy()

    def test_route_sink_input_raises_error(self) -> None:
        """Test that route_sink_input raises RuntimeError."""
        manager = SinkManager("test_sink")
        readonly = ReadOnlySink(manager)

        with pytest.raises(
            RuntimeError, match="Cannot route sink input in read-only mode"
        ):
            readonly.route_sink_input(42)

    def test_readonly_doesnt_affect_underlying_manager(self) -> None:
        """Test that readonly wrapper doesn't prevent manager operations."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Loaded module with index 42", stderr=""
            )

            manager = SinkManager("test_sink")
            readonly = ReadOnlySink(manager)

            # Manager should still be able to create
            manager.create()

            assert manager.is_created()
            assert readonly.is_created()

            # But readonly should still raise errors
            with pytest.raises(RuntimeError):
                readonly.create()
