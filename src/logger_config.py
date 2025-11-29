import loguru


def setup_logger() -> None:
    loguru.logger.remove()
    loguru.logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> - "
        "[<level>{level: <8}</level>] "
        "(<cyan>{name}</cyan>, <cyan>{line}</cyan>) - "
        "<level>{message}</level>",
        level="DEBUG",
        colorize=True,
    )
