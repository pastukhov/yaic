from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

UNKNOWN = "unknown"

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/auto"


@dataclass(frozen=True)
class PersonDetail:
    age_group: str
    gender: str
    appearance: str
    role: str

    def to_payload(self) -> dict[str, str]:
        return {
            "age_group": self.age_group,
            "gender": self.gender,
            "appearance": self.appearance,
            "role": self.role,
        }


@dataclass(frozen=True)
class PersonSummary:
    count: int
    description: str | None
    details: tuple[PersonDetail, ...]
    age_summary: str | None
    gender_summary: str | None
    role_summary: str | None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"count": self.count}
        if self.count <= 0:
            return payload

        payload["description"] = self.description or UNKNOWN
        payload["details"] = [detail.to_payload() for detail in self.details]
        payload["age_summary"] = self.age_summary or UNKNOWN
        payload["gender_summary"] = self.gender_summary or UNKNOWN
        payload["role_summary"] = self.role_summary or UNKNOWN
        return payload


@dataclass(frozen=True)
class ClassificationResult:
    label: str
    confidence: float
    person: PersonSummary

    def to_payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "person": self.person.to_payload(),
        }


class VlmClient:
    def __init__(
        self,
        api_key: str,
        endpoint: str = OPENROUTER_ENDPOINT,
        language: str = "en",
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._language = language
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._max_retries = max_retries

    def classify_image(self, image_bytes: bytes) -> ClassificationResult:
        if not image_bytes:
            raise ValueError("image_bytes is empty")

        data = self._post_image(image_bytes, prompt=None)
        result = self._parse_result(data)

        if result.label == "person" and not _has_person_details(data):
            detail_prompt = self._detail_prompt()
            detail_data = self._post_image(image_bytes, prompt=detail_prompt)
            result = self._parse_result(detail_data, fallback=result)

        return result

    def _post_image(self, image_bytes: bytes, prompt: str | None) -> dict[str, Any]:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt_text = prompt or self._default_prompt()
        image_url = _image_data_url(image_bytes, image_b64)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "YAIC",
        }

        response_format = {"type": "json_object"}
        backoff = 1.0
        for attempt in range(1, self._max_retries + 1):
            try:
                payload: dict[str, Any] = {
                    "model": self._model,
                    "temperature": self._temperature,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_url},
                                },
                                {"type": "text", "text": prompt_text},
                            ],
                        }
                    ],
                }
                payload["response_format"] = response_format
                _log_debug_request(self._endpoint, headers, payload)
                response = requests.post(
                    self._endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                if response.status_code == 400 and response_format:
                    logger.info("VLM API rejected response_format; retrying without it")
                    payload = {
                        "model": self._model,
                        "temperature": self._temperature,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_url},
                                    },
                                    {"type": "text", "text": prompt_text},
                                ],
                            }
                        ],
                    }
                    _log_debug_request(self._endpoint, headers, payload)
                    response = requests.post(
                        self._endpoint,
                        json=payload,
                        headers=headers,
                        timeout=self._timeout,
                    )
                _log_debug_response(response)
                response.raise_for_status()
                try:
                    response_data = response.json()
                except ValueError:
                    logger.exception("VLM API response is not valid JSON")
                    raise
                return self._extract_content_json(response_data)
            except requests.HTTPError:
                logger.info(
                    "VLM API HTTP error (status=%s)",
                    response.status_code if "response" in locals() else "unknown",
                )
                raise
            except requests.RequestException:
                logger.info("VLM API request failed (attempt %s)", attempt)
                if attempt == self._max_retries:
                    logger.exception("VLM API request failed")
                    raise
                logger.warning("VLM API request failed, retrying (attempt %s)", attempt)
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError("VLM API retry loop exhausted")

    def _parse_result(
        self, data: dict[str, Any], fallback: ClassificationResult | None = None
    ) -> ClassificationResult:
        if not isinstance(data, dict):
            raise ValueError("VLM API response must be a JSON object")

        label = _coerce_str(data.get("label")) or (fallback.label if fallback else UNKNOWN)
        confidence = _coerce_float(data.get("confidence"))
        if confidence is None:
            confidence = fallback.confidence if fallback else 0.0

        person = self._normalize_person(data.get("person"), label)
        if fallback and person.count <= 0:
            person = fallback.person

        return ClassificationResult(label=label, confidence=confidence, person=person)

    def _normalize_person(self, person_data: Any, label: str) -> PersonSummary:
        if isinstance(person_data, dict):
            count = _coerce_int(person_data.get("count")) or 0
            description = _coerce_str(person_data.get("description"))
            details = _parse_details(person_data.get("details"))
            age_summary = _coerce_str(person_data.get("age_summary"))
            gender_summary = _coerce_str(person_data.get("gender_summary"))
            role_summary = _coerce_str(person_data.get("role_summary"))
        else:
            count = 0
            description = None
            details = ()
            age_summary = None
            gender_summary = None
            role_summary = None

        if count <= 0 and label == "person":
            count = 1

        if count <= 0:
            return PersonSummary(
                count=0,
                description=None,
                details=(),
                age_summary=None,
                gender_summary=None,
                role_summary=None,
            )

        if not details:
            details = tuple(PersonDetail(UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN) for _ in range(count))

        age_summary = age_summary or _summary_from_details(details, "age_group")
        gender_summary = gender_summary or _summary_from_details(details, "gender")
        role_summary = role_summary or _summary_roles(details)

        return PersonSummary(
            count=count,
            description=description or UNKNOWN,
            details=details,
            age_summary=age_summary,
            gender_summary=gender_summary,
            role_summary=role_summary,
        )

    def _detail_prompt(self) -> str:
        return (
            "Analyze all people visible in the image.\n"
            "Return ONLY valid JSON. No markdown, no extra text.\n"
            "label must be exactly \"person\".\n"
            "confidence must be a number from 0.0 to 1.0.\n"
            "Count ALL visible people and set person.count accordingly.\n"
            "details must contain one entry PER person.\n"
            "If no person is visible, set person to {\"count\":0}.\n"
            "JSON shape:\n"
            '{"label":"person","confidence":0.0,"person":{"count":2,"description":"text","details":[{"age_group":"adult","gender":"male","appearance":"text","role":"unknown"},{"age_group":"adult","gender":"female","appearance":"text","role":"unknown"}],"age_summary":"text","gender_summary":"text","role_summary":"text"}}\n'
            f"Use language '{self._language}' for text values."
        )

    def _default_prompt(self) -> str:
        return (
            "You are analyzing a frame from a video intercom or entrance camera.\n"
            "Classify what is visible in the image using exactly one of these labels:\n"
            "  person  — one or more people are visible\n"
            "  animal  — an animal is visible, no people\n"
            "  package — a parcel or bag left unattended, no people\n"
            "  empty   — the scene is clear: corridor/entrance with no person, animal, or package\n"
            "  unknown — the image is too dark, blurry, or otherwise unreadable\n"
            "Return ONLY valid JSON. No markdown, no extra text.\n"
            "Set label to exactly one of the five values above.\n"
            "confidence must be a number from 0.0 to 1.0.\n"
            "If label is person: count ALL visible people, person.count >= 1, one details entry per person.\n"
            "If label is not person: person must be {\"count\":0}.\n"
            "JSON shape:\n"
            '{"label":"person","confidence":0.0,"person":{"count":0,"description":"text","details":[{"age_group":"unknown","gender":"unknown","appearance":"text","role":"unknown"}],"age_summary":"text","gender_summary":"text","role_summary":"text"}}\n'
            f"Use language '{self._language}' for text values."
        )

    def verify_same_person(self, ref_bytes: bytes, query_bytes: bytes, name: str) -> dict[str, Any]:
        """Send two images to the VLM and ask whether they show the same person.

        Returns a dict with keys ``same_person`` (bool) and ``confidence`` (float).
        Raises on network or HTTP errors.
        """
        ref_b64 = base64.b64encode(ref_bytes).decode("ascii")
        query_b64 = base64.b64encode(query_bytes).decode("ascii")
        ref_url = _image_data_url(ref_bytes, ref_b64)
        query_url = _image_data_url(query_bytes, query_b64)

        prompt = (
            f'The first photo shows {name}. '
            "Is the second photo the same person? "
            'Return ONLY valid JSON: {"same_person": true/false, "confidence": 0.0}'
        )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "YAIC",
        }

        response_format = {"type": "json_object"}
        backoff = 1.0
        for attempt in range(1, self._max_retries + 1):
            try:
                payload: dict[str, Any] = {
                    "model": self._model,
                    "temperature": self._temperature,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": ref_url}},
                                {"type": "image_url", "image_url": {"url": query_url}},
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    "response_format": response_format,
                }
                _log_debug_request(self._endpoint, headers, payload)
                response = requests.post(
                    self._endpoint, json=payload, headers=headers, timeout=self._timeout
                )
                if response.status_code == 400:
                    payload.pop("response_format", None)
                    response = requests.post(
                        self._endpoint, json=payload, headers=headers, timeout=self._timeout
                    )
                _log_debug_response(response)
                response.raise_for_status()
                return self._extract_content_json(response.json())
            except requests.HTTPError:
                raise
            except requests.RequestException:
                if attempt == self._max_retries:
                    raise
                logger.warning("verify_same_person request failed, retrying (attempt %s)", attempt)
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError("verify_same_person retry loop exhausted")

    def classify_role(self, image_bytes: bytes, prompt: str) -> dict[str, Any]:
        """Classify the role of a visitor in *image_bytes* using a custom prompt.

        Returns the raw parsed JSON dict from the VLM response.
        """
        return self._post_image(image_bytes, prompt=prompt)

    def _extract_content_json(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, TypeError, IndexError) as exc:
            logger.exception("VLM API response missing expected content")
            raise ValueError("VLM API response missing expected content") from exc

        if isinstance(content, list):
            try:
                text = content[0]["text"]
            except (TypeError, KeyError, IndexError) as exc:
                logger.exception("VLM API response missing expected content")
                raise ValueError("VLM API response missing expected content") from exc
        elif isinstance(content, str):
            text = content
        else:
            logger.exception("VLM API response missing expected content")
            raise ValueError("VLM API response missing expected content")

        text = _strip_think_block(text)
        text = _strip_json_fence(text)
        text = _extract_json_object(text)
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            logger.exception("VLM API response content is not valid JSON")
            return _recover_json_payload(text)


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_details(raw_details: Any) -> tuple[PersonDetail, ...]:
    if not isinstance(raw_details, list):
        return ()

    details: list[PersonDetail] = []
    for item in raw_details:
        if not isinstance(item, dict):
            continue
        details.append(
            PersonDetail(
                age_group=_coerce_str(item.get("age_group")) or UNKNOWN,
                gender=_coerce_str(item.get("gender")) or UNKNOWN,
                appearance=_coerce_str(item.get("appearance")) or UNKNOWN,
                role=_coerce_str(item.get("role")) or UNKNOWN,
            )
        )
    return tuple(details)


def _summary_from_details(details: tuple[PersonDetail, ...], field: str) -> str:
    values = [getattr(detail, field) for detail in details if getattr(detail, field) != UNKNOWN]
    if not values:
        return UNKNOWN

    counts = Counter(values)
    parts = []
    for value, count in counts.items():
        label = value.replace("_", " ")
        suffix = "s" if count != 1 else ""
        parts.append(f"{count} {label}{suffix}")
    return ", ".join(parts)


def _summary_roles(details: tuple[PersonDetail, ...]) -> str:
    roles: list[str] = []
    for detail in details:
        role = detail.role
        if role not in roles:
            roles.append(role)
    if not roles:
        return UNKNOWN
    return ", ".join(roles)


def _has_person_details(data: dict[str, Any]) -> bool:
    person = data.get("person")
    if not isinstance(person, dict):
        return False
    if person.get("details"):
        return True
    for key in ("description", "age_summary", "gender_summary", "role_summary"):
        if person.get(key):
            return True
    return False


def _image_data_url(image_bytes: bytes, image_b64: str) -> str:
    mime = _detect_image_mime(image_bytes)
    return f"data:{mime};base64,{image_b64}"


def _detect_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    return "image/jpeg"


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) <= 2:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _strip_think_block(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json_object(text: str) -> str:
    trimmed = text.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        return trimmed
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return trimmed
    return trimmed[start : end + 1]


def _recover_json_payload(text: str) -> dict[str, Any]:
    lowered = text.lower()
    label = UNKNOWN
    for candidate in ("person", "animal", "package", "empty", UNKNOWN):
        if f'"label":"{candidate}"' in lowered or f'"label": "{candidate}"' in lowered:
            label = candidate
            break

    confidence = 0.0
    confidence_match = re.search(r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)', text)
    if confidence_match:
        try:
            confidence = float(confidence_match.group(1))
        except ValueError:
            confidence = 0.0

    person_count = 0
    count_match = re.search(r'"count"\s*:\s*(\d+)', text)
    if count_match:
        try:
            person_count = int(count_match.group(1))
        except ValueError:
            person_count = 0
    elif label == "person":
        person_count = 1

    payload: dict[str, Any] = {
        "label": label,
        "confidence": confidence,
        "person": {"count": person_count},
    }

    description_match = re.search(r'"description"\s*:\s*"([^"]+)"', text)
    if description_match and person_count > 0:
        payload["person"]["description"] = description_match.group(1)
    return payload


def _log_debug_request(endpoint: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    safe_headers = dict(headers)
    safe_headers["Authorization"] = f"Bearer {_mask_api_key(safe_headers.get('Authorization', ''))}"
    safe_payload = _sanitize_payload(payload)
    logger.debug(
        "VLM request endpoint=%s headers=%s payload=%s",
        endpoint,
        safe_headers,
        json.dumps(safe_payload, ensure_ascii=True),
    )


def _log_debug_response(response: requests.Response) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    body = response.text
    if len(body) > 2000:
        body = f"{body[:2000]}...[truncated]"
    logger.debug(
        "VLM response status=%s body=%s",
        response.status_code,
        body,
    )


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe_payload = json.loads(json.dumps(payload))
    try:
        contents = safe_payload["messages"][0]["content"]
    except (KeyError, IndexError, TypeError):
        return safe_payload
    for item in contents:
        if isinstance(item, dict) and item.get("type") == "image_url":
            item["image_url"] = {"url": "data:<omitted>"}
    return safe_payload


def _mask_api_key(value: str) -> str:
    if not value:
        return ""
    prefix = "Bearer "
    token = value[len(prefix) :] if value.startswith(prefix) else value
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}***{token[-4:]}"
