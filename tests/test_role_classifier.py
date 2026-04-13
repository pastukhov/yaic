"""Tests for yaic.role_classifier."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from yaic.role_classifier import DEFAULT_ROLES, RoleClassifier, RoleResult


def _make_classifier(language="ru", roles=None):
    vlm = MagicMock()
    return RoleClassifier(vlm_client=vlm, language=language, roles=roles), vlm


# ---------------------------------------------------------------------------
# Basic classification
# ---------------------------------------------------------------------------

def test_classify_courier():
    clf, vlm = _make_classifier()
    vlm.classify_role.return_value = {
        "role": "courier",
        "confidence": 0.91,
        "reason": "Thermal bag with Ozon logo",
    }

    result = clf.classify(b"\xff\xd8fake")

    assert result.role == "courier"
    assert result.role_confidence == pytest.approx(0.91, abs=1e-4)
    assert result.role_reason == "Thermal bag with Ozon logo"
    vlm.classify_role.assert_called_once()


def test_classify_unknown_role_falls_back_to_stranger():
    clf, vlm = _make_classifier()
    vlm.classify_role.return_value = {
        "role": "pirate",  # not in DEFAULT_ROLES
        "confidence": 0.5,
        "reason": "Arrr",
    }

    result = clf.classify(b"\xff\xd8fake")

    assert result.role == "stranger"


def test_classify_missing_role_key():
    clf, vlm = _make_classifier()
    vlm.classify_role.return_value = {"confidence": 0.5, "reason": "nothing"}

    result = clf.classify(b"\xff\xd8fake")

    assert result.role == "stranger"


def test_classify_vlm_exception_returns_stranger():
    clf, vlm = _make_classifier()
    vlm.classify_role.side_effect = RuntimeError("network error")

    result = clf.classify(b"\xff\xd8fake")

    assert result.role == "stranger"
    assert result.role_confidence == 0.0
    assert result.role_reason == ""


def test_classify_bad_confidence_type():
    clf, vlm = _make_classifier()
    vlm.classify_role.return_value = {
        "role": "neighbor",
        "confidence": "high",  # not a float
        "reason": "casual clothes",
    }

    result = clf.classify(b"\xff\xd8fake")

    assert result.role == "neighbor"
    assert result.role_confidence == 0.0


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def test_prompt_includes_all_default_roles():
    clf, _ = _make_classifier(language="en")
    prompt = clf._build_prompt()
    for role in DEFAULT_ROLES:
        assert f'"{role}"' in prompt


def test_prompt_uses_language():
    clf, _ = _make_classifier(language="de")
    prompt = clf._build_prompt()
    assert "'de'" in prompt


def test_custom_roles_used():
    custom = {"vip": "Suit and tie", "other": "Anything else"}
    clf, vlm = _make_classifier(roles=custom)
    vlm.classify_role.return_value = {"role": "vip", "confidence": 0.99, "reason": "suit"}

    result = clf.classify(b"\xff\xd8fake")

    assert result.role == "vip"
    prompt = clf._build_prompt()
    assert '"vip"' in prompt
    assert '"other"' in prompt
    # Default roles must NOT appear
    assert '"courier"' not in prompt


# ---------------------------------------------------------------------------
# RoleResult dataclass
# ---------------------------------------------------------------------------

def test_role_result_fields():
    r = RoleResult(role="postman", role_confidence=0.75, role_reason="postal uniform")
    assert r.role == "postman"
    assert r.role_confidence == 0.75
    assert r.role_reason == "postal uniform"
