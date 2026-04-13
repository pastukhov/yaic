from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException

if TYPE_CHECKING:
    from .face_recognition import FaceRecognizer

logger = logging.getLogger(__name__)

app = FastAPI(title="YAIC", description="YAIC face index management API")

_face_recognizer: FaceRecognizer | None = None


def set_face_recognizer(recognizer: FaceRecognizer) -> None:
    """Register the FaceRecognizer instance used by endpoint handlers."""
    global _face_recognizer
    _face_recognizer = recognizer


def start_api_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the uvicorn server in a background daemon thread."""
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_config=None)
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="yaic-api")
    thread.start()
    logger.info("YAIC HTTP API listening on %s:%s", host, port)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/faces/reindex")
async def reindex() -> dict[str, Any]:
    """Re-scan the faces directory and rebuild the ChromaDB index."""
    if _face_recognizer is None:
        raise HTTPException(status_code=503, detail="Face recognition not enabled")

    import asyncio

    loop = asyncio.get_event_loop()
    result: dict[str, Any] = await loop.run_in_executor(None, _face_recognizer.reindex)
    return result


@app.get("/faces/status")
async def status() -> dict[str, Any]:
    """Return the current state of the face index."""
    if _face_recognizer is None:
        raise HTTPException(status_code=503, detail="Face recognition not enabled")

    import asyncio

    loop = asyncio.get_event_loop()
    result: dict[str, Any] = await loop.run_in_executor(None, _face_recognizer.status)
    return result
