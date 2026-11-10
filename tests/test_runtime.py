"""Optional face setup preserves the service's thresholds and role behavior."""
from dataclasses import replace
from unittest.mock import Mock

from yaic.config import load_config
from yaic.runtime import build_processor


def test_face_factory_preserves_optional_setup(monkeypatch):
    import yaic.face_recognition as faces
    import yaic.role_classifier as roles
    monkeypatch.setenv('YAIC_LANGUAGE','en')
    config = replace(load_config(require_mqtt=False),chroma_host='synthetic-host')
    recognizer = Mock()
    factory = Mock(return_value=recognizer)
    role = Mock()
    monkeypatch.setattr(faces,'FaceRecognizer',factory)
    monkeypatch.setattr(roles,'RoleClassifier',role)
    processor = build_processor(config)
    assert processor._face_recognizer is recognizer
    recognizer.reindex.assert_called_once_with()
    assert factory.call_args.kwargs['similarity_high'] == config.face_similarity_high
    assert factory.call_args.kwargs['similarity_low'] == config.face_similarity_low
    role.assert_called_once()


def test_face_reindex_and_role_are_opt_in(monkeypatch):
    import yaic.face_recognition as faces
    import yaic.role_classifier as roles
    monkeypatch.setenv('YAIC_LANGUAGE','en')
    config = replace(load_config(require_mqtt=False),chroma_host='synthetic-host',face_index_on_startup=False,classify_stranger_role=False)
    recognizer = Mock()
    monkeypatch.setattr(faces,'FaceRecognizer',Mock(return_value=recognizer))
    role = Mock()
    monkeypatch.setattr(roles,'RoleClassifier',role)
    processor = build_processor(config)
    recognizer.reindex.assert_not_called()
    role.assert_not_called()
    assert processor._role_classifier is None
