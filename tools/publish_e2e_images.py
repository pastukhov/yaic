#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt


def parse_args() -> argparse.Namespace:
    defaults = load_defaults(Path(".env"))
    parser = argparse.ArgumentParser(
        description="Publish image fixtures from tests/e2e/images to an MQTT topic."
    )
    parser.add_argument(
        "--broker",
        default=defaults["broker"],
        help="MQTT broker hostname or IP address. Default: MQTT_HOST from .env.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=defaults["port"],
        help="MQTT broker port. Default: MQTT_PORT from .env or 1883.",
    )
    parser.add_argument(
        "--topic",
        default=defaults["topic"],
        help="MQTT topic to publish all images to. Default: MQTT_TOPIC_IN from .env with '+' replaced by --source-id.",
    )
    parser.add_argument(
        "--source-id",
        default="e2e",
        help="Source ID used when MQTT_TOPIC_IN from .env contains '+'. Default: e2e.",
    )
    parser.add_argument(
        "--images-dir",
        default="tests/e2e/images",
        help="Directory with image fixtures. Default: tests/e2e/images.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between publishes in seconds. Default: 0.5.",
    )
    parser.add_argument("--qos", type=int, default=1, choices=(0, 1, 2), help="MQTT QoS level.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be published without connecting to MQTT.",
    )
    args = parser.parse_args()
    if not args.broker:
        parser.error("broker is required via --broker or MQTT_HOST in .env")
    if not args.topic:
        parser.error("topic is required via --topic or MQTT_TOPIC_IN in .env")
    args.topic = resolve_topic(args.topic, args.source_id)
    return args


def load_defaults(env_path: Path) -> dict[str, str | int | None]:
    env_values = parse_dotenv(env_path)
    return {
        "broker": os.getenv("MQTT_HOST", env_values.get("MQTT_HOST")),
        "port": int(os.getenv("MQTT_PORT", env_values.get("MQTT_PORT", "1883"))),
        "topic": os.getenv("MQTT_TOPIC_IN", env_values.get("MQTT_TOPIC_IN")),
    }


def parse_dotenv(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def resolve_topic(topic: str, source_id: str) -> str:
    return topic.replace("+", source_id)


def iter_images(images_dir: Path) -> list[Path]:
    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory does not exist: {images_dir}")
    if not images_dir.is_dir():
        raise NotADirectoryError(f"Images path is not a directory: {images_dir}")

    images = sorted(path for path in images_dir.iterdir() if path.is_file())
    if not images:
        raise FileNotFoundError(f"No image files found in: {images_dir}")
    return images


def publish_images(
    broker: str,
    port: int,
    topic: str,
    images: list[Path],
    qos: int,
    delay: float,
) -> None:
    client = mqtt.Client()
    client.connect(broker, port, keepalive=60)
    client.loop_start()
    try:
        for image_path in images:
            payload = image_path.read_bytes()
            info = client.publish(topic, payload=payload, qos=qos)
            info.wait_for_publish()
            print(
                f"published topic={topic} file={image_path.name} bytes={len(payload)} qos={qos}",
                flush=True,
            )
            if delay > 0:
                time.sleep(delay)
    finally:
        client.loop_stop()
        client.disconnect()


def main() -> int:
    args = parse_args()
    images_dir = Path(args.images_dir)

    try:
        images = iter_images(images_dir)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for image_path in images:
        print(
            f"queue topic={args.topic} file={image_path.name} bytes={image_path.stat().st_size}",
            flush=True,
        )

    if args.dry_run:
        print(f"dry-run complete: {len(images)} file(s) queued", flush=True)
        return 0

    publish_images(
        broker=args.broker,
        port=args.port,
        topic=args.topic,
        images=images,
        qos=args.qos,
        delay=args.delay,
    )
    print(f"publish complete: {len(images)} file(s) sent to {args.broker}:{args.port}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
