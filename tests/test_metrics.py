from prometheus_client import CollectorRegistry, generate_latest
from yaic.metrics import Metrics


def test_usage_missing_zero_and_isolated_registry():
    m = Metrics()
    m.usage(
        {"usage": {"prompt_tokens": 0, "completion_tokens": 3}}, "model", "classify"
    )
    m.usage({}, "model", "classify")
    assert (
        m.registry.get_sample_value(
            "yaic_vlm_tokens_total",
            {"model": "model", "operation": "classify", "direction": "input"},
        )
        == 0
    )
    assert (
        m.registry.get_sample_value(
            "yaic_vlm_usage_missing_total", {"model": "model", "operation": "classify"}
        )
        == 1
    )
    assert b"yaic_vlm_tokens_total{" not in generate_latest(Metrics().registry)


def test_device_validation_timestamp_and_invalidation():
    m = Metrics(clock=lambda: 123)
    m.observe_device({"dps": {"104": True, "134": False, "109": "100|20|80"}})
    assert (
        m.registry.get_sample_value(
            "yaic_device_setting", {"setting": "timestamp_overlay"}
        )
        == 1
    )
    assert (
        m.registry.get_sample_value(
            "yaic_device_setting_observed_timestamp_seconds",
            {"setting": "motion_detection"},
        )
        == 123
    )
    m.observe_device({"dps": {"104": "private arbitrary text"}})
    assert (
        m.registry.get_sample_value(
            "yaic_device_setting", {"setting": "timestamp_overlay"}
        )
        is None
    )
    assert b"private arbitrary" not in generate_latest(m.registry)


def test_stage_failure_is_timed_and_counted():
    import pytest

    m = Metrics()
    with pytest.raises(ValueError), m.stage("pipeline"):
        raise ValueError("private")
    assert (
        m.registry.get_sample_value(
            "yaic_stage_total", {"stage": "pipeline", "outcome": "error"}
        )
        == 1
    )
    assert (
        m.registry.get_sample_value(
            "yaic_stage_duration_seconds_count", {"stage": "pipeline"}
        )
        == 1
    )


def test_provider_usage_survives_invalid_content_and_format_retry(monkeypatch):
    from yaic.vlm_client import VlmClient
    import pytest

    m = Metrics()

    class Response:
        status_code = 400

        def json(self):
            return {"usage": {"prompt_tokens": 4, "completion_tokens": 2}}

        def raise_for_status(self):
            pass

    responses = [Response(), Response()]
    responses[1].status_code = 200
    monkeypatch.setattr(
        "yaic.vlm_client.requests.post", lambda *a, **kw: responses.pop(0)
    )
    client = VlmClient("secret", model="configured", metrics=m)
    with pytest.raises(ValueError):
        client.classify_role(b"image", "prompt")
    assert (
        m.registry.get_sample_value(
            "yaic_vlm_tokens_total",
            {"model": "configured", "operation": "role", "direction": "input"},
        )
        == 8
    )
    for outcome in ("success", "error"):
        assert m.registry.get_sample_value("yaic_stage_total", {"stage": "vlm_role", "outcome": outcome}) == 1


def test_only_safe_dps_are_polled():
    from yaic.tuya_source import READ_DPS

    assert READ_DPS == ("109", "110")


def test_metrics_endpoint_without_faces():
    from fastapi.testclient import TestClient
    from yaic.api import app

    response = TestClient(app).get("/metrics")
    assert response.status_code == 200
    assert "yaic_mqtt_connected" in response.text


def test_mqtt_connection_and_publish_failure(monkeypatch):
    from tests.test_mqtt_client import FakeMqttClient, DummyProcessor, build_config
    from yaic.mqtt_client import MqttClient
    from types import SimpleNamespace

    m = Metrics()
    fake = FakeMqttClient()
    monkeypatch.setattr("paho.mqtt.client.Client", lambda: fake)
    client = MqttClient(build_config(), DummyProcessor(), metrics=m)
    client._on_connect(fake, None, {}, 0)
    assert m.registry.get_sample_value("yaic_mqtt_connected") == 1
    fake.publish = lambda *a, **kw: SimpleNamespace(rc=4)
    client._publish_operation_status("private-device", "idle")
    assert (
        m.registry.get_sample_value(
            "yaic_mqtt_publish_total", {"kind": "operation", "outcome": "error"}
        )
        == 1
    )
    client._on_disconnect(fake, None, 1)
    assert m.registry.get_sample_value("yaic_mqtt_connected") == 0


def test_pipeline_last_success_only_updates_after_success():
    import pytest

    m = Metrics(clock=lambda: 321)
    labels = {"stage": "pipeline"}
    assert (
        m.registry.get_sample_value("yaic_last_success_timestamp_seconds", labels)
        is None
    )
    with m.stage("pipeline"):
        pass
    assert (
        m.registry.get_sample_value("yaic_last_success_timestamp_seconds", labels)
        == 321
    )
    m.clock = lambda: 999
    with pytest.raises(ValueError), m.stage("pipeline"):
        raise ValueError()
    assert (
        m.registry.get_sample_value("yaic_last_success_timestamp_seconds", labels)
        == 321
    )


def test_unknown_device_observations_are_absent():
    m = Metrics()
    assert (
        m.registry.get_sample_value(
            "yaic_device_observed_timestamp_seconds", {"transport": "lan"}
        )
        is None
    )


def test_all_vlm_operations_report_usage(monkeypatch):
    from yaic.vlm_client import VlmClient

    m = Metrics()
    payloads = [
        {"label": "person", "confidence": 0.9, "person": {"count": 1}},
        {"label": "person", "person": {"count": 1, "details": [{"role": "stranger"}]}},
        {"role": "stranger"},
        {"same_person": False},
    ]

    class Response:
        status_code = 200

        def __init__(self, content):
            import json

            self.data = {
                "usage": {"prompt_tokens": 7, "completion_tokens": 2},
                "choices": [{"message": {"content": json.dumps(content)}}],
            }

        def json(self):
            return self.data

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "yaic.vlm_client.requests.post", lambda *a, **kw: Response(payloads.pop(0))
    )
    client = VlmClient("private-key", model="model", metrics=m)
    client.classify_image(b"image")
    client.classify_role(b"image", "prompt")
    client.verify_same_person(b"ref", b"query", "private-name")
    for operation in ("classify", "details", "role", "verify_identity"):
        assert (
            m.registry.get_sample_value(
                "yaic_vlm_tokens_total",
                {"model": "model", "operation": operation, "direction": "input"},
            )
            == 7
        )
    assert b"private-name" not in generate_latest(m.registry)


def test_device_modes_zone_and_staleness():
    now = [1]
    m = Metrics(clock=lambda: now[0])
    m.observe_device(
        {
            "dps": {
                "169": "{num:1,region0:{x:16,xlen:63,y:9,ylen:90}}\n",
                "110": 5,
                "239": "Ring",
                "231": '{"res":1,"err":0,"cc":2,"chs":[{"id":2,"n":"private"}]}',
            }
        }
    )
    for setting, expected in [
        ("motion_area_x_percent", 16),
        ("sd_status_code", 5),
        ("panel_1_ring", 1),
        ("channel_selected", 2),
    ]:
        assert (
            m.registry.get_sample_value("yaic_device_setting", {"setting": setting})
            == expected
        )
    now[0] = 10
    m.observe_device({"dps": {"104": False}})
    assert (
        m.registry.get_sample_value(
            "yaic_device_setting_observed_timestamp_seconds",
            {"setting": "sd_status_code"},
        )
        == 1
    )
    m.observe_device({"dps": {"169": "invalid", "110": 99, "231": "{}"}})
    for setting in ("motion_area_x_percent", "sd_status_code", "channel_selected"):
        assert (
            m.registry.get_sample_value("yaic_device_setting", {"setting": setting})
            is None
        )
    assert b"private" not in generate_latest(m.registry)


def test_channel_valid_json_with_wrong_shape_does_not_interrupt_listener():
    m = Metrics()
    for raw in ("[]", "null", "1", "true", '"private"'):
        m.observe_device({"dps": {"231": raw}})
    assert (
        m.registry.get_sample_value(
            "yaic_device_setting", {"setting": "channel_selected"}
        )
        is None
    )


def test_http_rejection_is_failed_stage_without_success_timestamp(monkeypatch):
    from yaic.vlm_client import VlmClient

    m = Metrics(clock=lambda: 123)

    class Response:
        status_code = 401

        def json(self):
            return {"usage": {"prompt_tokens": 1, "completion_tokens": 0}}

    monkeypatch.setattr("yaic.vlm_client.requests.post", lambda *a, **kw: Response())
    client = VlmClient("secret", metrics=m)
    assert client._request("classify").status_code == 401
    assert (
        m.registry.get_sample_value(
            "yaic_stage_total", {"stage": "vlm_classify", "outcome": "error"}
        )
        == 1
    )
    assert (
        m.registry.get_sample_value(
            "yaic_last_success_timestamp_seconds", {"stage": "vlm_classify"}
        )
        is None
    )
