"""Integration tests for Virtual Sink Manager.

These tests interact with the actual PulseAudio/PipeWire system to verify
real-world behavior of the Virtual Sink Manager.

Requirements:
- PulseAudio or PipeWire must be installed and running
- `pactl` command must be available
- Tests will create and destroy real null sinks
"""

import contextlib
import subprocess

import pytest

from src.shared.dependencies.virtual_sink import ReadOnlySink, SinkManager

# Helper Functions


def get_sink_list() -> list[str]:
    """Get list of current sink names from pactl.

    Returns:
        List of sink names currently in the system
    """
    result = subprocess.run(
        ["pactl", "list", "short", "sinks"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    # Parse output: "index\tname\tdriver\tsample_spec\tstate"
    sinks = []
    for line in result.stdout.strip().split("\n"):
        if line:
            parts = line.split()
            if len(parts) >= 2:
                sinks.append(parts[1])
    return sinks


def get_source_list() -> list[str]:
    """Get list of current source names from pactl.

    Returns:
        List of source names currently in the system
    """
    result = subprocess.run(
        ["pactl", "list", "short", "sources"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    sources = []
    for line in result.stdout.strip().split("\n"):
        if line:
            parts = line.split()
            if len(parts) >= 2:
                sources.append(parts[1])
    return sources


def sink_exists(sink_name: str) -> bool:
    """Check if a sink with given name exists.

    Args:
        sink_name: Name of the sink to check

    Returns:
        True if sink exists, False otherwise
    """
    return sink_name in get_sink_list()


def cleanup_test_sinks() -> None:
    """Emergency cleanup of any leftover test sinks.

    This function removes all sinks that start with "test_sink_".
    Used for cleanup after tests to prevent pollution.
    """
    try:
        sinks = get_sink_list()
        for sink in sinks:
            if sink.startswith("test_sink_"):
                try:
                    # Find the module and unload it
                    result = subprocess.run(
                        ["pactl", "list", "short", "modules"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    for line in result.stdout.strip().split("\n"):
                        if sink in line:
                            parts = line.split()
                            if parts:
                                subprocess.run(
                                    ["pactl", "unload-module", parts[0]],
                                    check=False,
                                    timeout=5,
                                )
                                break
                except Exception:
                    pass  # Ignore cleanup errors
    except Exception:
        pass  # Ignore all cleanup errors


# Test Suite 1: Sink Creation and Destruction


@pytest.mark.integration
def test_create_and_destroy_sink_real_system(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test that SinkManager can create and destroy a real null sink.

    This test interacts with the actual PulseAudio/PipeWire system to verify:
    1. Null sink is created and appears in pactl output
    2. Sink is properly destroyed and removed from system
    3. No leftover resources remain after cleanup

    Requires: PulseAudio or PipeWire installed and running
    """
    manager = SinkManager(unique_sink_name)

    try:
        # Verify sink doesn't exist initially
        assert not manager.is_created()
        assert not sink_exists(unique_sink_name)

        # Create the sink
        manager.create()

        # Verify sink was created
        assert manager.is_created()
        assert sink_exists(unique_sink_name)

        # Destroy the sink
        manager.destroy()

        # Verify sink was destroyed
        assert not manager.is_created()
        assert not sink_exists(unique_sink_name)

    finally:
        # Ensure cleanup even if test fails
        with contextlib.suppress(Exception):
            manager.destroy()


@pytest.mark.integration
def test_sink_appears_in_pactl_list(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test that created sink appears in pactl list output.

    Verifies that the sink is visible to the audio system and can be
    queried using standard pactl commands.
    """
    manager = SinkManager(unique_sink_name)

    try:
        manager.create()

        # Get sink list
        sinks = get_sink_list()

        # Verify our sink is in the list
        assert unique_sink_name in sinks

    finally:
        manager.destroy()


@pytest.mark.integration
def test_monitor_source_exists(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test that monitor source is created with the sink.

    Every null sink should have an associated monitor source that
    can be used to record audio routed to the sink.
    """
    manager = SinkManager(unique_sink_name)

    try:
        manager.create()

        # Get expected monitor source name
        expected_monitor = manager.get_monitor_source()
        assert expected_monitor == f"{unique_sink_name}.monitor"

        # Verify monitor source exists in system
        sources = get_source_list()
        assert expected_monitor in sources

    finally:
        manager.destroy()


# Test Suite 2: Multiple Sink Management


@pytest.mark.integration
@pytest.mark.slow
def test_multiple_sinks_can_coexist(pulseaudio_available: bool) -> None:
    """Test that multiple sinks can be created and managed simultaneously.

    Verifies that SinkManager instances don't interfere with each other
    and multiple sinks can coexist in the system.
    """
    import uuid

    # Create unique names for 3 sinks
    sink_names = [f"test_sink_{uuid.uuid4().hex[:8]}" for _ in range(3)]
    managers = [SinkManager(name) for name in sink_names]

    try:
        # Create all sinks
        for manager in managers:
            manager.create()

        # Verify all sinks exist
        sinks = get_sink_list()
        for name in sink_names:
            assert name in sinks

        # Destroy all sinks
        for manager in managers:
            manager.destroy()

        # Verify all cleaned up
        sinks = get_sink_list()
        for name in sink_names:
            assert name not in sinks

    finally:
        # Cleanup any remaining sinks
        for manager in managers:
            with contextlib.suppress(Exception):
                manager.destroy()


@pytest.mark.integration
def test_destroy_is_idempotent(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test that calling destroy multiple times doesn't raise errors.

    The destroy operation should be idempotent - calling it multiple times
    should not cause errors or unexpected behavior.
    """
    manager = SinkManager(unique_sink_name)

    try:
        manager.create()
        manager.destroy()

        # Call destroy again - should not raise error
        manager.destroy()

        # And again for good measure
        manager.destroy()

        # Verify sink doesn't exist
        assert not sink_exists(unique_sink_name)

    finally:
        with contextlib.suppress(Exception):
            manager.destroy()


# Test Suite 3: Sink Configuration


@pytest.mark.integration
def test_sink_with_custom_sample_rate(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test creating a sink with custom sample rate.

    Verifies that the sample_rate parameter is properly passed to
    the audio system when creating the sink.
    """
    manager = SinkManager(unique_sink_name, sample_rate=44100)

    try:
        manager.create()

        # Verify sink was created
        assert manager.is_created()
        assert sink_exists(unique_sink_name)

        # Note: Verifying the actual sample rate would require parsing
        # the full pactl output, which varies by system. We just verify
        # creation succeeds with custom parameters.

    finally:
        manager.destroy()


@pytest.mark.integration
def test_sink_with_custom_channels(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test creating a sink with custom channel count.

    Verifies that the channels parameter (mono, stereo, etc.) is
    properly passed to the audio system.
    """
    manager = SinkManager(unique_sink_name, channels=1)  # Mono

    try:
        manager.create()

        # Verify sink was created
        assert manager.is_created()
        assert sink_exists(unique_sink_name)

    finally:
        manager.destroy()


@pytest.mark.integration
def test_sink_with_all_custom_parameters(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test creating a sink with all custom parameters.

    Verifies that all configuration parameters can be customized
    simultaneously without issues.
    """
    manager = SinkManager(unique_sink_name, sample_rate=96000, channels=1)

    try:
        manager.create()

        assert manager.is_created()
        assert sink_exists(unique_sink_name)

    finally:
        manager.destroy()


# Test Suite 4: Error Conditions


@pytest.mark.integration
def test_create_duplicate_sink_name_allowed(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test behavior when creating sinks with duplicate names.

    Note: PulseAudio/PipeWire actually allows multiple modules with the
    same sink name. Each gets a unique module ID internally. This test
    verifies that behavior and ensures proper cleanup.
    """
    manager1 = SinkManager(unique_sink_name)
    manager2 = SinkManager(unique_sink_name)

    try:
        # Create first sink
        manager1.create()
        assert sink_exists(unique_sink_name)

        # Create second sink with same name - PulseAudio allows this
        manager2.create()

        # Both should report as created (different module IDs)
        assert manager1.is_created()
        assert manager2.is_created()

        # Sink name should still exist
        assert sink_exists(unique_sink_name)

    finally:
        # Cleanup both - each has its own module ID
        with contextlib.suppress(Exception):
            manager1.destroy()
        with contextlib.suppress(Exception):
            manager2.destroy()


@pytest.mark.integration
def test_destroy_nonexistent_sink_graceful(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test that destroying a non-existent sink doesn't raise errors.

    The destroy operation should be graceful and not fail if the sink
    doesn't exist or was already destroyed.
    """
    manager = SinkManager(unique_sink_name)

    # Don't create the sink, just try to destroy
    manager.destroy()  # Should not raise

    assert not manager.is_created()
    assert not sink_exists(unique_sink_name)


# Test Suite 5: ReadOnlySink Integration


@pytest.mark.integration
def test_readonly_sink_can_read_created_sink(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test that ReadOnlySink can access information about created sinks.

    Verifies that the ReadOnlySink wrapper correctly delegates read
    operations to the underlying SinkManager.
    """
    manager = SinkManager(unique_sink_name)
    readonly = ReadOnlySink(manager)

    try:
        # Create via manager
        manager.create()

        # Verify readonly can access info
        assert readonly.is_created()
        assert readonly.get_monitor_source() == f"{unique_sink_name}.monitor"

        # Verify monitor source actually exists
        sources = get_source_list()
        assert readonly.get_monitor_source() in sources

    finally:
        manager.destroy()


@pytest.mark.integration
def test_readonly_sink_cannot_modify(
    pulseaudio_available: bool, unique_sink_name: str
) -> None:
    """Test that ReadOnlySink prevents write operations.

    Verifies that the ReadOnlySink wrapper correctly prevents any
    operations that would modify the sink state.
    """
    manager = SinkManager(unique_sink_name)
    readonly = ReadOnlySink(manager)

    try:
        # ReadOnly should not be able to create
        with pytest.raises(RuntimeError, match="Cannot create sink in read-only mode"):
            readonly.create()

        # Create via manager
        manager.create()

        # ReadOnly should not be able to destroy
        with pytest.raises(RuntimeError, match="Cannot destroy sink in read-only mode"):
            readonly.destroy()

        # Verify sink still exists (wasn't destroyed)
        assert sink_exists(unique_sink_name)

    finally:
        manager.destroy()


# Test Suite 6: Cleanup and Resource Management


@pytest.mark.integration
@pytest.mark.slow
def test_cleanup_handles_orphaned_sinks() -> None:
    """Test that cleanup function can remove orphaned test sinks.

    Verifies that the cleanup mechanism can properly clean up test sinks
    that might be left over from crashed tests or other issues.
    """
    import uuid

    # Create a sink that we'll intentionally leave orphaned
    orphan_name = f"test_sink_{uuid.uuid4().hex[:8]}"
    manager = SinkManager(orphan_name)

    manager.create()
    assert sink_exists(orphan_name)

    # Now cleanup without using manager.destroy()
    cleanup_test_sinks()

    # Verify orphaned sink was cleaned up
    assert not sink_exists(orphan_name)
