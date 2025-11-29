"""FastAPI application factory and configuration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import audio
from src.shared.dependencies.virtual_sink import SinkManager
from src.shared.models.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle: startup and shutdown.

    Creates the virtual sink on startup and destroys it on shutdown.
    The sink_manager is stored in app.state for access by routes.

    Args:
        app: FastAPI application instance

    Yields:
        None - application runs here
    """
    # Load configuration
    settings = Settings()  # type: ignore[call-arg]

    # Create and initialize sink manager
    sink_manager = SinkManager(
        sink_name=settings.sink_name,
        sample_rate=settings.audio_rate,
        channels=settings.audio_channels,
    )

    try:
        # Startup: create virtual sink
        sink_manager.create()

        # Store in app state for access by dependencies
        app.state.sink_manager = sink_manager
        app.state.settings = settings

        yield
    finally:
        # Shutdown: cleanup virtual sink
        sink_manager.destroy()


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="LOUD Bot API",
        description="Local Output Uploaded to Discord - Audio routing API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register routes
    app.include_router(audio.router, prefix="/api", tags=["audio"])

    return app
