"""Audio recorder for capturing audio from virtual sink monitor source.

This module provides the SinkRecorder class which captures raw PCM audio from
a PulseAudio/PipeWire monitor source using parec and implements the discord.py
AudioSource interface for voice channel streaming.
"""

import subprocess
from typing import Protocol


class AudioSource(Protocol):
    """Protocol defining the discord.py AudioSource interface.

    This protocol defines the interface that discord.py expects for audio sources.
    We use a Protocol instead of importing discord.py to avoid adding it as a
    required dependency during development.
    """

    def read(self) -> bytes:
        """Read audio data.

        Returns:
            Audio data as bytes. Should return exactly 3,840 bytes (20ms of
            16-bit 48kHz stereo PCM) per call, or empty bytes if no data available.
        """
        ...

    def is_opus(self) -> bool:
        """Check if the audio source provides Opus-encoded data.

        Returns:
            True if audio is Opus-encoded, False if raw PCM.
        """
        ...

    def cleanup(self) -> None:
        """Clean up resources used by the audio source.

        This method is called when the audio source is no longer needed.
        Should terminate any subprocesses and close file handles.
        """
        ...


class SinkRecorder:
    """Records audio from a PulseAudio/PipeWire monitor source.

    This class captures audio using the parec command and provides it in the format
    required by discord.py for voice streaming. Audio is captured as raw PCM in
    20ms frames (3,840 bytes per frame).

    Args:
        monitor_source: Name of the monitor source (e.g., "discord_capture.monitor")
        audio_format: PCM format (default: "s16le" for 16-bit signed little-endian)
        audio_rate: Sample rate in Hz (default: 48000)
        audio_channels: Number of audio channels (default: 2 for stereo)

    Example:
        >>> recorder = SinkRecorder("discord_capture.monitor")
        >>> recorder.start()
        >>> audio_data = recorder.read()  # Returns 3,840 bytes
        >>> recorder.cleanup()

    Note:
        The frame size of 3,840 bytes is calculated as:
        - 48,000 samples/second * 0.02 seconds = 960 samples per 20ms
        - 960 samples * 2 channels = 1,920 samples
        - 1,920 samples * 2 bytes (16-bit) = 3,840 bytes
    """

    FRAME_SIZE = 3840  # 20ms of 16-bit 48kHz stereo PCM

    def __init__(
        self,
        monitor_source: str,
        audio_format: str = "s16le",
        audio_rate: int = 48000,
        audio_channels: int = 2,
    ) -> None:
        """Initialize the recorder with audio parameters.

        Args:
            monitor_source: Name of the monitor source to capture from
            audio_format: PCM format string for parec
            audio_rate: Sample rate in Hz
            audio_channels: Number of audio channels
        """
        self.monitor_source = monitor_source
        self.audio_format = audio_format
        self.audio_rate = audio_rate
        self.audio_channels = audio_channels
        self.process: subprocess.Popen[bytes] | None = None
        self._started = False

    def start(self) -> None:
        """Start capturing audio from the monitor source.

        Launches a parec subprocess to capture audio. The subprocess will continue
        running until cleanup() is called.

        Raises:
            FileNotFoundError: If parec command is not found in PATH
            subprocess.SubprocessError: If parec fails to start
            RuntimeError: If recorder is already started
        """
        if self._started:
            msg = "Recorder is already started"
            raise RuntimeError(msg)

        command = [
            "parec",
            "-d",
            self.monitor_source,
            f"--format={self.audio_format}",
            f"--rate={self.audio_rate}",
            f"--channels={self.audio_channels}",
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._started = True
        except FileNotFoundError as e:
            msg = "parec command not found. Please install PulseAudio utilities."
            raise FileNotFoundError(msg) from e
        except Exception as e:
            msg = f"Failed to start parec: {e}"
            raise subprocess.SubprocessError(msg) from e

    def read(self) -> bytes:
        """Read one frame of audio data.

        Returns exactly 3,840 bytes (20ms of audio) per call if data is available.
        This method blocks until the full frame is read or the process ends.

        Returns:
            Audio data as bytes. Returns exactly 3,840 bytes if successful,
            or empty bytes if the recorder is not started or has ended.

        Note:
            This method is called repeatedly by discord.py's voice client to
            stream audio to the voice channel.
        """
        if not self._started or self.process is None or self.process.stdout is None:
            return b""

        try:
            data = self.process.stdout.read(self.FRAME_SIZE)
            if len(data) < self.FRAME_SIZE:
                # EOF or process ended
                return b""
            return data
        except Exception:
            # Handle any read errors by returning empty bytes
            return b""

    def cleanup(self) -> None:
        """Clean up the recorder and terminate the subprocess.

        This method is idempotent - it can be called multiple times safely.
        It terminates the parec subprocess and waits for it to end.
        """
        if not self._started:
            return

        self._started = False

        if self.process is None:
            return

        try:
            # Terminate the process if it's still running
            if self.process.poll() is None:
                self.process.terminate()
                # Wait up to 5 seconds for graceful termination
                try:
                    self.process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    self.process.kill()
                    self.process.wait()
        except Exception:
            # If anything goes wrong, try to kill the process
            try:
                if self.process.poll() is None:
                    self.process.kill()
            except Exception:
                pass  # Process might already be dead

        # Close pipes if they're still open
        try:
            if self.process.stdout:
                self.process.stdout.close()
            if self.process.stderr:
                self.process.stderr.close()
        except Exception:
            pass  # Ignore errors closing pipes

        self.process = None

    def is_opus(self) -> bool:
        """Check if this audio source provides Opus-encoded data.

        Returns:
            False, as this recorder provides raw PCM audio, not Opus.
        """
        return False
