import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from yaic.processor import Processor, ImageMessage, fetch_image_bytes
from yaic.vlm_client import ClassificationResult, PersonDetail, PersonSummary, UNKNOWN


class DummyVlm:
    def __init__(self, result: ClassificationResult) -> None:
        self.last_image = None
        self._result = result

    def classify_image(self, image_bytes: bytes):
        self.last_image = image_bytes
        return self._result


def test_process_binary_payload():
    result = ClassificationResult(
        label="cat",
        confidence=0.9,
        person=PersonSummary(
            count=0,
            description=None,
            details=(),
            age_summary=None,
            gender_summary=None,
            role_summary=None,
        ),
    )
    qwen = DummyVlm(result)
    processor = Processor(qwen)

    payload = b"binary-image"
    processed = processor.process_message(payload, "cam1")

    assert qwen.last_image == payload
    assert processed.payload == {
        "label": "cat",
        "confidence": 0.9,
        "person": {"count": 0},
        "source": "cam1",
    }


def test_process_json_payload_with_device():
    result = ClassificationResult(
        label="person",
        confidence=0.88,
        person=PersonSummary(
            count=1,
            description="one adult",
            details=(PersonDetail(age_group="adult", gender="male", appearance=UNKNOWN, role=UNKNOWN),),
            age_summary="1 adult",
            gender_summary="1 male",
            role_summary=UNKNOWN,
        ),
    )
    qwen = DummyVlm(result)
    processor = Processor(qwen)

    image_bytes = b"image-data"
    payload = json.dumps(
        {
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
            "device": "cam-1",
        }
    ).encode("utf-8")

    processed = processor.process_message(payload, "front_door")

    assert qwen.last_image == image_bytes
    assert processed.payload == {
        "label": "person",
        "confidence": 0.88,
        "person": {
            "count": 1,
            "description": "one adult",
            "details": [
                {"age_group": "adult", "gender": "male", "appearance": "unknown", "role": "unknown"}
            ],
            "age_summary": "1 adult",
            "gender_summary": "1 male",
            "role_summary": "unknown",
        },
        "device": "cam-1",
        "source": "front_door",
    }


def test_process_json_missing_image_b64():
    result = ClassificationResult(
        label="cat",
        confidence=0.9,
        person=PersonSummary(
            count=0,
            description=None,
            details=(),
            age_summary=None,
            gender_summary=None,
            role_summary=None,
        ),
    )
    qwen = DummyVlm(result)
    processor = Processor(qwen)

    payload = b'{"device": "cam-2"}'
    with pytest.raises(Exception, match="image_b64.*image_url|image_url.*image_b64"):
        processor.process_message(payload, "cam2")


def test_image_message_requires_image_source():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="image_b64.*image_url|image_url.*image_b64"):
        ImageMessage(device="cam")


def test_image_message_image_b64_valid():
    msg = ImageMessage(device="cam", image_b64="dGVzdA==")
    assert msg.image_b64 == "dGVzdA=="


def test_image_message_image_url_valid():
    msg = ImageMessage(device="cam", image_url="http://ha.local:8123/local/img.jpg")
    assert msg.image_url == "http://ha.local:8123/local/img.jpg"


def test_legacy_ha_token_is_not_forwarded_to_image_url(monkeypatch):
    import httpx
    from yaic.config import load_config
    from yaic.runtime import build_processor

    monkeypatch.setenv("YAIC_LANGUAGE", "en")
    monkeypatch.setenv("HA_TOKEN", "legacy-test-token")
    monkeypatch.setenv("CHROMA_HOST", "")
    vlm = DummyVlm(ClassificationResult(
        label="cat", confidence=0.9,
        person=PersonSummary(count=0, description=None, details=(),
                             age_summary=None, gender_summary=None, role_summary=None),
    ))
    monkeypatch.setattr("yaic.runtime.VlmClient", lambda **kwargs: vlm)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=b"downloaded-image")

    client_type = httpx.Client
    monkeypatch.setattr("yaic.processor.httpx.Client", lambda: client_type(
        transport=httpx.MockTransport(respond)))
    processor = build_processor(load_config(require_mqtt=False))
    processed = processor.process_message(json.dumps({
        "image_url": "http://homeassistant.local:8123/local/image.jpg",
        "event_id": "evt-url-123",
    }).encode(), "door")

    assert len(requests) == 1
    assert "authorization" not in requests[0].headers
    assert vlm.last_image == b"downloaded-image"
    assert processed.payload["label"] == "cat"
    assert processed.payload["event_id"] == "evt-url-123"
    assert processed.payload["source"] == "door"


def test_process_image_url_payload():
    image_bytes = b"fetched-image"
    result = ClassificationResult(
        label="cat",
        confidence=0.9,
        person=PersonSummary(
            count=0,
            description=None,
            details=(),
            age_summary=None,
            gender_summary=None,
            role_summary=None,
        ),
    )
    qwen = DummyVlm(result)
    processor = Processor(qwen)

    payload = json.dumps(
        {"image_url": "http://ha.local:8123/local/shot.jpg", "device": "domofon"}
    ).encode("utf-8")

    mock_response = MagicMock()
    mock_response.content = image_bytes
    mock_response.raise_for_status = MagicMock()

    with patch("yaic.processor.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        processed = processor.process_message(payload, "front_door")

    assert qwen.last_image == image_bytes
    assert processed.payload["device"] == "domofon"
    assert processed.payload["source"] == "front_door"
    mock_client.get.assert_called_once_with(
        "http://ha.local:8123/local/shot.jpg",
        timeout=5.0,
        follow_redirects=True,
    )


def test_event_id_correlation_preserved():
    vlm=MagicMock()
    vlm.classify_image.return_value=ClassificationResult(label='cat',confidence=.9,
        person=PersonSummary(count=0,description=None,details=(),age_summary=None,gender_summary=None,role_summary=None))
    data=json.dumps({'image_b64':base64.b64encode(b'image').decode(),'device':'door','event_id':'evt-123'}).encode()
    result=Processor(vlm).process_message(data,'door')
    assert result.payload['event_id']=='evt-123'
    assert result.payload['source']=='door'
