from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

from .config import Config
from .ha_discovery import (
    build_discovery_messages,
    build_event_topic,
    build_image_topic,
    build_operation_status_topic,
    build_output_topic,
    build_status_topic,
)
from .processor import ProcessingResult, Processor

logger = logging.getLogger(__name__)


class MqttClient:
    def __init__(self, config: Config, processor: Processor, sw_version: str) -> None:
        self._config = config
        self._processor = processor
        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._sw_version = sw_version
        self._known_sources: set[str] = set()
        self._log_handler: logging.Handler | None = None

    def start(self) -> None:
        logger.info("Connecting to MQTT broker %s:%s", self._config.mqtt_host, self._config.mqtt_port)
        self._attach_log_handler()
        self._client.connect_async(self._config.mqtt_host, self._config.mqtt_port, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        logger.info("Stopping MQTT client")
        for source_id in sorted(self._known_sources):
            self._publish_status(source_id, "offline")
        self._detach_log_handler()
        self._client.disconnect()
        self._client.loop_stop()

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: dict[str, Any], rc: int) -> None:
        if rc != 0:
            logger.error("MQTT connection failed with rc=%s", rc)
            return
        logger.info("MQTT connected; subscribing to %s", self._config.mqtt_topic_in)
        for source_id in sorted(self._known_sources):
            self._publish_discovery(source_id)
        client.subscribe(self._config.mqtt_topic_in, qos=1)
        status_prefix = self._config.mqtt_topic_status.rstrip("/")
        client.subscribe(f"{status_prefix}/+", qos=1)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        if rc != 0:
            logger.warning("MQTT disconnected unexpectedly (rc=%s)", rc)
        else:
            logger.info("MQTT disconnected")

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        source_id = self._extract_source_id(msg.topic)
        if source_id is None:
            status_source = self._extract_status_source_id(msg.topic)
            if status_source:
                self._register_source(status_source)
            else:
                logger.warning("Ignoring MQTT message on unexpected topic %s", msg.topic)
            return

        self._register_source(source_id)
        try:
            self._publish_operation_status(source_id, "processing")
            result = self._processor.process_message(msg.payload, source_id)
        except Exception:
            logger.exception("Failed to process MQTT message")
            self._publish_operation_status(source_id, "error")
            return

        try:
            payload = json.dumps(result.payload, separators=(",", ":"))
        except (TypeError, ValueError):
            logger.exception("Failed to serialize output JSON")
            self._publish_operation_status(source_id, "error")
            return

        client.publish(build_output_topic(self._config, source_id), payload=payload, qos=1)
        client.publish(build_image_topic(source_id), payload=result.image_bytes, qos=1, retain=True)
        client.publish(
            build_event_topic(source_id),
            payload=json.dumps(self._build_event_payload(result, source_id), separators=(",", ":")),
            qos=1,
        )
        self._publish_operation_status(source_id, "idle")

    def _build_event_payload(self, result: ProcessingResult, source_id: str) -> dict[str, Any]:
        person = result.payload.get("person", {})
        return {
            "event_type": "classified",
            "source": source_id,
            "label": result.payload.get("label", "unknown"),
            "confidence": result.payload.get("confidence", 0.0),
            "person_count": person.get("count", 0),
            "people": [detail.to_payload() for detail in result.people],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_source_id(self, topic: str) -> str | None:
        parts = topic.split("/")
        if len(parts) != 4:
            return None
        if parts[0] != "yaic" or parts[1] != "input" or parts[3] != "image":
            return None
        source_id = parts[2].strip()
        if not source_id or source_id == "+":
            return None
        return source_id

    def _extract_status_source_id(self, topic: str) -> str | None:
        base = self._config.mqtt_topic_status.rstrip("/")
        if not topic.startswith(f"{base}/"):
            return None
        remainder = topic[len(base) + 1 :]
        parts = remainder.split("/")
        if len(parts) < 1 or not parts[0]:
            return None
        source_id = parts[0].strip()
        if not source_id or source_id == "+":
            return None
        return source_id

    def _register_source(self, source_id: str) -> None:
        if source_id in self._known_sources:
            return
        self._known_sources.add(source_id)
        self._publish_discovery(source_id)
        self._publish_status(source_id, "online")

    def _publish_discovery(self, source_id: str) -> None:
        messages = build_discovery_messages(self._config, self._sw_version, source_id)
        for message in messages:
            self._client.publish(
                message.topic,
                payload=json.dumps(message.payload, separators=(",", ":")),
                qos=message.qos,
                retain=message.retain,
            )

    def _publish_status(self, source_id: str, status: str) -> None:
        self._client.publish(build_status_topic(self._config, source_id), payload=status, qos=1, retain=True)

    def _publish_operation_status(self, source_id: str, status: str) -> None:
        payload = json.dumps(
            {"source": source_id, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()},
            separators=(",", ":"),
        )
        self._client.publish(build_operation_status_topic(self._config, source_id), payload=payload, qos=1)

    def _attach_log_handler(self) -> None:
        if self._log_handler is not None:
            return
        self._log_handler = _MqttLogHandler(self._client, self._config.mqtt_topic_log)
        self._log_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(self._log_handler)

    def _detach_log_handler(self) -> None:
        if self._log_handler is None:
            return
        logging.getLogger().removeHandler(self._log_handler)
        self._log_handler = None


class _MqttLogHandler(logging.Handler):
    def __init__(self, client: mqtt.Client, topic: str) -> None:
        super().__init__()
        self._client = client
        self._topic = topic.rstrip("/")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
            self._client.publish(
                self._topic,
                payload=json.dumps(payload, separators=(",", ":")),
                qos=1,
            )
        except Exception:
            pass
