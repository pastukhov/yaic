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
    ha_token: str = ""
    inference_timeout: float = 60.0
    inference_temperature: float = 0.1
    # Face recognition (optional; disabled when chroma_host is empty)
    chroma_host: str = ""
    chroma_port: int = 8000
    faces_dir: str = "/app/faces"
    face_similarity_high: float = 0.85
    face_similarity_low: float = 0.60
    classify_stranger_role: bool = True
    face_index_on_startup: bool = True
    # HTTP API
    api_host: str = "0.0.0.0"
    api_port: int = 8080


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
    ha_token = os.getenv("HA_TOKEN", "")
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

    chroma_host = os.getenv("CHROMA_HOST", "")
    chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
    faces_dir = os.getenv("FACES_DIR", "/app/faces")
    face_similarity_high = float(os.getenv("FACE_SIMILARITY_HIGH", "0.85"))
    face_similarity_low = float(os.getenv("FACE_SIMILARITY_LOW", "0.60"))
    classify_stranger_role = os.getenv("CLASSIFY_STRANGER_ROLE", "true").lower() == "true"
    face_index_on_startup = os.getenv("FACE_INDEX_ON_STARTUP", "true").lower() == "true"
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", "8080"))

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
        ha_token=ha_token,
        inference_timeout=inference_timeout,
        inference_temperature=inference_temperature,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
        faces_dir=faces_dir,
        face_similarity_high=face_similarity_high,
        face_similarity_low=face_similarity_low,
        classify_stranger_role=classify_stranger_role,
        face_index_on_startup=face_index_on_startup,
        api_host=api_host,
        api_port=api_port,
    )
