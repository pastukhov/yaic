from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chromadb
import cv2
import insightface.app as isf_app
import numpy as np

if TYPE_CHECKING:
    from .vlm_client import VlmClient

logger = logging.getLogger(__name__)

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png"}


@dataclass
class FaceResult:
    identity: str | None
    identity_confidence: float | None
    identity_stage: str  # "no_face" | "embedding" | "llm"


class FaceRecognizer:
    """Recognise known people using local InsightFace embeddings + ChromaDB.

    Pipeline:
      1. Detect faces in the image (InsightFace, CPU only).
      2. Compute an ArcFace embedding for the largest detected face.
      3. Query ChromaDB for the nearest neighbour (cosine distance).
      4. Apply thresholds:
         - distance < (1 - HIGH)  → confirmed (stage="embedding")
         - distance in [1-HIGH, 1-LOW] → LLM verification (stage="llm")
         - distance >= (1 - LOW)  → unknown  (stage="embedding")
    """

    _COLLECTION = "faces"

    def __init__(
        self,
        chroma_host: str,
        chroma_port: int,
        faces_dir: str,
        similarity_high: float,
        similarity_low: float,
        vlm_client: VlmClient,
    ) -> None:
        self._similarity_high = similarity_high
        self._similarity_low = similarity_low
        self._vlm = vlm_client
        self._faces_dir = Path(faces_dir)
        self._lock = threading.Lock()
        self._last_indexed: datetime | None = None

        # InsightFace model (not thread-safe → guarded by _lock)
        self._isf = isf_app.FaceAnalysis(
            name="buffalo_l", providers=["CPUExecutionProvider"]
        )
        self._isf.prepare(ctx_id=-1)

        # ChromaDB persistent client
        self._chroma = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        self._collection = self._chroma.get_or_create_collection(
            self._COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "FaceRecognizer initialised chroma=%s:%s faces_dir=%s high=%.2f low=%.2f",
            chroma_host,
            chroma_port,
            faces_dir,
            similarity_high,
            similarity_low,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recognize(self, image_bytes: bytes) -> FaceResult:
        """Return the identity (or None) for the dominant face in *image_bytes*."""
        embedding = self._get_embedding(image_bytes)
        if embedding is None:
            return FaceResult(identity=None, identity_confidence=None, identity_stage="no_face")

        # Query ChromaDB for the closest stored embedding
        results = self._collection.query(
            query_embeddings=[embedding.tolist()],
            n_results=1,
            include=["distances", "metadatas"],
        )

        if not results["ids"] or not results["ids"][0]:
            # Collection is empty
            return FaceResult(identity=None, identity_confidence=None, identity_stage="embedding")

        distance: float = results["distances"][0][0]
        similarity = 1.0 - distance
        meta: dict[str, Any] = results["metadatas"][0][0]
        candidate_name: str = meta["name"]
        ref_photo_path: str = meta["photo_path"]

        logger.debug(
            "Face query candidate=%s similarity=%.3f", candidate_name, similarity
        )

        if similarity >= self._similarity_high:
            return FaceResult(
                identity=candidate_name,
                identity_confidence=round(similarity, 4),
                identity_stage="embedding",
            )

        if similarity >= self._similarity_low:
            # Gray zone — ask LLM
            same, confidence = self._llm_verify(
                candidate_name, ref_photo_path, image_bytes
            )
            if same:
                return FaceResult(
                    identity=candidate_name,
                    identity_confidence=round(confidence, 4),
                    identity_stage="llm",
                )
            return FaceResult(identity=None, identity_confidence=None, identity_stage="llm")

        # Below low threshold — unknown
        return FaceResult(identity=None, identity_confidence=None, identity_stage="embedding")

    def reindex(self) -> dict[str, Any]:
        """Rebuild the ChromaDB collection from *faces_dir*.

        Scans ``faces_dir/<name>/*.jpg`` (and .jpeg/.png), computes ArcFace
        embeddings, and upserts them into the collection.
        """
        start = time.monotonic()
        logger.info("Reindexing faces from %s", self._faces_dir)

        identities: list[str] = []
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, str]] = []

        if self._faces_dir.is_dir():
            for name_dir in sorted(self._faces_dir.iterdir()):
                if not name_dir.is_dir():
                    continue
                name = name_dir.name
                photo_count = 0
                for photo_path in sorted(name_dir.iterdir()):
                    if photo_path.suffix.lower() not in _SUPPORTED_EXTS:
                        continue
                    try:
                        img_bytes = photo_path.read_bytes()
                        emb = self._get_embedding(img_bytes)
                    except Exception:
                        logger.warning("Failed to embed %s", photo_path, exc_info=True)
                        continue
                    if emb is None:
                        logger.warning("No face detected in %s, skipping", photo_path)
                        continue
                    doc_id = f"{name}_{photo_count}"
                    ids.append(doc_id)
                    embeddings.append(emb.tolist())
                    metadatas.append({"name": name, "photo_path": str(photo_path)})
                    photo_count += 1

                if photo_count:
                    identities.append(name)
                    logger.debug("Indexed %d photo(s) for %s", photo_count, name)

        # Replace entire collection
        self._collection.delete(where={"name": {"$ne": ""}}) if ids else None
        if ids:
            self._collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

        self._last_indexed = datetime.now(tz=timezone.utc)
        duration = round(time.monotonic() - start, 2)
        logger.info(
            "Reindex complete: %d identities, %d embeddings in %.2fs",
            len(identities),
            len(ids),
            duration,
        )
        return {
            "status": "ok",
            "indexed": len(identities),
            "identities": identities,
            "duration_seconds": duration,
        }

    def status(self) -> dict[str, Any]:
        """Return the current state of the face index."""
        try:
            count = self._collection.count()
            # Fetch distinct names via metadata
            if count:
                result = self._collection.get(include=["metadatas"])
                names = sorted({m["name"] for m in result["metadatas"]})
            else:
                names = []
        except Exception:
            logger.warning("Failed to query ChromaDB status", exc_info=True)
            count = 0
            names = []

        return {
            "indexed": len(names),
            "identities": names,
            "last_indexed": self._last_indexed.isoformat() if self._last_indexed else None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_embedding(self, image_bytes: bytes) -> np.ndarray | None:
        """Detect the largest face and return its L2-normalised ArcFace embedding."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.warning("Could not decode image bytes")
            return None

        with self._lock:
            faces = self._isf.get(img)

        if not faces:
            return None

        # Pick the largest face by bounding-box area
        face = max(faces, key=lambda f: _bbox_area(f.bbox))
        emb: np.ndarray = face.embedding
        norm = np.linalg.norm(emb)
        if norm == 0:
            return emb
        return emb / norm

    def _llm_verify(
        self, name: str, ref_photo_path: str, query_bytes: bytes
    ) -> tuple[bool, float]:
        """Ask the VLM whether *query_bytes* shows the same person as *ref_photo_path*."""
        try:
            ref_bytes = Path(ref_photo_path).read_bytes()
        except OSError:
            logger.warning("Cannot read reference photo %s", ref_photo_path)
            return False, 0.0

        try:
            result = self._vlm.verify_same_person(ref_bytes, query_bytes, name)
        except Exception:
            logger.warning("LLM verification failed for %s", name, exc_info=True)
            return False, 0.0

        same = bool(result.get("same_person", False))
        confidence = float(result.get("confidence", 0.0))
        logger.debug("LLM verify name=%s same=%s confidence=%.3f", name, same, confidence)
        return same, confidence


def _bbox_area(bbox: Any) -> float:
    x1, y1, x2, y2 = bbox[:4]
    return max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))
