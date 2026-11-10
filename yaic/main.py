from __future__ import annotations

import json
import logging
import signal
import threading

from .config import load_config
from .runtime import build_processor


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


def run_mqtt() -> None:
    config = load_config()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=config.log_level, handlers=[handler])

    from .mqtt_client import MqttClient
    processor = build_processor(config)
    from . import api
    api.set_face_recognizer(processor._face_recognizer)
    api.start_api_server(config.api_host, config.api_port)
    client = MqttClient(config, processor)

    shutdown_event = threading.Event()

    def _handle_shutdown(signum: int, frame: object | None) -> None:
        logging.getLogger(__name__).info("Received signal %s, shutting down", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    client.start()
    shutdown_event.wait()
    client.stop()


def main(argv: list[str] | None = None) -> None:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="YAIC image classifier")
    commands = parser.add_subparsers(dest="command")
    classify = commands.add_parser("classify", help="Classify one local image as JSON")
    classify.add_argument("--image", required=True)
    classify.add_argument("--source-id", required=True)
    listen = commands.add_parser("listen-tuya", help="Read local Tuya events as JSONL")
    listen.add_argument("--device-config", required=True)
    listen.add_argument("--source-id", required=True)
    listen.add_argument("--classify", action="store_true")
    args = parser.parse_args(argv)
    if args.command is None:
        run_mqtt()
        return
    if args.command == "listen-tuya":
        import os
        from .tuya_source import TuyaSource
        from .tuya_runner import TuyaRunner
        try:
            device_config = json.loads(Path(args.device_config).read_text())
            source = TuyaSource(device_config, args.source_id)
            processor = build_processor(load_config(require_mqtt=False)) if args.classify else None
            from . import api
            api.set_face_recognizer(processor._face_recognizer if processor else None)
            api.start_api_server(os.getenv("API_HOST", "0.0.0.0"), int(os.getenv("API_PORT", "8080")))
            stop = threading.Event()
            previous = {}
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.signal(signum, lambda *_: stop.set())
            try:
                TuyaRunner(source, processor=processor, snapshot_url=os.getenv("YAIC_SNAPSHOT_URL")).run(stop)
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
        except Exception:
            parser.exit(1, "Tuya listener failed; check external device and classifier configuration.\n")
        return
    try:
        config = load_config(require_mqtt=False)
        result = build_processor(config).process_message(Path(args.image).read_bytes(), args.source_id)
        print(json.dumps(result.payload, separators=(",", ":")))
    except Exception:
        parser.exit(1, "Classification failed; check image and classifier configuration.\n")


if __name__ == "__main__":
    main()
