from __future__ import annotations

import json
import logging
import signal
import threading
from importlib.metadata import PackageNotFoundError, version

from .config import load_config
from .mqtt_client import MqttClient
from .processor import Processor
from .qwen_client import QwenClient


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def _get_version() -> str:
    try:
        return version("yaic")
    except PackageNotFoundError:
        return "unknown"


def main() -> None:
    config = load_config()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=config.log_level, handlers=[handler])

    qwen = QwenClient(
        api_key=config.qwen_api_key,
        endpoint=config.qwen_endpoint,
        language=config.yaic_language,
        model=config.qwen_model,
    )
    processor = Processor(qwen)
    client = MqttClient(config, processor, sw_version=_get_version())

    shutdown_event = threading.Event()

    def _handle_shutdown(signum: int, frame: object | None) -> None:
        logging.getLogger(__name__).info("Received signal %s, shutting down", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    client.start()
    shutdown_event.wait()
    client.stop()
