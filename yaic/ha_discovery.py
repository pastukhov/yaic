from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Config

DISCOVERY_PREFIX = "homeassistant"
STATUS_OPERATION_SUFFIX = "operation"
IMAGE_TOPIC_TEMPLATE = "yaic/image/{source_id}/last"
EVENT_TOPIC_TEMPLATE = "yaic/event/{source_id}"
OUTPUT_TOPIC_TEMPLATE = "yaic/output/{source_id}/classification"


@dataclass(frozen=True)
class DiscoveryMessage:
    topic: str
    payload: dict[str, Any]
    retain: bool = True
    qos: int = 1


def build_device_block(sw_version: str, source_id: str) -> dict[str, Any]:
    return {
        "identifiers": [f"yaic_{source_id}"],
        "name": f"YAIC {source_id}",
        "manufacturer": "YAIC",
        "model": "MQTT Vision Classifier",
        "sw_version": sw_version,
    }

def build_output_topic(config: Config, source_id: str) -> str:
    prefix = config.mqtt_topic_out.rstrip("/")
    return f"{prefix}/{source_id}/classification"


def build_status_topic(config: Config, source_id: str) -> str:
    prefix = config.mqtt_topic_status.rstrip("/")
    return f"{prefix}/{source_id}"


def build_operation_status_topic(config: Config, source_id: str) -> str:
    return f"{build_status_topic(config, source_id)}/{STATUS_OPERATION_SUFFIX}"


def build_image_topic(source_id: str) -> str:
    return IMAGE_TOPIC_TEMPLATE.format(source_id=source_id)


def build_event_topic(source_id: str) -> str:
    return EVENT_TOPIC_TEMPLATE.format(source_id=source_id)


def build_discovery_messages(config: Config, sw_version: str, source_id: str) -> list[DiscoveryMessage]:
    device = build_device_block(sw_version, source_id)
    state_topic = build_output_topic(config, source_id)
    availability_topic = build_status_topic(config, source_id)
    discovery_suffix = f"yaic_{source_id}"

    messages = [
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/sensor/{discovery_suffix}_classification/config",
            payload={
                "name": f"YAIC {source_id} Classification",
                "uniq_id": f"{discovery_suffix}_class_sensor",
                "state_topic": state_topic,
                "value_template": "{{ value_json.label }}",
                "json_attributes_topic": state_topic,
                "icon": "mdi:image-search",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/sensor/{discovery_suffix}_confidence/config",
            payload={
                "name": f"YAIC {source_id} Confidence",
                "uniq_id": f"{discovery_suffix}_confidence",
                "state_topic": state_topic,
                "unit_of_measurement": "%",
                "value_template": "{{ (value_json.confidence * 100) | round(1) }}",
                "icon": "mdi:percent",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/sensor/{discovery_suffix}_people_count/config",
            payload={
                "name": f"YAIC {source_id} People Count",
                "uniq_id": f"{discovery_suffix}_people_count",
                "state_topic": state_topic,
                "value_template": "{{ value_json.person.count | default(0) }}",
                "icon": "mdi:account-multiple",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/sensor/{discovery_suffix}_people_description/config",
            payload={
                "name": f"YAIC {source_id} People Description",
                "uniq_id": f"{discovery_suffix}_people_description",
                "state_topic": state_topic,
                "value_template": "{{ value_json.person.description | default('no data') }}",
                "icon": "mdi:text",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/sensor/{discovery_suffix}_people_age/config",
            payload={
                "name": f"YAIC {source_id} People Age Groups",
                "uniq_id": f"{discovery_suffix}_people_age",
                "state_topic": state_topic,
                "value_template": "{{ value_json.person.age_summary | default('unknown') }}",
                "icon": "mdi:calendar-clock",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/sensor/{discovery_suffix}_people_gender/config",
            payload={
                "name": f"YAIC {source_id} People Gender",
                "uniq_id": f"{discovery_suffix}_people_gender",
                "state_topic": state_topic,
                "value_template": "{{ value_json.person.gender_summary | default('unknown') }}",
                "icon": "mdi:account-group",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/sensor/{discovery_suffix}_people_roles/config",
            payload={
                "name": f"YAIC {source_id} People Roles",
                "uniq_id": f"{discovery_suffix}_people_roles",
                "state_topic": state_topic,
                "value_template": "{{ value_json.person.role_summary | default('unknown') }}",
                "icon": "mdi:briefcase-account",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/binary_sensor/{discovery_suffix}_person_detect/config",
            payload={
                "name": f"YAIC {source_id} Person Detected",
                "uniq_id": f"{discovery_suffix}_person_detect",
                "state_topic": state_topic,
                "value_template": "{% if value_json.person.count | default(0) | int > 0 %}\n"
                "  on\n"
                "{% else %}\n"
                "  off\n"
                "{% endif %}",
                "icon": "mdi:account",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/camera/{discovery_suffix}_last/config",
            payload={
                "name": f"YAIC {source_id} Last Image",
                "uniq_id": f"{discovery_suffix}_last",
                "topic": build_image_topic(source_id),
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
        DiscoveryMessage(
            topic=f"{DISCOVERY_PREFIX}/event/{discovery_suffix}_event/config",
            payload={
                "name": f"YAIC {source_id} Event",
                "uniq_id": f"{discovery_suffix}_event",
                "state_topic": build_event_topic(source_id),
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            },
        ),
    ]

    return messages
