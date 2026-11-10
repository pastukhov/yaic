"""Bounded, unauthenticated image downloads with private URLs kept out of logs."""
from __future__ import annotations

import io
import logging
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx
from PIL import Image


class SnapshotError(RuntimeError):
    pass


@contextmanager
def _private_request_logs():
    thread_id = threading.get_ident()

    class PrivateFilter(logging.Filter):
        def filter(self, record):
            return not (record.thread == thread_id and record.name.split('.')[0] in ('httpx', 'httpcore'))

    guard = PrivateFilter()
    # httpx emits the complete signed URL at INFO; httpcore DEBUG may include headers.
    targets = [logging.getLogger('httpx')]
    targets.extend(logging.getLogger().handlers)
    for value in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(value, logging.Logger):
            targets.extend(value.handlers)
            if value.name.startswith('httpcore'):
                targets.append(value)
    targets = list(set(targets))
    for target in targets:
        target.addFilter(guard)
    try:
        yield
    finally:
        for target in targets:
            target.removeFilter(guard)


def fetch_snapshot(url: str, *, timeout: float = 5.0, max_bytes: int = 10485760) -> bytes:
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            raise ValueError('Invalid snapshot URL')
        deadline = time.monotonic() + timeout
        with _private_request_logs(), httpx.Client(follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', url, timeout=timeout) as response:
                if response.status_code != 200:
                    raise ValueError('Snapshot request unsuccessful')
                if response.headers.get('content-encoding', 'identity') != 'identity':
                    raise ValueError('Encoded snapshot response unsupported')
                length = response.headers.get('content-length')
                if length is not None and int(length) > max_bytes:
                    raise ValueError('Snapshot too large')
                data = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise ValueError("Snapshot deadline exceeded")
                    if len(data) + len(chunk) > max_bytes:
                        raise ValueError('Snapshot too large')
                    data.extend(chunk)
        image_bytes = bytes(data)
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.width * image.height > 40000000:
                raise ValueError('Snapshot dimensions too large')
            image.verify()
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
        return image_bytes
    except Exception:
        # Do not chain transport exceptions containing presigned URLs or headers.
        raise SnapshotError('Snapshot download or image validation failed') from None
