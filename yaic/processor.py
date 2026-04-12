from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from pydantic import BaseModel, model_validator

from .vlm_client import VlmClient, PersonDetail

logger = logging.getLogger(__name__)


class ImageMessage(BaseModel):
    device: Optional[str] = None
    image_b64: Optional[str] = None
    image_url: Optional[str] = None

    @model_validator(mode="after")
    def check_image_source(self) -> "ImageMessage":
        if not self.image_b64 and not self.image_url:
            raise ValueError("Payload must contain 'image_b64' or 'image_url'")
        return self


def get_http_headers_for_url(url: str, ha_token: str) -> dict:
    if ha_token and (":8123" in url or "homeassistant" in url):
        return {"Authorization": f"Bearer {ha_token}"}
    return {}


def fetch_image_bytes(msg: ImageMessage, ha_token: str = "", timeout: float = 5.0) -> bytes:
    if msg.image_b64:
        return base64.b64decode(msg.image_b64)

    headers = get_http_headers_for_url(msg.image_url, ha_token)
    try:
        with httpx.Client() as client:
            response = client.get(
                msg.image_url,
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.content
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch image from {msg.image_url!r}: {exc}") from exc


@dataclass(frozen=True)
class ProcessingResult:
    payload: dict[str, Any]
    image_bytes: bytes
    people: tuple[PersonDetail, ...]


class Processor:
    def __init__(self, vlm_client: VlmClient, ha_token: str = "") -> None:
        self._qwen = vlm_client
        self._ha_token = ha_token

    def process_message(self, payload: bytes, source_id: str) -> ProcessingResult:
        image_bytes, device = self._extract_image(payload)
        result = self._qwen.classify_image(image_bytes)

        output = result.to_payload()
        output["source"] = source_id
        if device:
            output["device"] = device
        return ProcessingResult(payload=output, image_bytes=image_bytes, people=result.person.details)

    def _extract_image(self, payload: bytes) -> tuple[bytes, str | None]:
        if not payload:
            raise ValueError("Empty payload")

        try:
            decoded = payload.decode("utf-8")
            data = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return payload, None

        if not isinstance(data, dict):
            raise ValueError("JSON payload must be an object")

        msg = ImageMessage(**data)
        image_bytes = fetch_image_bytes(msg, self._ha_token)
        return image_bytes, msg.device
