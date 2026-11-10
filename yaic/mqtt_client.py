from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

from .config import Config
from .mqtt_topics import (
    build_operation_status_topic,
    build_output_topic,
    build_status_topic,
)
from .processor import Processor

logger = logging.getLogger(__name__)


class MqttClient:
    def __init__(self, config: Config, processor: Processor, metrics=None) -> None:
        from .metrics import metrics as default_metrics
        self._metrics = metrics if metrics is not None else default_metrics
        self._config = config
        self._processor = processor
        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
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
        self._metrics.mqtt_connected.set(int(rc == 0))
        if rc != 0:
            logger.error("MQTT connection failed with rc=%s", rc)
            return
        logger.info("MQTT connected; subscribing to %s", self._config.mqtt_topic_in)
        for source_id in sorted(self._known_sources):
            self._publish_status(source_id, "online")
        client.subscribe(self._config.mqtt_topic_in, qos=1)
        status_prefix = self._config.mqtt_topic_status.rstrip("/")
        client.subscribe(f"{status_prefix}/+", qos=1)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        self._metrics.mqtt_connected.set(0)
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
        logger.info("Processing image from source=%s bytes=%d", source_id, len(msg.payload))
        try:
            self._publish_operation_status(source_id, "processing")
            result = self._processor.process_message(msg.payload, source_id)
        except Exception:
            logger.exception("Failed to process MQTT message from source=%s", source_id)
            self._publish_operation_status(source_id, "error")
            return

        try:
            output = {
                **result.payload,
                "image_b64": base64.b64encode(result.image_bytes).decode("ascii"),
            }
            payload = json.dumps(output, separators=(",", ":"))
        except (TypeError, ValueError):
            logger.exception("Failed to serialize output JSON for source=%s", source_id)
            self._publish_operation_status(source_id, "error")
            return

        output_bytes = len(payload.encode("utf-8"))
        if output_bytes > self._config.mqtt_max_output_bytes:
            logger.error(
                "Output too large for source=%s bytes=%d limit=%d",
                source_id, output_bytes, self._config.mqtt_max_output_bytes,
            )
            self._publish_operation_status(source_id, "error")
            return

        label = result.payload.get("label", "unknown")
        confidence = result.payload.get("confidence", 0.0)
        person_count = result.payload.get("person", {}).get("count", 0)
        output_topic = build_output_topic(self._config, source_id)
        logger.info(
            "Classified source=%s label=%s confidence=%.2f people=%d -> %s",
            source_id, label, confidence, person_count, output_topic,
        )

        try:
            info = self._publish("output", output_topic, payload=payload, qos=1, retain=False)
        except Exception as exc:
            # Exception messages can contain payload data; log only their type.
            logger.error(
                "Output publish raised for source=%s error_type=%s",
                source_id, type(exc).__name__,
            )
            self._publish_operation_status(source_id, "error")
            return
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error("Output publish failed for source=%s rc=%s", source_id, info.rc)
            self._publish_operation_status(source_id, "error")
            return
        self._publish_operation_status(source_id, "idle")

    def _extract_source_id(self, topic: str) -> str | None:
        template = self._config.mqtt_topic_in.split("/")
        parts = topic.split("/")
        if template.count("+") != 1 or "#" in template or len(parts) != len(template):
            return None
        source_id = None
        for expected, actual in zip(template, parts):
            if expected == "+":
                if not actual or actual.strip() != actual or any(c in actual for c in "+#\x00"):
                    return None
                source_id = actual
            elif expected != actual:
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
        self._publish_status(source_id, "online")

    def _publish_status(self, source_id: str, status: str) -> None:
        self._publish("status", build_status_topic(self._config, source_id), payload=status, qos=1, retain=True)

    def _publish_operation_status(self, source_id: str, status: str) -> None:
        payload = json.dumps(
            {"source": source_id, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()},
            separators=(",", ":"),
        )
        self._publish("operation", build_operation_status_topic(self._config, source_id), payload=payload, qos=1)

    def _publish(self, kind, *args, **kwargs):
        try:
            info = self._client.publish(*args, **kwargs)
        except Exception:
            self._metrics.publishes.labels(kind, 'error').inc()
            raise
        outcome = 'success' if info.rc == mqtt.MQTT_ERR_SUCCESS else 'error'
        self._metrics.publishes.labels(kind, outcome).inc()
        return info

    def _attach_log_handler(self) -> None:
        if self._log_handler is not None:
            return
        self._log_handler = _MqttLogHandler(self._client, self._config.mqtt_topic_log, self._metrics)
        self._log_handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(self._log_handler)

    def _detach_log_handler(self) -> None:
        if self._log_handler is None:
            return
        logging.getLogger().removeHandler(self._log_handler)
        self._log_handler = None


class _MqttLogHandler(logging.Handler):
    def __init__(self, client: mqtt.Client, topic: str, metrics=None) -> None:
        super().__init__()
        self._client = client
        from .metrics import metrics as default_metrics
        self._metrics = metrics if metrics is not None else default_metrics
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
            info = self._client.publish(
                self._topic,
                payload=json.dumps(payload, separators=(",", ":")),
                qos=1,
            )
            outcome = "success" if info.rc == mqtt.MQTT_ERR_SUCCESS else "error"
            self._metrics.publishes.labels("log", outcome).inc()
        except Exception:
            self._metrics.publishes.labels("log", "error").inc()
