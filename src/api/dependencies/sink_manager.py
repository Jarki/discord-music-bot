"""Dependency injection for SinkManager."""

from typing import cast

from fastapi import Request

from src.shared.dependencies.virtual_sink import SinkManager


def get_sink_manager(request: Request) -> SinkManager:
    """Dependency to get SinkManager from app state.

    Args:
        request: FastAPI request object

    Returns:
        SinkManager instance from app state
    """
    return cast(SinkManager, request.app.state.sink_manager)
