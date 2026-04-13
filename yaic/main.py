from __future__ import annotations

import json
import logging
import signal
import threading
from importlib.metadata import PackageNotFoundError, version

from . import api
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

    face_recognizer = None
    role_classifier = None

    if config.chroma_host:
        from .face_recognition import FaceRecognizer
        from .role_classifier import RoleClassifier

        face_recognizer = FaceRecognizer(
            chroma_host=config.chroma_host,
            chroma_port=config.chroma_port,
            faces_dir=config.faces_dir,
            similarity_high=config.face_similarity_high,
            similarity_low=config.face_similarity_low,
            vlm_client=vlm,
        )
        if config.face_index_on_startup:
            logging.getLogger(__name__).info("Building face index on startup")
            face_recognizer.reindex()

        if config.classify_stranger_role:
            role_classifier = RoleClassifier(vlm, config.yaic_language)

        api.set_face_recognizer(face_recognizer)
        api.start_api_server(config.api_host, config.api_port)

    processor = Processor(
        vlm,
        ha_token=config.ha_token,
        face_recognizer=face_recognizer,
        role_classifier=role_classifier,
    )
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
