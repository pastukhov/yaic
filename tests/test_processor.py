import base64
import json

import pytest

from yaic.processor import Processor
from yaic.qwen_client import ClassificationResult, PersonDetail, PersonSummary, UNKNOWN


class DummyQwen:
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
    qwen = DummyQwen(result)
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
    qwen = DummyQwen(result)
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
    qwen = DummyQwen(result)
    processor = Processor(qwen)

    payload = b'{"device": "cam-2"}'
    with pytest.raises(ValueError, match="image_b64"):
        processor.process_message(payload, "cam2")
