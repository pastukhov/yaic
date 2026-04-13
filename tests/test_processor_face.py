"""Tests for the face-recognition + role-classification enrichment in Processor."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from yaic.face_recognition import FaceResult
from yaic.processor import Processor
from yaic.role_classifier import RoleResult
from yaic.vlm_client import ClassificationResult, PersonDetail, PersonSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person_result(label="person", confidence=1.0, count=1):
    """Build a ClassificationResult for a single person."""
    detail = PersonDetail(age_group="adult", gender="male", appearance="casual", role="unknown")
    summary = PersonSummary(
        count=count,
        description="A person",
        details=(detail,) if count else (),
        age_summary="adult",
        gender_summary="male",
        role_summary="unknown",
    )
    return ClassificationResult(label=label, confidence=confidence, person=summary)


def _make_processor(face_result=None, role_result=None, vlm_result=None, classify_stranger_role=True):
    vlm = MagicMock()
    vlm.classify_image.return_value = vlm_result or _person_result()

    face_recognizer = None
    role_classifier = None

    if face_result is not None:
        face_recognizer = MagicMock()
        face_recognizer.recognize.return_value = face_result

    if role_result is not None and classify_stranger_role:
        role_classifier = MagicMock()
        role_classifier.classify.return_value = role_result

    processor = Processor(
        vlm_client=vlm,
        face_recognizer=face_recognizer,
        role_classifier=role_classifier,
    )
    return processor


# ---------------------------------------------------------------------------
# No face recognition (legacy mode)
# ---------------------------------------------------------------------------

def test_no_face_recognizer_output_unchanged():
    """When face_recognizer is None, output must not contain identity fields."""
    processor = Processor(vlm_client=MagicMock())
    processor._qwen.classify_image.return_value = _person_result()

    payload = json.dumps({"image_b64": "AAAA", "device": "cam"}).encode()
    result = processor.process_message(payload, "cam")

    person = result.payload.get("person", {})
    assert "identity" not in person
    assert "role" not in person


# ---------------------------------------------------------------------------
# Face known — no role classification
# ---------------------------------------------------------------------------

def test_known_face_enriches_identity():
    face = FaceResult(identity="artem", identity_confidence=0.92, identity_stage="embedding")
    processor = _make_processor(face_result=face)

    payload = json.dumps({"image_b64": "AAAA"}).encode()
    result = processor.process_message(payload, "cam")

    person = result.payload["person"]
    assert person["identity"] == "artem"
    assert person["identity_confidence"] == 0.92
    assert person["identity_stage"] == "embedding"
    assert person["role"] is None
    assert person["role_confidence"] is None
    assert person["role_reason"] is None

    # Role classifier must NOT be called when identity is known
    if processor._role_classifier:
        processor._role_classifier.classify.assert_not_called()


# ---------------------------------------------------------------------------
# Face unknown — role classification triggered
# ---------------------------------------------------------------------------

def test_unknown_face_triggers_role_classification():
    face = FaceResult(identity=None, identity_confidence=None, identity_stage="embedding")
    role = RoleResult(role="courier", role_confidence=0.91, role_reason="Ozon thermal bag")
    processor = _make_processor(face_result=face, role_result=role)

    payload = json.dumps({"image_b64": "AAAA"}).encode()
    result = processor.process_message(payload, "cam")

    person = result.payload["person"]
    assert person["identity"] is None
    assert person["identity_stage"] == "embedding"
    assert person["role"] == "courier"
    assert person["role_confidence"] == 0.91
    assert person["role_reason"] == "Ozon thermal bag"


# ---------------------------------------------------------------------------
# No face detected (identity_stage="no_face")
# ---------------------------------------------------------------------------

def test_no_face_detected_stage():
    face = FaceResult(identity=None, identity_confidence=None, identity_stage="no_face")
    role = RoleResult(role="neighbor", role_confidence=0.7, role_reason="casual")
    processor = _make_processor(face_result=face, role_result=role)

    payload = json.dumps({"image_b64": "AAAA"}).encode()
    result = processor.process_message(payload, "cam")

    person = result.payload["person"]
    assert person["identity"] is None
    assert person["identity_stage"] == "no_face"
    assert person["role"] == "neighbor"


# ---------------------------------------------------------------------------
# Non-person label — face recognition not called
# ---------------------------------------------------------------------------

def test_non_person_label_skips_face_recognition():
    empty_result = ClassificationResult(
        label="empty",
        confidence=0.99,
        person=PersonSummary(count=0, description=None, details=(), age_summary=None,
                             gender_summary=None, role_summary=None),
    )
    face_recognizer = MagicMock()

    vlm = MagicMock()
    vlm.classify_image.return_value = empty_result

    processor = Processor(vlm_client=vlm, face_recognizer=face_recognizer)

    payload = json.dumps({"image_b64": "AAAA"}).encode()
    processor.process_message(payload, "cam")

    face_recognizer.recognize.assert_not_called()


# ---------------------------------------------------------------------------
# LLM stage identity
# ---------------------------------------------------------------------------

def test_llm_stage_identity():
    face = FaceResult(identity="anna", identity_confidence=0.88, identity_stage="llm")
    processor = _make_processor(face_result=face)

    payload = json.dumps({"image_b64": "AAAA"}).encode()
    result = processor.process_message(payload, "cam")

    person = result.payload["person"]
    assert person["identity"] == "anna"
    assert person["identity_stage"] == "llm"
    assert person["role"] is None


# ---------------------------------------------------------------------------
# Source / device pass-through
# ---------------------------------------------------------------------------

def test_source_and_device_in_output():
    face = FaceResult(identity=None, identity_confidence=None, identity_stage="embedding")
    processor = _make_processor(face_result=face)

    payload = json.dumps({"image_b64": "AAAA", "device": "domofon"}).encode()
    result = processor.process_message(payload, "domofon")

    assert result.payload["source"] == "domofon"
    assert result.payload["device"] == "domofon"
