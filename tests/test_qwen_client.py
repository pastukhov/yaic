import json

from yaic.qwen_client import QwenClient, _detect_image_mime, _extract_json_object, _strip_json_fence


def test_extract_content_json_from_list():
    client = QwenClient(api_key="key", endpoint="http://example", language="en")
    data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "{\"label\":\"cat\"}"}
                    ]
                }
            }
        ]
    }

    assert client._extract_content_json(data) == {"label": "cat"}


def test_extract_content_json_from_string_fence():
    client = QwenClient(api_key="key", endpoint="http://example", language="en")
    data = {
        "choices": [
            {
                "message": {
                    "content": "```json\n{\"label\":\"person\",\"confidence\":0.9}\n```"
                }
            }
        ]
    }

    assert client._extract_content_json(data) == {"label": "person", "confidence": 0.9}


def test_strip_json_fence():
    fenced = "```json\n{\"ok\":true}\n```"
    assert _strip_json_fence(fenced) == "{\"ok\":true}"


def test_extract_json_object_from_text():
    text = "prefix {\"ok\": true} suffix"
    assert json.loads(_extract_json_object(text)) == {"ok": True}


def test_detect_image_mime():
    png = b"\x89PNG\r\n\x1a\n" + b"data"
    jpeg = b"\xff\xd8" + b"data"
    assert _detect_image_mime(png) == "image/png"
    assert _detect_image_mime(jpeg) == "image/jpeg"
