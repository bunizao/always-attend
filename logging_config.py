import logging
import os
import sys

# Environment configuration
LOG_LEVEL_NAME = (os.getenv("LOG_LEVEL") or "INFO").upper()
NO_COLOR = os.getenv("NO_COLOR") is not None
LOG_FILE = os.getenv("LOG_FILE")

# Custom levels for step and ok
OK_LEVEL_NUM = 21
STEP_LEVEL_NUM = 22
logging.addLevelName(OK_LEVEL_NUM, "OK")
logging.addLevelName(STEP_LEVEL_NUM, "STEP")


def ok(self, message, *args, **kws):
    if self.isEnabledFor(OK_LEVEL_NUM):
        self._log(OK_LEVEL_NUM, message, args, **kws)

def step(self, message, *args, **kws):
    if self.isEnabledFor(STEP_LEVEL_NUM):
        self._log(STEP_LEVEL_NUM, message, args, **kws)

logging.Logger.ok = ok
logging.Logger.step = step


class _C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"


LEVEL_COLORS = {
    logging.DEBUG: _C.DIM,
    logging.INFO: _C.DIM,
    OK_LEVEL_NUM: _C.GREEN,
    STEP_LEVEL_NUM: _C.BLUE,
    logging.WARNING: _C.YELLOW,
    logging.ERROR: _C.RED,
    logging.CRITICAL: _C.RED,
}


class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if not NO_COLOR:
            color = LEVEL_COLORS.get(record.levelno)
            if color:
                message = f"{color}{message}{_C.RESET}"
        record.message = message
        return super().format(record)


LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
logger.handlers.clear()

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(ColorFormatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(stream_handler)

if LOG_FILE:
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(file_handler)
    except Exception:
        pass
