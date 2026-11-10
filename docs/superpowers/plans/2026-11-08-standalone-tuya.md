# Standalone YAIC and Tuya Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. User explicitly delegates implementation to Sol; no further handoff approval is needed.

**Goal:** Run YAIC classification and Tuya event processing without requiring Home Assistant or MQTT.

**Architecture:** Reuse Processor/VLM/optional face recognition through a shared factory. Preserve MQTT as the default command and add standalone file and Tuya inputs with JSONL output. Treat unverified Tuya image resolution as an explicit limitation.

**Tech Stack:** Python >=3.11, existing httpx/Pydantic, TinyTuya1.20.0, pytest.

**Spec:** docs/superpowers/specs/2026-11-08-standalone-tuya-design.md

## Global Constraints

- Python >=3.11; preserve existing MQTT/face behavior and no-argument entry point.
- Read-only Tuya known null queries; never send lock/reset/OTA or DP set commands.
- No secrets, real photos, signed URLs or private captures in code, fixtures, output or commits.
- Do not edit .env, credentials, running services or docs/yaic_image_url_support.md; no push/deploy.
- No real VLM calls in tests. Real Tuya image resolution and WAN independence remain unverified.
- Work in /home/artem/repos/yaic on existing non-main branch with a single implementation writer.
  Native worktree creation was unavailable for this sourceRoot in the current chat. Keep changes
  unstaged for review; no automatic commits or branch switches for this task.
- Invoke tests via Python -m pytest. Existing .venv/bin/python is Python3.14.4 and currently
  reports No module named pytest. Repair isolated test dependencies, never global packages;
  report pre-existing/import/environment failures separately. Do not fake missing dependencies
  globally or remove existing tests to achieve green.

## Review Focus

- No MQTT env or imports required for standalone classification and event-only listening.
- Malformed/base64/unknown Tuya data, duplicate events and non-image downloads never reach VLM.
- Reconnect/idle receive/shutdown cannot form a busy loop or an unbounded queue.
- Expired signed URLs and errors must not leak credentials or reuse stale images.
- Existing MQTT default, HA discovery default and optional face semantics remain compatible.

---

### Task 1: Standalone classification and optional HA integration

**Files:** Modify yaic/config.py, main.py, mqtt_client.py; create yaic/runtime.py;
tests/test_config.py, tests/test_main.py; extend tests/test_mqtt_client.py; README.md.

**Interfaces:** `load_config(*, require_mqtt: bool = True) -> Config`;
`build_processor(config: Config) -> Processor` in runtime.py;
`main(argv: list[str] | None = None) -> None`.
`classify --image FILE --source-id ID` prints ProcessingResult.payload as one JSON line.
Config gains `ha_discovery_enabled: bool = True`; env HA_DISCOVERY_ENABLED=false disables it.

- [ ] Add tests: standalone config without all MQTT_* succeeds; default still lists missing vars;
  no-argument entry dispatches MQTT; classify uses file bytes and source; stdout parses as one
  JSON object and diagnostic output is stderr; face initialization remains opt-in.
- [ ] Run targeted tests and observe expected failures before implementation.
- [ ] Extract existing processor construction with lazy optional face imports, retaining face
  API startup in MQTT path rather than accidentally opening an API on one-shot commands.
- [ ] Implement CLI dispatch, error exit codes and HA discovery toggle (both register/reconnect).
  Leave MQTT topic builders in place; moving them is not needed for independence.
- [ ] Run existing processor, role, VLM, MQTT/discovery and new CLI/config tests.

### Task 2: Pure Tuya event decoder and bounded LAN listener

**Files:** Create yaic/tuya_events.py, yaic/tuya_source.py, tests/test_tuya_events.py,
tests/test_tuya_source.py; modify pyproject.toml only for TinyTuya dependency.

**Interfaces:** `TuyaEvent` dataclass with kind, source_id, received_at, optional device_timestamp,
private optional snapshot_url and dedup_key. `decode_events(response: object, source_id: str)
-> list[TuyaEvent]`; `TuyaSource(device_config: dict, source_id: str).run(on_event, stop_event)`.
Event kinds: human_detected, doorbell_ring, doorbell_idle, doorbell_image. Public serialization
must omit snapshot_url/dedup raw contents/resource fields; panel number can be retained.

- [ ] Add synthetic fixtures (not copied secrets): DP185 base64 ipc_human, other cmd, broken
  base64/JSON, DP154 HTTPS URL, DP239/240 Ring/Normal, non-dict and TinyTuya error responses.
- [ ] Assert unknown values are ignored safely; v3.0 does not change LAN3.3; URLs are private.
- [ ] Implement pure decoder. No cloud resolver or guessed crypto for DP185.
- [ ] Fake transport tests verify device22, LAN3.3, retry1, timeout2, persistent socket and exact
  null-query DP list; reconnect on connection failure, stop closes device, idle timeouts avoid
  busy loop, malformed payload doesn't kill listener. Choose and document bounded backoff.
- [ ] Implement listener with injected/fakeable device factory; separate idle timeout from
  failure using installed TinyTuya behavior. Heartbeat only if supported API semantics checked;
  otherwise document long-idle liveness limit without inventing commands.
- [ ] Run decoder/listener tests and existing suite applicable to installed dependencies.

### Task 3: Snapshot acquisition and standalone event-to-classification pipeline

**Files:** Create yaic/snapshots.py, yaic/tuya_runner.py; extend main.py;
tests/test_snapshots.py, tests/test_tuya_runner.py, tests/test_main.py.

**Interfaces:** `fetch_snapshot(url: str, *, timeout: float = 5.0,
max_bytes: int = 10485760) -> bytes`; CLI `listen-tuya --device-config PATH --source-id ID
[--classify]`. YAIC_SNAPSHOT_URL is an optional URL for human snapshots. Event-only mode
does not build Processor, require language/VLM/MQTT env, or download images.

- [ ] Tests cover timeout/status/redirect policy, 10 MiB streaming cap (including no or false
  content-length), non-image response, safe exception strings and no Authorization header.
  Use an actual small synthetic encoded image for successful tests; choose existing image
  decoder if available or a lightweight dependency, not magic-byte-only acceptance.
- [ ] Implement snapshot downloader without logging URL/query; no unbounded response.content.
  Redirects may be rejected explicitly, never automatically downgrade HTTPS or carry tokens.
- [ ] Test event-only output, human with/without configured snapshot source, DP154 own URL,
  rejected/expired image never calls Processor, classification carries source and triggering
  event context. Emit snapshot_unavailable when no human image source is configured.
- [ ] Implement one bounded classification worker queue (max8), drop new jobs when full,
  event emission independent of worker progress. Dedup duplicate notification content/timestamp
  within30s, bounded256 entries; repeated event after window is eligible again. Avoid dedup
  suppressing a new Ring after Normal. Public events have no private resource data.
- [ ] Test slow worker/backpressure and thread-safe JSONL lines, repeat suppression/expiry,
  errors don't terminate ingestion; shutdown closes source and reports any in-flight deadline
  limitation inherited from VLM. No daemon that silently abandons intended output as success.
- [ ] Run fake end-to-end ipc_human→snapshot→existing Processor→classification JSONL,
  plus doorbell image path; this is mocked integration, explicitly not physical validation.

### Task 4: Documentation and verification handoff

**Files:** README.md; add docs/standalone-tuya.md; optional docker-compose.standalone.yaml
only if it provides a genuinely runnable separate configuration without changing existing stack.

- [ ] Document commands, credentials external JSON, stdout contract, optional Chroma/VLM,
  MQTT/HA switch, signed snapshot cloud dependence, unknown DP185 resource resolution,
  heartbeat/shutdown limitations and steps for later physical validation.
- [ ] Run full `.venv/bin/python -m pytest` if repaired environment supports repository deps;
  otherwise use isolated compatible interpreter and report exact command and missing coverage.
  Never mark a partial suite as full. Run CLI --help and compile/import smoke checks.
- [ ] Check git diff --check and inspect secrets in own diff; preserve unrelated untracked doc.
- [ ] Write docs/superpowers/plans/2026-11-08-standalone-tuya-report.md with files, tests,
  deviations, actual blockers, and physical-validation limits. Return report path to parent.

## Follow-on investigation (not fabricated in this implementation)

Obtain a fresh DP154 snapshot and validate its encoding; research official Tuya resource
resolution for DP185; then test a person event without HA using a real frame and the configured
classifier. Until then no claim of fully automatic person classification on this physical device.
