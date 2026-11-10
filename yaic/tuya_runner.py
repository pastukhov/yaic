"""JSONL event ingestion with bounded deduplication and one classification worker."""
from __future__ import annotations

import json
import logging
import queue
import sys
import threading
import time
from collections import OrderedDict
from .snapshots import fetch_snapshot

logger = logging.getLogger(__name__)


class TuyaRunner:
    def __init__(self, source, *, processor=None, snapshot_url=None, output=None,
                 fetch=fetch_snapshot, clock=time.monotonic, metrics=None):
        from .metrics import metrics as default_metrics
        self.metrics = metrics if metrics is not None else default_metrics
        self.source = source
        self.processor = processor
        self.snapshot_url = snapshot_url
        self.output = output if output is not None else sys.stdout
        self.fetch = fetch
        self.clock = clock
        self._lock = threading.Lock()
        self._seen = OrderedDict()
        self._ring_state = {}
        self._jobs = queue.Queue(maxsize=8)
        self._failure = None
        self._stop_event = None

    def emit(self, payload):
        try:
            with self._lock:
                self.output.write(json.dumps(payload, separators=(',', ':')) + '\n')
                self.output.flush()
        except Exception as exc:
            self._failure = exc
            if self._stop_event is not None:
                self._stop_event.set()
            raise

    def _receive(self, event):
        now = self.clock()
        while self._seen and next(iter(self._seen.values())) <= now - 30:
            self._seen.popitem(last=False)
        key = (event.source_id, event.kind, event.dedup_key)
        panel_key = (event.source_id, event.panel)
        ring_change = (event.kind in ('doorbell_ring', 'doorbell_idle')
                       and self._ring_state.get(panel_key) != event.kind)
        if key in self._seen and not ring_change:
            return
        if event.kind in ('doorbell_ring', 'doorbell_idle'):
            # Only the latest ring state matters; bound this map with the dedup cache.
            self._ring_state[panel_key] = event.kind
            if len(self._ring_state) > 256:
                del self._ring_state[next(iter(self._ring_state))]
        self._seen.pop(key, None)
        self._seen[key] = now
        if len(self._seen) > 256:
            self._seen.popitem(last=False)
        self.metrics.events.labels(event.kind if event.kind in ("human_detected", "doorbell_image", "doorbell_ring", "doorbell_idle", "doorbell_press", "sd_card_flag", "movement_image_available") else "other").inc()
        self.emit(event.to_payload())
        if self.processor is None or event.kind not in ('human_detected', 'doorbell_image'):
            return
        url = event.snapshot_url if event.kind == 'doorbell_image' else self.snapshot_url
        if not url:
            self._unavailable(event, 'no_snapshot_source')
            return
        try:
            self._jobs.put_nowait((event, url, now))
            self.metrics.queue.set(self._jobs.qsize())
        except queue.Full:
            self._unavailable(event, 'queue_full')
            logger.warning('Snapshot classification queue full; dropped new job')

    def _unavailable(self, event, reason):
        self.metrics.drops.labels(reason).inc()
        self.emit({'event_type':'snapshot_unavailable', 'source':event.source_id,
                   'reason':reason, 'trigger':event.to_payload()})

    def _worker(self):
        while True:
            job = self._jobs.get()
            self.metrics.queue.set(self._jobs.qsize())
            try:
                if job is None:
                    return
                if self._failure is not None:
                    continue
                event, url, queued_at = job
                if self._stop_event.is_set():
                    self._unavailable(event, 'shutdown')
                    continue
                # Signed links may expire within 60s; never fetch queued old frames.
                if self.clock() - queued_at > 5:
                    self._unavailable(event, 'snapshot_job_expired')
                    continue
                try:
                    with self.metrics.stage("snapshot_fetch"):
                        image = self.fetch(url)
                except Exception:
                    self._unavailable(event, 'download_failed')
                    continue
                try:
                    result = self.processor.process_message(image, event.source_id)
                    self.emit({'event_type':'classified', **result.payload, 'trigger':event.to_payload()})
                except Exception:
                    self.emit({'event_type':'classification_failed', 'source':event.source_id,
                               'trigger':event.to_payload()})
            except Exception as exc:
                self._failure = exc
                self._stop_event.set()
            finally:
                self._jobs.task_done()

    def run(self, stop_event):
        self._stop_event = stop_event
        worker = None
        if self.processor is not None:
            worker = threading.Thread(target=self._worker, name='yaic-classifier')
            worker.start()
        try:
            self.source.run(self._receive, stop_event)
        finally:
            if worker is not None:
                logger.info('Waiting for classification worker; active inference uses configured timeout/retries')
                # Drop queued work at shutdown; never download stale snapshots after stop.
                if stop_event.is_set():
                    while True:
                        try:
                            job = self._jobs.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            if self._failure is None:
                                self._unavailable(job[0], 'shutdown')
                        except Exception:
                            pass  # emit recorded failure; still stop and join the worker
                        finally:
                            self._jobs.task_done()
                self._jobs.put(None)
                worker.join()
                self.metrics.queue.set(self._jobs.qsize())
        if self._failure is not None:
            raise self._failure
