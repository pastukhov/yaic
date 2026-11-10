"""Shared classifier construction; optional face imports stay lazy."""
import logging

from .config import Config
from .processor import Processor
from .vlm_client import VlmClient


def build_processor(config: Config) -> Processor:
    vlm = VlmClient(
        api_key=config.vlm_api_key,
        endpoint=config.vlm_endpoint,
        language=config.yaic_language,
        model=config.vlm_model,
        timeout=config.inference_timeout,
        temperature=config.inference_temperature,
    )

    face_recognizer = None
    role_classifier = None

    if config.chroma_host:
        from .face_recognition import FaceRecognizer
        from .role_classifier import RoleClassifier

        face_recognizer = FaceRecognizer(
            chroma_host=config.chroma_host,
            chroma_port=config.chroma_port,
            faces_dir=config.faces_dir,
            similarity_high=config.face_similarity_high,
            similarity_low=config.face_similarity_low,
            vlm_client=vlm,
        )
        if config.face_index_on_startup:
            logging.getLogger(__name__).info("Building face index on startup")
            face_recognizer.reindex()

        if config.classify_stranger_role:
            role_classifier = RoleClassifier(vlm, config.yaic_language)

    return Processor(
        vlm,
        face_recognizer=face_recognizer,
        role_classifier=role_classifier,
    )
