# Standalone YAIC / Tuya implementation report

Date: 2026-11-08. Changes remain unstaged on the existing feature branch.
No commits, push, deployment, .env/credential edits, live device requests, live
VLM calls, service restarts or model-weight downloads were performed.
The unrelated untracked `docs/yaic_image_url_support.md` was preserved.

## Delivered

- `yaic/config.py`: `load_config(require_mqtt=False)` permits classification
  without MQTT variables; default validation preserved. HA discovery toggle.
- `yaic/runtime.py`: shared Processor construction, lazy optional faces/roles,
  original thresholds/reindex settings. Standalone commands open no face API.
- `yaic/main.py`: existing no-argument MQTT runtime; file classification command
  and read-only Tuya listener, safe stderr failures, signal handling.
- `yaic/mqtt_client.py`: discovery disabled on registration and reconnect when
  `HA_DISCOVERY_ENABLED=false`; ordinary MQTT topics/status remain enabled.
- `yaic/tuya_events.py`: pure bounded DP185/154/239/240 decoder, public allowlisted
  metadata, hashed dedup content, independent panels, finite timestamps.
- `yaic/tuya_source.py`: verified device22/LAN3.3, retry 1 / timeout 2 s/persistent,
  exact known null read query, idle handling, interruptible 1..30 s reconnect,
  close on stop/failure, consumer errors propagate instead of reconnecting.
- `yaic/snapshots.py`: streaming 10 MiB cap regardless of Content-Length, HTTP(S),
  no credentials/redirects/auth header, timeout/deadline, Pillow verify+decode,
  private URL/header log suppression and safe error messages.
- `yaic/tuya_runner.py`: event-only has no Processor/download; optional one-worker
  classification, max 8 pending jobs, reject snapshot jobs older than 5 s, bounded
  dedup 256 / 30 s, immediate Ring-after-Normal per panel, synchronized JSONL,
  snapshot-unavailable/failure events, explicit shutdown and output failure handling.
- New config/CLI/runtime/decoder/source/snapshot/runner tests and MQTT regression.
  README and `docs/standalone-tuya.md` cover usage and limitations.
- `pyproject.toml` explicitly adds TinyTuya 1.20.0 and Pillow; `poetry.lock` updated.
  Parent lock audit found no existing package version changes/removals; new
  transitive crypto packages are cffi, cryptography and pycparser.

## Verification

The original `.venv/bin/python` is Python 3.14.4 and initially had neither pip nor
pytest. Installed only isolated venv packages with:

```bash
uv pip install --python .venv/bin/python pytest paho-mqtt==1.6.1 pydantic httpx requests pillow tinytuya==1.20.0 fastapi uvicorn
```

Initial TDD runs observed missing standalone config signature/CLI dispatch and
missing new modules. Corrections also observed actual failing regressions for
panel independence, NaN timestamp omission and truncated JPEG acceptance.
The original environment's full `.venv/bin/python -m pytest -q` then failed
collection in `tests/test_face_recognition.py` (missing numpy) and
`tests/test_processor_face.py` (missing chromadb). No tests were removed or
missing production dependencies globally faked.

A compatible full test environment was created locally (ignored scratch):

```bash
uv python install 3.11
uv venv --python 3.11 .superpowers/sdd/2026-11-08-standalone-tuya/venv
uv pip install --python .superpowers/sdd/2026-11-08-standalone-tuya/venv/bin/python -e . 'pytest>=7.4,<8'
.superpowers/sdd/2026-11-08-standalone-tuya/venv/bin/python -m pytest -q
```

Final complete suite: **103 passed in 0.66s**, Python 3.11.15 / pytest 7.4.4,
including existing optional-face tests with their dependency constructors mocked.
No physical E2E is implied. Earlier targeted original-interpreter run of
config/CLI/Processor/VLM/role/MQTT/discovery passed 41 tests. Parent independently
ran the complete 101-test suite successfully before the final two additional
runtime face-factory tests, plus targeted 80 tests and CLI help smoke checks.

```bash
.venv/bin/python -m yaic --help
.venv/bin/python -m compileall -q yaic
git diff --check
poetry lock
```

All succeeded. Own diff inspected for credentials: only deliberately synthetic
URLs/keys in fixtures and external-config placeholders in documentation.
Local generated `.superpowers/` directory was added to `.git/info/exclude`.

Tests exercise streaming caps with missing/false length, timeout/status/redirect
rejection, invalid/truncated images, request-log privacy, idle/reconnect/close,
read-only DP configuration, malformed decoder data, independent panel dedup,
slow inference/backpressure, event emission under load, expired queued jobs,
shutdown/drop/join, broken stdout and fake event→snapshot→existing Processor→JSONL.
The successful downloader uses a generated tiny PNG; pipeline inference is mocked.

Parent also decoded an existing private physical recording offline through the
new decoder: human_detected 1, doorbell_ring 1, doorbell_image 1, doorbell_idle 2;
public serialization contained no URL. This validates parsing of captured data,
not live listening or physical-image acquisition. No capture was copied here.

## Decisions and deviations

- Worktree creation was unavailable for this sourceRoot; used the explicitly
  authorized existing feature branch with one writer, no staging or commits.
- Added explicit Pillow dependency for actual decode/validation; it was already
  transitive in the optional face stack. Kept lock reproducible via Poetry.
- No heartbeat: only verified initial null query and passive receives. Long-idle
  liveness remains physically unvalidated; no speculative command was added.
- To avoid expired or old queued snapshots, reject jobs after 5 s before download
  instead of buffering fetched images. Slow inference can intentionally lose events.
- HTTPX timeout is per network operation; elapsed 5 s deadline is checked between
  chunks. One blocked operation may extend total duration. Hard wall-clock
  cancellation is not claimed. Encoded HTTP response bodies are rejected.
- Active inference is joined, not silently abandoned; existing VLM retries,
  timeout and optional face/role work can delay shutdown. Socket closes first.
- No extra standalone Docker compose: direct CLI is runnable without the broker
  and does not require a new service configuration.
- Parent performed independent review instead of spawning another reviewer,
  consistent with the single-writer/delegation instruction.

## Remaining physical blockers

DP185 resource URL resolution/decryption is **unknown**. No bucket-derived URL,
guessed AES key or cloud API was invented. Human-event classification needs an
explicit fresh `YAIC_SNAPSHOT_URL`; otherwise output is `snapshot_unavailable`.
DP154 is a cloud signed URL and its real image encoding remains unverified;
previously captured links have expired and were never retried. A fresh physical
snapshot and configured classifier are required for later person-event E2E.
LAN event delivery does not prove WAN independence. Phone notification delivery
is outside this implementation. This is a tested standalone code pipeline, not
completed physical end-to-end Tuya image integration.
