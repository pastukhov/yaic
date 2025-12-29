from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

from .qwen_client import QwenClient, PersonDetail

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingResult:
    payload: dict[str, Any]
    image_bytes: bytes
    people: tuple[PersonDetail, ...]


class Processor:
    def __init__(self, qwen_client: QwenClient) -> None:
        self._qwen = qwen_client

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

        image_b64 = data.get("image_b64")
        if not image_b64:
            raise ValueError("JSON payload missing image_b64")

        try:
            image_bytes = base64.b64decode(image_b64, validate=True)
        except (ValueError, TypeError):
            raise ValueError("image_b64 is not valid base64")

        device = data.get("device")
        return image_bytes, device
