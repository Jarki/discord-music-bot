from loguru import logger

import src


def main() -> None:
    src.setup_logger()

    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
    print("Hello from loud_bot!")

if __name__ == "__main__":
    main()
