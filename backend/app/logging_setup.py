import json
import logging
from logging.handlers import RotatingFileHandler
from backend.app.config import ROOT


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "level": record.levelname,
                "time": self.formatTime(record),
                "logger": record.name,
                "message": record.getMessage(),
            }
        )


def setup_logging():
    (ROOT / "logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler(ROOT / "logs/radar.log", maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(JsonFormatter())
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
