from __future__ import annotations

import logging
import sys


def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("se_claims_tool")
    if logger.handlers:
        # Avoid duplicate handlers in repeated runs
        return logger

    logger.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(fmt)

    logger.addHandler(handler)
    logger.propagate = False
    return logger
