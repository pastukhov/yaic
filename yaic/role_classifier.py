from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .vlm_client import VlmClient

logger = logging.getLogger(__name__)

DEFAULT_ROLES: dict[str, str] = {
    "courier": (
        "Thermal delivery bag, logos of delivery services "
        "(Yandex, CDEK, Ozon, Wildberries, DHL, etc.), boxes or parcels"
    ),
    "postman": "Postal service uniform, letter bag or envelope bundle",
    "technician": (
        "Workwear, tools, hard hat, high-visibility vest, utility belt"
    ),
    "neighbor": "Casual everyday clothing, no specific work-related attributes",
    "stranger": "Does not clearly fit any of the above categories",
}


@dataclass
class RoleResult:
    role: str
    role_confidence: float
    role_reason: str


class RoleClassifier:
    """Classify the role of an unrecognised visitor using a single VLM call."""

    def __init__(
        self,
        vlm_client: VlmClient,
        language: str,
        roles: dict[str, str] | None = None,
    ) -> None:
        self._vlm = vlm_client
        self._language = language
        self._roles = roles if roles is not None else DEFAULT_ROLES

    def classify(self, image_bytes: bytes) -> RoleResult:
        prompt = self._build_prompt()
        try:
            raw = self._vlm.classify_role(image_bytes, prompt)
        except Exception:
            logger.warning("Role classification VLM call failed", exc_info=True)
            return RoleResult(role="stranger", role_confidence=0.0, role_reason="")

        role = str(raw.get("role", "stranger")).strip() or "stranger"
        if role not in self._roles:
            role = "stranger"

        try:
            confidence = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        reason = str(raw.get("reason", "")).strip()
        logger.debug("Role classified: role=%s confidence=%.3f", role, confidence)
        return RoleResult(role=role, role_confidence=round(confidence, 4), role_reason=reason)

    def _build_prompt(self) -> str:
        roles_block = "\n".join(
            f'  "{role}" — {desc}' for role, desc in self._roles.items()
        )
        valid_roles = ", ".join(f'"{r}"' for r in self._roles)
        example_role = next(iter(self._roles))
        return (
            "You are analysing a frame from a video intercom camera.\n"
            "Classify the visitor's role based on their clothing, accessories, and visible attributes.\n\n"
            f"Available roles:\n{roles_block}\n\n"
            "Return ONLY valid JSON. No markdown, no extra text.\n"
            f'role must be exactly one of: {valid_roles}.\n'
            "confidence is a number from 0.0 to 1.0.\n"
            f'reason is a short explanation in language \'{self._language}\'.\n'
            f'JSON shape: {{"role": "{example_role}", "confidence": 0.9, "reason": "short reason"}}'
        )
