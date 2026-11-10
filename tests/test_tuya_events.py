import base64
import json
import pytest
from yaic.tuya_events import decode_events


def encoded(value):
    return base64.b64encode(json.dumps(value).encode()).decode()


def test_human_is_private_and_not_a_lan_version():
    event, = decode_events({'dps': {'185': encoded({'cmd': 'ipc_human', 'v': '3.0', 'type': 'image', 'with': 'resources', 'files': [['private/path', 'fake-key-only']]})}}, 'door')
    assert event.kind == 'human_detected'
    assert event.snapshot_url is None
    assert 'private' not in json.dumps(event.to_payload())
    assert 'files' not in event.to_payload()


@pytest.mark.parametrize('response', [None, [], 'error', {'Error': 'network'}, {'dps': []}, {'dps': {'185': '!'}}, {'dps': {'185': encoded({'cmd':'other'})}}, {'dps': {'185': encoded([])}}])
def test_malformed_unknown_safe(response):
    assert decode_events(response, 'door') == []


def test_ring_idle_and_signed_image():
    events = decode_events({'dps': {'239': 'Ring', '240': 'Normal', '154': base64.b64encode(b'https://example.test/frame?secret=fake').decode()}}, 'door')
    assert [e.kind for e in events] == ['doorbell_ring', 'doorbell_idle', 'doorbell_image']
    assert events[-1].snapshot_url.startswith('https://')
    assert 'secret' not in json.dumps([e.to_payload() for e in events])


def test_panels_distinct_and_nonfinite_timestamp_omitted():
    events = decode_events({'t':float('nan'), 'dps':{'239':'Ring', '240':'Ring'}}, 'door')
    assert [event.to_payload()['panel'] for event in events] == [1,2]
    assert events[0].dedup_key != events[1].dedup_key
    assert all('device_timestamp' not in event.to_payload() for event in events)
