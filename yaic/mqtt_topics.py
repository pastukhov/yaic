"""Topic helpers for the configured MQTT transport."""
from .config import Config

STATUS_OPERATION_SUFFIX = "operation"


def build_output_topic(config: Config, source_id: str = "") -> str:
    return config.mqtt_topic_out


def build_status_topic(config: Config, source_id: str) -> str:
    prefix = config.mqtt_topic_status.rstrip("/")
    return f"{prefix}/{source_id}"


def build_operation_status_topic(config: Config, source_id: str) -> str:
    return f"{build_status_topic(config, source_id)}/{STATUS_OPERATION_SUFFIX}"
