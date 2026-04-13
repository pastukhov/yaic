"""Tests for yaic.face_recognition (InsightFace + ChromaDB mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from yaic.face_recognition import FaceRecognizer, FaceResult, _bbox_area


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_recognizer(similarity_high=0.85, similarity_low=0.60, tmp_path=None):
    """Return a FaceRecognizer with all heavy external deps mocked."""
    faces_dir = str(tmp_path) if tmp_path else "/tmp/faces"

    mock_isf = MagicMock()
    mock_isf_cls = MagicMock(return_value=mock_isf)

    mock_chroma = MagicMock()
    mock_collection = MagicMock()
    mock_chroma.get_or_create_collection.return_value = mock_collection
    mock_chroma_cls = MagicMock(return_value=mock_chroma)

    with (
        patch("yaic.face_recognition.isf_app.FaceAnalysis", mock_isf_cls),
        patch("yaic.face_recognition.chromadb.HttpClient", mock_chroma_cls),
    ):
        vlm = MagicMock()
        recognizer = FaceRecognizer(
            chroma_host="localhost",
            chroma_port=8000,
            faces_dir=faces_dir,
            similarity_high=similarity_high,
            similarity_low=similarity_low,
            vlm_client=vlm,
        )

    # Expose mocks for assertions in tests
    recognizer._mock_isf = mock_isf
    recognizer._mock_collection = mock_collection
    return recognizer


def _fake_embedding(seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    emb = rng.random(512).astype(np.float32)
    return emb / np.linalg.norm(emb)


# Context manager that stubs out cv2 + numpy at the module level
def _patch_image_decode(img_return=MagicMock(), frombuffer_return=MagicMock()):
    return (
        patch("yaic.face_recognition.cv2.imdecode", return_value=img_return),
        patch("yaic.face_recognition.np.frombuffer", return_value=frombuffer_return),
    )


# ---------------------------------------------------------------------------
# _bbox_area
# ---------------------------------------------------------------------------

def test_bbox_area_basic():
    assert _bbox_area([0, 0, 10, 20]) == 200.0


def test_bbox_area_zero():
    assert _bbox_area([5, 5, 5, 5]) == 0.0


# ---------------------------------------------------------------------------
# recognize — no face detected
# ---------------------------------------------------------------------------

def test_recognize_no_face(tmp_path):
    rec = _make_recognizer(tmp_path=tmp_path)

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = []
        result = rec.recognize(b"\xff\xd8\xff\xe0fake")

    assert result == FaceResult(identity=None, identity_confidence=None, identity_stage="no_face")


# ---------------------------------------------------------------------------
# recognize — high similarity → embedding confirmed
# ---------------------------------------------------------------------------

def test_recognize_high_similarity(tmp_path):
    rec = _make_recognizer(similarity_high=0.85, similarity_low=0.60, tmp_path=tmp_path)

    emb = _fake_embedding(1)
    face_mock = MagicMock()
    face_mock.embedding = emb
    face_mock.bbox = [0, 0, 100, 100]

    # ChromaDB returns distance = 0.08 → similarity = 0.92 (above HIGH threshold)
    rec._mock_collection.query.return_value = {
        "ids": [["artem_0"]],
        "distances": [[0.08]],
        "metadatas": [[{"name": "artem", "photo_path": "/faces/artem/photo1.jpg"}]],
    }

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = [face_mock]
        result = rec.recognize(b"\xff\xd8\xff\xe0fake")

    assert result.identity == "artem"
    assert result.identity_stage == "embedding"
    assert result.identity_confidence == pytest.approx(0.92, abs=1e-3)


# ---------------------------------------------------------------------------
# recognize — low similarity → unknown (no LLM)
# ---------------------------------------------------------------------------

def test_recognize_low_similarity(tmp_path):
    rec = _make_recognizer(similarity_high=0.85, similarity_low=0.60, tmp_path=tmp_path)

    emb = _fake_embedding(2)
    face_mock = MagicMock()
    face_mock.embedding = emb
    face_mock.bbox = [0, 0, 50, 50]

    # distance = 0.60 → similarity = 0.40 (below LOW threshold)
    rec._mock_collection.query.return_value = {
        "ids": [["artem_0"]],
        "distances": [[0.60]],
        "metadatas": [[{"name": "artem", "photo_path": "/faces/artem/photo1.jpg"}]],
    }

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = [face_mock]
        result = rec.recognize(b"\xff\xd8\xff\xe0fake")

    assert result.identity is None
    assert result.identity_stage == "embedding"
    rec._vlm.verify_same_person.assert_not_called()


# ---------------------------------------------------------------------------
# recognize — grey zone → LLM confirms identity
# ---------------------------------------------------------------------------

def test_recognize_llm_confirmed(tmp_path):
    rec = _make_recognizer(similarity_high=0.85, similarity_low=0.60, tmp_path=tmp_path)

    emb = _fake_embedding(3)
    face_mock = MagicMock()
    face_mock.embedding = emb
    face_mock.bbox = [0, 0, 80, 80]

    # distance = 0.20 → similarity = 0.80 (in grey zone [0.60, 0.85))
    ref_photo = tmp_path / "anna" / "p.jpg"
    ref_photo.parent.mkdir(parents=True)
    ref_photo.write_bytes(b"\xff\xd8\xff\xe0ref")

    rec._mock_collection.query.return_value = {
        "ids": [["anna_0"]],
        "distances": [[0.20]],
        "metadatas": [[{"name": "anna", "photo_path": str(ref_photo)}]],
    }
    rec._vlm.verify_same_person.return_value = {"same_person": True, "confidence": 0.93}

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = [face_mock]
        result = rec.recognize(b"\xff\xd8\xff\xe0query")

    assert result.identity == "anna"
    assert result.identity_stage == "llm"
    assert result.identity_confidence == pytest.approx(0.93, abs=1e-3)
    rec._vlm.verify_same_person.assert_called_once()


# ---------------------------------------------------------------------------
# recognize — grey zone → LLM rejects
# ---------------------------------------------------------------------------

def test_recognize_llm_rejected(tmp_path):
    rec = _make_recognizer(similarity_high=0.85, similarity_low=0.60, tmp_path=tmp_path)

    emb = _fake_embedding(4)
    face_mock = MagicMock()
    face_mock.embedding = emb
    face_mock.bbox = [0, 0, 60, 60]

    ref_photo = tmp_path / "anna" / "p.jpg"
    ref_photo.parent.mkdir(parents=True)
    ref_photo.write_bytes(b"\xff\xd8\xff\xe0ref")

    rec._mock_collection.query.return_value = {
        "ids": [["anna_0"]],
        "distances": [[0.25]],
        "metadatas": [[{"name": "anna", "photo_path": str(ref_photo)}]],
    }
    rec._vlm.verify_same_person.return_value = {"same_person": False, "confidence": 0.10}

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = [face_mock]
        result = rec.recognize(b"\xff\xd8\xff\xe0query")

    assert result.identity is None
    assert result.identity_stage == "llm"


# ---------------------------------------------------------------------------
# recognize — empty ChromaDB collection
# ---------------------------------------------------------------------------

def test_recognize_empty_collection(tmp_path):
    rec = _make_recognizer(tmp_path=tmp_path)

    emb = _fake_embedding(5)
    face_mock = MagicMock()
    face_mock.embedding = emb
    face_mock.bbox = [0, 0, 50, 50]

    rec._mock_collection.query.return_value = {"ids": [[]], "distances": [[]], "metadatas": [[]]}

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = [face_mock]
        result = rec.recognize(b"\xff\xd8\xff\xe0query")

    assert result.identity is None
    assert result.identity_stage == "embedding"


# ---------------------------------------------------------------------------
# reindex
# ---------------------------------------------------------------------------

def test_reindex_with_photos(tmp_path):
    faces_dir = tmp_path / "faces"
    artem = faces_dir / "artem"
    artem.mkdir(parents=True)
    (artem / "photo1.jpg").write_bytes(b"\xff\xd8\xff\xe0fake1")
    (artem / "photo2.jpg").write_bytes(b"\xff\xd8\xff\xe0fake2")

    anna = faces_dir / "anna"
    anna.mkdir()
    (anna / "photo1.jpg").write_bytes(b"\xff\xd8\xff\xe0fake3")

    rec = _make_recognizer(tmp_path=faces_dir)
    rec._faces_dir = faces_dir

    emb = _fake_embedding(1)
    face_mock = MagicMock()
    face_mock.embedding = emb
    face_mock.bbox = [0, 0, 100, 100]

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = [face_mock]
        result = rec.reindex()

    assert result["status"] == "ok"
    assert result["indexed"] == 2
    assert set(result["identities"]) == {"artem", "anna"}
    assert result["duration_seconds"] >= 0
    rec._mock_collection.upsert.assert_called_once()
    call_kwargs = rec._mock_collection.upsert.call_args
    assert len(call_kwargs.kwargs["ids"]) == 3  # 2 artem + 1 anna


def test_reindex_skips_no_face(tmp_path):
    faces_dir = tmp_path / "faces"
    person = faces_dir / "bob"
    person.mkdir(parents=True)
    (person / "photo1.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    rec = _make_recognizer(tmp_path=faces_dir)
    rec._faces_dir = faces_dir

    p1, p2 = _patch_image_decode()
    with p1, p2:
        rec._isf.get.return_value = []
        result = rec.reindex()

    assert result["indexed"] == 0
    rec._mock_collection.upsert.assert_not_called()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_populated(tmp_path):
    rec = _make_recognizer(tmp_path=tmp_path)
    rec._mock_collection.count.return_value = 3
    rec._mock_collection.get.return_value = {
        "metadatas": [
            {"name": "artem", "photo_path": "p1"},
            {"name": "artem", "photo_path": "p2"},
            {"name": "anna", "photo_path": "p3"},
        ]
    }

    result = rec.status()
    assert result["indexed"] == 2
    assert set(result["identities"]) == {"artem", "anna"}
    assert result["last_indexed"] is None


def test_status_empty(tmp_path):
    rec = _make_recognizer(tmp_path=tmp_path)
    rec._mock_collection.count.return_value = 0

    result = rec.status()
    assert result["indexed"] == 0
    assert result["identities"] == []
