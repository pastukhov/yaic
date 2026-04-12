from __future__ import annotations

import os
from dataclasses import dataclass

from .vlm_client import OPENROUTER_ENDPOINT, DEFAULT_MODEL


@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    mqtt_topic_in: str
    mqtt_topic_out: str
    mqtt_topic_status: str
    mqtt_topic_log: str
    vlm_api_key: str
    vlm_endpoint: str
    vlm_model: str
    log_level: str
    yaic_language: str
    inference_timeout: float = 60.0
    inference_temperature: float = 0.1


def load_config() -> Config:
    mqtt_host = os.getenv("MQTT_HOST")
    mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_topic_in = os.getenv("MQTT_TOPIC_IN")
    mqtt_topic_out = os.getenv("MQTT_TOPIC_OUT")
    mqtt_topic_status = os.getenv("MQTT_TOPIC_STATUS")
    mqtt_topic_log = os.getenv("MQTT_TOPIC_LOG")
    vlm_api_key = os.getenv("VLM_API_KEY", "none")
    vlm_endpoint = os.getenv("VLM_ENDPOINT", OPENROUTER_ENDPOINT)
    vlm_model = os.getenv("VLM_MODEL", DEFAULT_MODEL)
    log_level = os.getenv("LOG_LEVEL", "INFO")
    yaic_language = os.getenv("YAIC_LANGUAGE")
    inference_timeout = float(os.getenv("YAIC_INFERENCE_TIMEOUT", "60"))
    inference_temperature = float(os.getenv("YAIC_INFERENCE_TEMPERATURE", "0.1"))

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
        vlm_api_key=vlm_api_key,
        vlm_endpoint=vlm_endpoint,
        vlm_model=vlm_model,
        log_level=log_level,
        yaic_language=yaic_language,
        inference_timeout=inference_timeout,
        inference_temperature=inference_temperature,
    )
