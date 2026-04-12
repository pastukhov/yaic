import json

from yaic.vlm_client import (
    VlmClient,
    _detect_image_mime,
    _extract_json_object,
    _strip_json_fence,
    _strip_think_block,
)


def test_extract_content_json_from_list():
    client = VlmClient(api_key="key", endpoint="http://example", language="en")
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
    client = VlmClient(api_key="key", endpoint="http://example", language="en")
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


def test_strip_think_block_removes_thinking():
    text = "<think>some reasoning</think>\n{\"label\":\"person\"}"
    assert _strip_think_block(text) == "{\"label\":\"person\"}"


def test_strip_think_block_multiline():
    text = "<think>multi\nline\nthinking</think>{\"ok\":true}"
    assert _strip_think_block(text) == "{\"ok\":true}"


def test_strip_think_block_no_think():
    text = "{\"label\":\"cat\"}"
    assert _strip_think_block(text) == "{\"label\":\"cat\"}"


def test_extract_json_object_from_text():
    text = "prefix {\"ok\": true} suffix"
    assert json.loads(_extract_json_object(text)) == {"ok": True}


def test_extract_content_json_with_think_block():
    client = VlmClient(api_key="key", endpoint="http://example", language="en")
    data = {
        "choices": [
            {
                "message": {
                    "content": "<think>reasoning</think>\n{\"label\":\"person\",\"confidence\":0.9}"
                }
            }
        ]
    }

    assert client._extract_content_json(data) == {
        "label": "person",
        "confidence": 0.9,
    }


def test_extract_content_json_recovers_malformed_json():
    client = VlmClient(api_key="key", endpoint="http://example", language="en")
    data = {
        "choices": [
            {
                "message": {
                    "content": '{"label":"person","confidence":0.82,"person":{"count":1,"description":"courier"'
                }
            }
        ]
    }

    assert client._extract_content_json(data) == {
        "label": "person",
        "confidence": 0.82,
        "person": {"count": 1, "description": "courier"},
    }


def test_post_image_includes_temperature(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"choices":[{"message":{"content":"{\\"label\\":\\"cat\\"}"}}]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{\"label\":\"cat\"}"}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("yaic.vlm_client.requests.post", fake_post)

    client = VlmClient(
        api_key="key",
        endpoint="http://example",
        language="en",
        temperature=0.25,
    )

    assert client._post_image(b"image-bytes", prompt="prompt") == {"label": "cat"}
    assert captured["json"]["temperature"] == 0.25
    image_url = captured["json"]["messages"][0]["content"][0]["image_url"]["url"]
    assert isinstance(image_url, str)
    assert image_url.startswith("data:image/")


def test_post_image_sends_x_title_header(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{\"label\":\"cat\"}"}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("yaic.vlm_client.requests.post", fake_post)

    client = VlmClient(api_key="key", endpoint="http://example", language="en")
    client._post_image(b"image-bytes", prompt="prompt")

    assert captured["headers"].get("X-Title") == "YAIC"


def test_default_prompt_no_think_prefix():
    client = VlmClient(api_key="key", endpoint="http://example", language="en")
    assert not client._default_prompt().startswith("/no_think")


def test_detail_prompt_no_think_prefix():
    client = VlmClient(api_key="key", endpoint="http://example", language="en")
    assert not client._detail_prompt().startswith("/no_think")


def test_detect_image_mime():
    png = b"\x89PNG\r\n\x1a\n" + b"data"
    jpeg = b"\xff\xd8" + b"data"
    assert _detect_image_mime(png) == "image/png"
    assert _detect_image_mime(jpeg) == "image/jpeg"
