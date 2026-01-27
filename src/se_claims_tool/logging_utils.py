import logging
import sys

def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("se_claims_tool")
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    h = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    h.setFormatter(fmt)
    logger.addHandler(h)
    return logger
