import os
import logging

# --- Constants ---
_C = {
    "RESET": "\033[0m",
    "DIM": "\033[2m",
    "BOLD": "\033[1m",
    "BLUE": "\033[34m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
    "RED": "\033[31m",
}

# --- Configuration ---
LOG_LEVEL_NAME = (os.getenv("LOG_LEVEL") or "INFO").upper()
NO_COLOR = os.getenv("NO_COLOR") is not None
LOG_FILE = os.getenv("LOG_FILE")

# --- Custom Formatter ---
class ColorFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formatters = {
            logging.DEBUG: self._colorize(f"%(asctime)s [%(levelname)s] %(message)s", _C["DIM"]),
            logging.INFO: self._colorize(f"%(asctime)s [%(levelname)s] %(message)s", _C["DIM"]),
            logging.WARNING: self._colorize(f"%(asctime)s [%(levelname)s] %(message)s", _C["YELLOW"]),
            logging.ERROR: self._colorize(f"%(asctime)s [%(levelname)s] %(message)s", _C["RED"]),
            logging.CRITICAL: self._colorize(f"%(asctime)s [%(levelname)s] %(message)s", _C["RED"] + _C["BOLD"]),
        }

    def _colorize(self, text: str, color: str) -> str:
        if NO_COLOR:
            return text
        return f"{color}{text}{_C['RESET']}"

    def format(self, record):
        # Custom prefixes for special info logs
        if record.levelname == 'INFO':
            if record.msg.startswith('[STEP]'):
                record.msg = self._colorize(record.msg, _C["BLUE"])
            elif record.msg.startswith('[OK]'):
                record.msg = self._colorize(record.msg, _C["GREEN"])
        
        log_fmt = self.formatters.get(record.levelno, self._style._fmt)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)

# --- Logger Setup ---
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL_NAME)

# Console Handler
ch = logging.StreamHandler()
ch.setFormatter(ColorFormatter())
logger.addHandler(ch)

# File Handler
if LOG_FILE:
    try:
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
        # For file, don't use colors
        file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(file_formatter)
        logger.addHandler(fh)
    except Exception as e:
        logger.warning(f"Failed to set up file logger: {e}")