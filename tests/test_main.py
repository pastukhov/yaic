import json
from types import SimpleNamespace
from unittest.mock import Mock
import importlib
main = importlib.import_module("yaic.main")


def test_default_dispatch(monkeypatch):
    run = Mock()
    monkeypatch.setattr(main, 'run_mqtt', run, raising=False)
    main.main([])
    run.assert_called_once_with()


def test_classify_file(monkeypatch, tmp_path, capsys):
    import yaic.api as api
    monkeypatch.setattr(api, 'start_api_server', Mock(side_effect=AssertionError('one shot must not serve HTTP')))
    image = tmp_path / 'frame.jpg'
    image.write_bytes(b'fake image')
    processor = Mock()
    processor.process_message.return_value = SimpleNamespace(payload={'source': 'door', 'label': 'person'})
    monkeypatch.setenv('YAIC_LANGUAGE', 'en')
    monkeypatch.setattr(main, 'build_processor', lambda config: processor, raising=False)
    main.main(['classify', '--image', str(image), '--source-id', 'door'])
    processor.process_message.assert_called_once_with(b'fake image', 'door')
    output = json.loads(capsys.readouterr().out)
    assert output['label'] == 'person'
    assert 'image_b64' not in output


def test_event_only_without_language_or_mqtt(monkeypatch, tmp_path):
    import yaic.api as api
    monkeypatch.setattr(api, 'start_api_server', Mock())
    import yaic.tuya_runner as runner
    import yaic.tuya_source as source
    config = tmp_path / 'external.json'
    config.write_text('{}')
    run = Mock()
    monkeypatch.delenv('YAIC_LANGUAGE', raising=False)
    monkeypatch.setattr(source, 'TuyaSource', lambda *args: object())
    monkeypatch.setattr(runner, 'TuyaRunner', lambda *args, **kwargs: SimpleNamespace(run=run))
    monkeypatch.setattr(main, 'build_processor', Mock(side_effect=AssertionError('not event only')))
    main.main(['listen-tuya', '--device-config', str(config), '--source-id', 'door'])
    run.assert_called_once()
    api.start_api_server.assert_called_once()


def test_failure_is_stderr_and_nonzero(monkeypatch, capsys):
    import pytest
    monkeypatch.setenv('YAIC_LANGUAGE','en')
    with pytest.raises(SystemExit) as exc:
        main.main(['classify','--image','/does-not-exist','--source-id','door'])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'Classification failed' in captured.err


def test_standalone_import_does_not_load_mqtt_or_face():
    import subprocess
    import sys
    completed = subprocess.run([sys.executable,'-c',"import yaic.main,sys; assert 'paho.mqtt.client' not in sys.modules; assert 'yaic.face_recognition' not in sys.modules; assert 'yaic.api' not in sys.modules"],capture_output=True,text=True)
    assert completed.returncode == 0, completed.stderr
