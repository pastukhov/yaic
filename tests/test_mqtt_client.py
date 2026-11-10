import json
from types import SimpleNamespace
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
        return SimpleNamespace(rc=0)

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
        vlm_api_key="key",
        vlm_endpoint="http://example",
        vlm_model="model",
        log_level="INFO",
        yaic_language="en",
        inference_timeout=60.0,
        inference_temperature=0.1,
    )


def test_subscribes_to_input_mask(monkeypatch):
    fake_client = FakeMqttClient()
    monkeypatch.setattr("paho.mqtt.client.Client", lambda: fake_client)

    mqtt_client = MqttClient(build_config(), DummyProcessor())
    mqtt_client._on_connect(fake_client, None, {}, 0)

    assert ("yaic/input/+/image", 1) in fake_client.subscriptions
    assert ("yaic/status/+", 1) in fake_client.subscriptions


def test_handles_multiple_sources(monkeypatch):
    fake_client = FakeMqttClient()
    monkeypatch.setattr("paho.mqtt.client.Client", lambda: fake_client)

    processor = DummyProcessor()
    mqtt_client = MqttClient(build_config(), processor)
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
    assert "yaic/output" in topics
    assert topics == {
        "yaic/output", "yaic/status/cam1", "yaic/status/front_door",
        "yaic/status/cam1/operation", "yaic/status/front_door/operation",
    }

    payloads = [
        json.loads(item["payload"])
        for item in fake_client.published
        if item["topic"] == "yaic/output"
    ]
    assert {payload["source"] for payload in payloads} == {"cam1", "front_door"}

def test_custom_input_template_publishes_only_configured_topics(monkeypatch):
    from dataclasses import replace
    fake=FakeMqttClient()
    monkeypatch.setattr('paho.mqtt.client.Client',lambda:fake)
    processor=DummyProcessor()
    config=replace(build_config(),mqtt_topic_in='isolated/probe/+/photo',
                   mqtt_topic_out='isolated/result',mqtt_topic_status='isolated/status')
    client=MqttClient(config,processor)
    client._on_message(fake,None,FakeMessage('yaic/input/door/image',b'wrong'))
    assert processor.calls==[]
    client._on_message(fake,None,FakeMessage('isolated/probe/door/photo',b'image'))
    assert processor.calls==[(b'image','door')]
    assert any(row['topic']=='isolated/result' for row in fake.published)
    assert {row['topic'] for row in fake.published} == {
        'isolated/result', 'isolated/status/door', 'isolated/status/door/operation',
    }


def test_default_mqtt_publishes_only_configured_topics(monkeypatch):
    fake = FakeMqttClient()
    monkeypatch.setattr('paho.mqtt.client.Client', lambda: fake)
    client = MqttClient(build_config(), DummyProcessor())
    client._on_message(fake, None, FakeMessage('yaic/input/door/image', b'image'))
    client._on_connect(fake, None, {}, 0)
    client.stop()
    assert {row['topic'] for row in fake.published} == {
        'yaic/output', 'yaic/status/door', 'yaic/status/door/operation',
    }
    assert [row['payload'] for row in fake.published
            if row['topic'] == 'yaic/status/door'] == ['online', 'online', 'offline']


def test_result_contains_original_image(monkeypatch, caplog):
    import base64
    import logging
    from types import SimpleNamespace

    fake = FakeMqttClient()
    monkeypatch.setattr('paho.mqtt.client.Client', lambda: fake)
    payload = {'source': 'door', 'label': 'unknown', 'confidence': 0.5,
               'person': {'count': 0}, 'device': 'camera', 'event_id': 'event-1'}
    original = dict(payload)
    result = ProcessingResult(payload, b'original-photo-secret', ())
    processor = SimpleNamespace(process_message=lambda *args: result)
    client = MqttClient(build_config(), processor)
    caplog.set_level(logging.DEBUG)
    client._attach_log_handler()
    try:
        client._on_message(fake, None, FakeMessage('yaic/input/door/image', b'input'))
    finally:
        client._detach_log_handler()
    outputs = [row for row in fake.published if row['topic'] == 'yaic/output']
    assert len(outputs) == 1
    output = json.loads(outputs[0]['payload'])
    assert base64.b64decode(output.pop('image_b64'), validate=True) == result.image_bytes
    assert output == original == payload
    assert outputs[0]['qos'] == 1 and outputs[0]['retain'] is False
    encoded = base64.b64encode(result.image_bytes).decode()
    assert encoded not in caplog.text
    assert 'original-photo-secret' not in caplog.text
    logs = [row['payload'] for row in fake.published if row['topic'] == 'yaic/log']
    assert logs and all(encoded not in row and 'original-photo-secret' not in row for row in logs)


def test_real_processor_inputs_keep_images_and_metadata(monkeypatch):
    import base64
    from types import SimpleNamespace
    from unittest.mock import Mock
    import httpx
    from yaic.processor import Processor
    from yaic.vlm_client import ClassificationResult, PersonSummary

    fake = FakeMqttClient()
    monkeypatch.setattr('paho.mqtt.client.Client', lambda: fake)
    images = [b'\xffbinary-camera', b'base64-camera', b'url-camera']
    vlm = Mock()
    vlm.classify_image.side_effect = [
        ClassificationResult(label, 0.7, PersonSummary(count, None, (), None, None, None))
        for label, count in [('person', 1), ('unknown', 0), ('person', 1)]
    ]
    get = Mock(return_value=httpx.Response(200, content=images[2],
                                         request=httpx.Request('GET', 'https://example.test/frame')))
    # Context manager special methods are looked up on the class.
    class HttpClient:
        def __enter__(self):
            return SimpleNamespace(get=get)
        def __exit__(self, *args):
            pass
    monkeypatch.setattr('yaic.processor.httpx.Client', HttpClient)
    client = MqttClient(build_config(), Processor(vlm))
    inputs = [images[0], json.dumps({'image_b64': base64.b64encode(images[1]).decode(),
                                   'device': 'second', 'event_id': 'event-2'}).encode(),
              json.dumps({'image_url': 'https://example.test/frame', 'device': 'third'}).encode()]
    for source, incoming in zip(['first', 'second', 'third'], inputs):
        client._on_message(fake, None, FakeMessage(f'yaic/input/{source}/image', incoming))
    outputs = [json.loads(row['payload']) for row in fake.published if row['topic'] == 'yaic/output']
    assert len(outputs) == 3
    for output, image, call in zip(outputs, images, vlm.classify_image.call_args_list):
        assert base64.b64decode(output['image_b64'], validate=True) == image == call.args[0]
    assert [row['source'] for row in outputs] == ['first', 'second', 'third']
    assert outputs[1]['device'] == 'second' and outputs[1]['event_id'] == 'event-2'
    assert outputs[1]['person']['count'] == 0
    assert 'event_id' not in outputs[0] and 'event_id' not in outputs[2]
    assert outputs[2]['device'] == 'third'
    get.assert_called_once()


def operation_states(fake):
    return [json.loads(row['payload'])['status'] for row in fake.published
            if row['topic'].endswith('/operation')]


def test_output_limit_uses_final_serialized_bytes(monkeypatch):
    import base64
    from dataclasses import replace
    from types import SimpleNamespace
    payload = {'source': 'door', 'label': 'unknown', 'confidence': 0.5,
               'person': {'count': 0}, 'device': 'камера'}
    result = ProcessingResult(payload, b'photo', ())
    serialized = json.dumps({**payload, 'image_b64': base64.b64encode(b'photo').decode()},
                            separators=(',', ':'))
    size = len(serialized.encode('utf-8'))
    for limit, allowed in [(size, True), (size - 1, False)]:
        fake = FakeMqttClient()
        monkeypatch.setattr('paho.mqtt.client.Client', lambda: fake)
        client = MqttClient(replace(build_config(), mqtt_max_output_bytes=limit),
                            SimpleNamespace(process_message=lambda *args: result))
        client._on_message(fake, None, FakeMessage('yaic/input/door/image', b'input'))
        outputs = [row for row in fake.published if row['topic'] == 'yaic/output']
        assert bool(outputs) == allowed
        assert operation_states(fake) == ['processing', 'idle' if allowed else 'error']
        if allowed:
            assert len(outputs[0]['payload'].encode('utf-8')) == limit


def test_publish_failure_reports_error_without_fallback(monkeypatch, caplog):
    from types import SimpleNamespace
    for failure in [4, RuntimeError('private-photo-data')]:
        fake = FakeMqttClient()
        original_publish = fake.publish
        attempts = []
        def publish(topic, **kwargs):
            if topic == 'yaic/output':
                attempts.append(kwargs)
                if isinstance(failure, Exception):
                    raise failure
                return SimpleNamespace(rc=failure)
            return original_publish(topic, **kwargs)
        fake.publish = publish
        monkeypatch.setattr('paho.mqtt.client.Client', lambda: fake)
        client = MqttClient(build_config(), DummyProcessor())
        client._on_message(fake, None, FakeMessage('yaic/input/door/image', b'input'))
        assert len(attempts) == 1
        assert 'image_b64' in json.loads(attempts[0]['payload'])
        assert operation_states(fake) == ['processing', 'error']
    assert 'private-photo-data' not in caplog.text
