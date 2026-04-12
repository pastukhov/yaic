#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt


def parse_args() -> argparse.Namespace:
    defaults = load_defaults(Path(".env"))
    parser = argparse.ArgumentParser(
        description="E2E scenario: publish photo(s) to YAIC input topic and wait for descriptions."
    )
    parser.add_argument(
        "--broker",
        default=defaults["broker"],
        help="MQTT broker host. Default: MQTT_HOST from .env.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=defaults["port"],
        help="MQTT broker port. Default: MQTT_PORT from .env or 1883.",
    )
    parser.add_argument(
        "--input-topic",
        default=defaults["input_topic"],
        help="Input topic template. Default: MQTT_TOPIC_IN from .env.",
    )
    parser.add_argument(
        "--output-prefix",
        default=defaults["output_prefix"],
        help="Output topic prefix. Default: MQTT_TOPIC_OUT from .env.",
    )
    parser.add_argument(
        "--source-id",
        default="e2e",
        help="Source ID for topic resolution. Default: e2e.",
    )
    parser.add_argument(
        "--images-dir",
        default="tests/e2e/images",
        help="Directory with images. Default: tests/e2e/images.",
    )
    parser.add_argument(
        "--image",
        default=None,
        help="Single image file path. If set, only this file is used.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Seconds to wait for each response. Default: 45.",
    )
    parser.add_argument("--qos", type=int, default=1, choices=(0, 1, 2), help="MQTT QoS.")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between images.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned publish/subscribe topics and files only.",
    )
    args = parser.parse_args()
    if not args.broker:
        parser.error("broker is required via --broker or MQTT_HOST in .env")
    if not args.input_topic:
        parser.error("input topic is required via --input-topic or MQTT_TOPIC_IN in .env")
    if not args.output_prefix:
        parser.error("output prefix is required via --output-prefix or MQTT_TOPIC_OUT in .env")
    return args


def load_defaults(env_path: Path) -> dict[str, str | int | None]:
    env_values = parse_dotenv(env_path)
    return {
        "broker": os.getenv("MQTT_HOST", env_values.get("MQTT_HOST")),
        "port": int(os.getenv("MQTT_PORT", env_values.get("MQTT_PORT", "1883"))),
        "input_topic": os.getenv("MQTT_TOPIC_IN", env_values.get("MQTT_TOPIC_IN")),
        "output_prefix": os.getenv("MQTT_TOPIC_OUT", env_values.get("MQTT_TOPIC_OUT")),
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


def resolve_input_topic(topic_template: str, source_id: str) -> str:
    return topic_template.replace("+", source_id)


def resolve_output_topic(output_prefix: str, source_id: str) -> str:
    return output_prefix.rstrip("/")


def collect_images(images_dir: Path, image_path: str | None) -> list[Path]:
    if image_path:
        single = Path(image_path)
        if not single.is_file():
            raise FileNotFoundError(f"Image does not exist: {single}")
        return [single]

    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory does not exist: {images_dir}")
    if not images_dir.is_dir():
        raise NotADirectoryError(f"Images path is not a directory: {images_dir}")

    files = sorted(path for path in images_dir.iterdir() if path.is_file())
    if not files:
        raise FileNotFoundError(f"No image files found in: {images_dir}")
    return files


def wait_for_result(
    results: "queue.Queue[dict[str, Any]]",
    timeout: float,
    expected_source: str,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for classification response")
        item = results.get(timeout=remaining)
        source = item.get("source")
        if source is None or source == expected_source:
            return item


def format_description(payload: dict[str, Any]) -> str:
    label = payload.get("label", "unknown")
    confidence = payload.get("confidence", 0.0)
    person = payload.get("person")
    if isinstance(person, dict) and isinstance(person.get("count"), int) and person["count"] > 0:
        description = person.get("description")
        if description:
            return f"label={label} confidence={confidence} people={person['count']} description={description}"
        return f"label={label} confidence={confidence} people={person['count']}"
    return f"label={label} confidence={confidence}"


def run_scenario(
    broker: str,
    port: int,
    input_topic: str,
    output_topic: str,
    source_id: str,
    images: list[Path],
    qos: int,
    timeout: float,
    delay: float,
) -> int:
    result_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()

    def on_message(client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if isinstance(payload, dict):
                result_queue.put(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

    client = mqtt.Client()
    client.on_message = on_message
    client.connect(broker, port, keepalive=60)
    client.subscribe(output_topic, qos=qos)
    client.loop_start()
    exit_code = 0
    try:
        for image_path in images:
            payload = image_path.read_bytes()
            publish_info = client.publish(input_topic, payload=payload, qos=qos)
            publish_info.wait_for_publish()
            print(f"sent file={image_path.name} topic={input_topic} bytes={len(payload)}", flush=True)
            try:
                result = wait_for_result(result_queue, timeout=timeout, expected_source=source_id)
            except TimeoutError as exc:
                print(f"timeout file={image_path.name}: {exc}", file=sys.stderr, flush=True)
                exit_code = 1
                continue
            print(f"received file={image_path.name} {format_description(result)}", flush=True)
            if delay > 0:
                time.sleep(delay)
    finally:
        client.loop_stop()
        client.disconnect()
    return exit_code


def main() -> int:
    args = parse_args()
    input_topic = resolve_input_topic(args.input_topic, args.source_id)
    output_topic = resolve_output_topic(args.output_prefix, args.source_id)

    try:
        images = collect_images(Path(args.images_dir), args.image)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        f"plan broker={args.broker}:{args.port} input={input_topic} output={output_topic} files={len(images)}",
        flush=True,
    )
    for image_path in images:
        print(f"queue file={image_path.name} bytes={image_path.stat().st_size}", flush=True)

    if args.dry_run:
        print("dry-run complete", flush=True)
        return 0

    return run_scenario(
        broker=args.broker,
        port=args.port,
        input_topic=input_topic,
        output_topic=output_topic,
        source_id=args.source_id,
        images=images,
        qos=args.qos,
        timeout=args.timeout,
        delay=args.delay,
    )


if __name__ == "__main__":
    raise SystemExit(main())
