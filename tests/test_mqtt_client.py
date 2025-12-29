import json
from dataclasses import dataclass

from yaic.config import Config
from yaic.mqtt_client import MqttClient
from yaic.processor import ProcessingResult


class DummyProcessor:
    def __init__(self) -> None:
        self.calls = []

    def process_message(self, payload: bytes, source_id: str) -> ProcessingResult:
        self.calls.append((payload, source_id))
        return ProcessingResult(
            payload={
                "label": "ok",
                "confidence": 0.5,
                "person": {},
                "source": source_id,
            },
            image_bytes=f"img-{source_id}".encode("utf-8"),
            people=(),
        )


class FakeMqttClient:
    def __init__(self) -> None:
        self.published = []
        self.subscriptions = []

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.published.append(
            {"topic": topic, "payload": payload, "qos": qos, "retain": retain}
        )

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))

    def connect_async(self, host, port, keepalive=60):
        return None

    def loop_start(self):
        return None

    def disconnect(self):
        return None

    def loop_stop(self):
        return None

    def reconnect_delay_set(self, min_delay, max_delay):
        return None


@dataclass
class FakeMessage:
    topic: str
    payload: bytes


def build_config() -> Config:
    return Config(
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


def test_subscribes_to_input_mask(monkeypatch):
    fake_client = FakeMqttClient()
    monkeypatch.setattr("paho.mqtt.client.Client", lambda: fake_client)

    mqtt_client = MqttClient(build_config(), DummyProcessor(), sw_version="1.0.0")
    mqtt_client._on_connect(fake_client, None, {}, 0)

    assert ("yaic/input/+/image", 1) in fake_client.subscriptions
    assert ("yaic/status/+", 1) in fake_client.subscriptions


def test_handles_multiple_sources(monkeypatch):
    fake_client = FakeMqttClient()
    monkeypatch.setattr("paho.mqtt.client.Client", lambda: fake_client)

    processor = DummyProcessor()
    mqtt_client = MqttClient(build_config(), processor, sw_version="1.0.0")
    mqtt_client._on_connect(fake_client, None, {}, 0)

    mqtt_client._on_message(
        fake_client, None, FakeMessage(topic="yaic/input/cam1/image", payload=b"img1")
    )
    mqtt_client._on_message(
        fake_client,
        None,
        FakeMessage(topic="yaic/input/front_door/image", payload=b"img2"),
    )

    topics = {item["topic"] for item in fake_client.published}
    assert "yaic/output/cam1/classification" in topics
    assert "yaic/output/front_door/classification" in topics
    assert "yaic/image/cam1/last" in topics
    assert "yaic/image/front_door/last" in topics
    assert "yaic/event/cam1" in topics
    assert "yaic/event/front_door" in topics
    assert "yaic/status/cam1" in topics
    assert "yaic/status/front_door" in topics

    payloads = [
        json.loads(item["payload"])
        for item in fake_client.published
        if item["topic"].startswith("yaic/output/")
    ]
    assert {payload["source"] for payload in payloads} == {"cam1", "front_door"}

    event_payloads = [
        json.loads(item["payload"])
        for item in fake_client.published
        if item["topic"].startswith("yaic/event/")
    ]
    assert {payload["source"] for payload in event_payloads} == {"cam1", "front_door"}

    discovery_topics = {
        item["topic"]
        for item in fake_client.published
        if item["topic"].startswith("homeassistant/")
    }
    assert "homeassistant/sensor/yaic_cam1_classification/config" in discovery_topics
    assert (
        "homeassistant/sensor/yaic_front_door_classification/config" in discovery_topics
    )
