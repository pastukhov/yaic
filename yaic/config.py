from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    mqtt_topic_in: str
    mqtt_topic_out: str
    mqtt_topic_status: str
    mqtt_topic_log: str
    qwen_api_key: str
    qwen_endpoint: str
    qwen_model: str
    log_level: str
    yaic_language: str


def load_config() -> Config:
    mqtt_host = os.getenv("MQTT_HOST")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_topic_in = os.getenv("MQTT_TOPIC_IN")
    mqtt_topic_out = os.getenv("MQTT_TOPIC_OUT")
    mqtt_topic_status = os.getenv("MQTT_TOPIC_STATUS")
    mqtt_topic_log = os.getenv("MQTT_TOPIC_LOG")
    qwen_api_key = os.getenv("QWEN_API_KEY")
    qwen_endpoint = os.getenv("QWEN_ENDPOINT")
    qwen_model = os.getenv("QWEN_MODEL", "qwen-vl-plus")
    log_level = os.getenv("LOG_LEVEL", "INFO")
    yaic_language = os.getenv("YAIC_LANGUAGE")

    missing = []
    if not mqtt_host:
        missing.append("MQTT_HOST")
    if not mqtt_topic_in:
        missing.append("MQTT_TOPIC_IN")
    if not mqtt_topic_out:
        missing.append("MQTT_TOPIC_OUT")
    if not mqtt_topic_status:
        missing.append("MQTT_TOPIC_STATUS")
    if not mqtt_topic_log:
        missing.append("MQTT_TOPIC_LOG")
    if not qwen_api_key:
        missing.append("QWEN_API_KEY")
    if not qwen_endpoint:
        missing.append("QWEN_ENDPOINT")
    if not yaic_language:
        missing.append("YAIC_LANGUAGE")

    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"Missing required env vars: {missing_str}")

    return Config(
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_topic_in=mqtt_topic_in,
        mqtt_topic_out=mqtt_topic_out,
        mqtt_topic_status=mqtt_topic_status,
        mqtt_topic_log=mqtt_topic_log,
        qwen_api_key=qwen_api_key,
        qwen_endpoint=qwen_endpoint,
        qwen_model=qwen_model,
        log_level=log_level,
        yaic_language=yaic_language,
    )
