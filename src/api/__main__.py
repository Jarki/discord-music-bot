"""Entry point for running the FastAPI API server."""

import uvicorn

from src.api import create_app
from src.shared.models.config import Settings


def main() -> None:
    """Run the FastAPI application with uvicorn."""
    settings = Settings()  # type: ignore[call-arg]
    app = create_app()

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
