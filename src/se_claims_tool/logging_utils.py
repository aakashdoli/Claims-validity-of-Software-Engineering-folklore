from __future__ import annotations

import logging
import sys


class BufferHandler(logging.Handler):
    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self.lines = []

    def emit(self, record):
        msg = self.format(record)
        self.lines.append(msg)


def setup_logger(level: str = "INFO"):
    logger = logging.getLogger("se_claims_tool")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear old handlers to avoid duplicates on Streamlit reruns
    logger.handlers = []

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(logger.level)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    buffer = BufferHandler(level=logger.level)
    buffer.setFormatter(fmt)
    logger.addHandler(buffer)

    logger.propagate = False
    return logger, buffer
