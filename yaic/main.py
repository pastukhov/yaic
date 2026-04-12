from __future__ import annotations

import json
import logging
import signal
import threading
from importlib.metadata import PackageNotFoundError, version

from .config import load_config
from .mqtt_client import MqttClient
from .processor import Processor
from .vlm_client import VlmClient


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

    vlm = VlmClient(
        api_key=config.vlm_api_key,
        endpoint=config.vlm_endpoint,
        language=config.yaic_language,
        model=config.vlm_model,
        timeout=config.inference_timeout,
        temperature=config.inference_temperature,
    )
    processor = Processor(vlm, ha_token=config.ha_token)
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
