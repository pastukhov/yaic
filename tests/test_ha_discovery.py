from yaic.config import Config
from yaic.ha_discovery import (
    build_discovery_messages,
    build_event_topic,
    build_image_topic,
    build_operation_status_topic,
    build_output_topic,
    build_status_topic,
)


def test_discovery_payloads_include_device_block():
    config = Config(
        mqtt_host="host",
        mqtt_port=1883,
        mqtt_topic_in="yaic/input/+/image",
        mqtt_topic_out="yaic/output",
        mqtt_topic_status="yaic/status",
        mqtt_topic_log="yaic/log",
        qwen_api_key="key",
        qwen_endpoint="http://example",
        qwen_model="model",
        log_level="INFO",
        yaic_language="en",
    )

    messages = build_discovery_messages(config, sw_version="1.2.3", source_id="cam1")

    for message in messages:
        assert message.retain is True
        assert message.payload["device"]["sw_version"] == "1.2.3"
        assert message.payload["device"]["identifiers"] == ["yaic_cam1"]


def test_discovery_topics_for_camera_and_event():
    config = Config(
        mqtt_host="host",
        mqtt_port=1883,
        mqtt_topic_in="yaic/input/+/image",
        mqtt_topic_out="yaic/output",
        mqtt_topic_status="yaic/status",
        mqtt_topic_log="yaic/log",
        qwen_api_key="key",
        qwen_endpoint="http://example",
        qwen_model="model",
        log_level="INFO",
        yaic_language="en",
    )

    messages = build_discovery_messages(config, sw_version="1.2.3", source_id="front")
    camera_topics = {msg.payload.get("topic") for msg in messages}
    event_topics = {msg.payload.get("state_topic") for msg in messages}
    state_topics = {msg.payload.get("state_topic") for msg in messages if msg.payload.get("state_topic")}

    assert build_image_topic("front") in camera_topics
    assert build_event_topic("front") in event_topics
    assert build_output_topic(config, "front") in state_topics
    assert build_status_topic(config, "front") in {
        msg.payload.get("availability_topic") for msg in messages
    }
    assert build_operation_status_topic(config, "front").endswith("/operation")
