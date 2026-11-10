import pytest
from yaic.config import load_config


def test_standalone_does_not_require_mqtt(monkeypatch):
    for name in ('MQTT_HOST', 'MQTT_TOPIC_IN', 'MQTT_TOPIC_OUT', 'MQTT_TOPIC_STATUS', 'MQTT_TOPIC_LOG'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('YAIC_LANGUAGE', 'en')
    config = load_config(require_mqtt=False)
    assert config.mqtt_host == ''
    with pytest.raises(ValueError, match='MQTT_HOST'):
        load_config()


def test_legacy_ha_configuration_is_ignored(monkeypatch):
    monkeypatch.setenv('YAIC_LANGUAGE', 'en')
    monkeypatch.setenv('HA_TOKEN', 'legacy-test-token')
    monkeypatch.setenv('HA_DISCOVERY_ENABLED', 'true')
    config = load_config(require_mqtt=False)
    assert not hasattr(config, 'ha_token')
    assert not hasattr(config, 'ha_discovery_enabled')


def test_mqtt_output_limit_default_and_override(monkeypatch):
    monkeypatch.setenv('YAIC_LANGUAGE', 'en')
    monkeypatch.delenv('MQTT_MAX_OUTPUT_BYTES', raising=False)
    assert load_config(require_mqtt=False).mqtt_max_output_bytes == 16777216
    monkeypatch.setenv('MQTT_MAX_OUTPUT_BYTES', '123')
    assert load_config(require_mqtt=False).mqtt_max_output_bytes == 123


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'invalid'])
def test_mqtt_output_limit_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv('YAIC_LANGUAGE', 'en')
    monkeypatch.setenv('MQTT_MAX_OUTPUT_BYTES', value)
    with pytest.raises(ValueError, match='MQTT_MAX_OUTPUT_BYTES.*positive integer'):
        load_config(require_mqtt=False)
