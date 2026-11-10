# Remove Home Assistant Coupling Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. The user explicitly requested planning and delegation to Sol; proceed with implementation without another approval round.

**Goal:** Remove Home Assistant-specific runtime behavior while preserving standalone classification, Tuya input, ordinary MQTT and optional face recognition.

**Architecture:** MQTT publishes results and lifecycle/operation status using configured topics. Topic construction belongs to a neutral mqtt_topics module. Image URL fetching no longer reads or forwards HA credentials.

**Tech Stack:** Existing Python, pytest, paho-mqtt, httpx; no new application dependencies.

**Spec:** Current user request to remove Home Assistant dependencies, superseding the optional-HA compatibility choice in ../specs/2026-11-08-standalone-tuya-design.md. This document includes the bounded design below.

## Design and scope

Disabling discovery by default leaves HA coupling in place. Extracting an optional HA plugin adds unnecessary maintenance. Remove HA-specific code instead: discovery, fixed retained image/event compatibility publications, HA_TOKEN and HA_DISCOVERY_ENABLED configuration, and bundled HA blueprint. Preserve configured MQTT results/status/logging, event_id correlation in classification results, generic HTTP(S) image input, standalone commands and optional recognition. Authenticated image sources should provide image bytes/base64 or a suitable signed URL; do not invent generic token forwarding.

## Global constraints

- Work in /home/artem/repos/yaic; preserve pre-existing dirty/untracked standalone and Tuya work. No checkout/reset or broad reformatting.
- No commit, push, deploy, service restart, real inference or physical-device calls. No changes to secrets/.env/session artifacts.
- Preserve untracked docs/yaic_image_url_support.md; historical plans/reports may describe old HA behavior.
- Run .venv/bin/python -m pytest after code changes, not the broken pytest shebang.
- Baseline full collection currently fails: missing numpy in test_face_recognition.py and chromadb in test_processor_face.py. Report these separately from regressions. Use targeted tests and an explicit reduced suite if needed; do not fake dependencies or silently skip failures.
- Parent added only test_default_mqtt_publishes_only_configured_topics to tests/test_mqtt_client.py. It was run and fails because HA discovery/image/event publications remain. All other dirty files predate this task.

## Review focus

- Custom MQTT prefixes must not leak images/events to fixed yaic or homeassistant topics (Task 1).
- Reconnect must restore online state for registered sources; shutdown publishes offline (Task 1).
- Input from multiple sources and event_id correlation must remain intact (Tasks 1–2).
- Legacy HA environment variables must not result in credential forwarding to image URLs (Task 2).
- Standalone commands must remain usable without MQTT or HA configuration (Task 2).

## Task 1: Neutral MQTT transport

Files: yaic/mqtt_client.py, yaic/main.py, new yaic/mqtt_topics.py, tests/test_mqtt_client.py; remove yaic/ha_discovery.py and obsolete tests/test_ha_discovery.py.

- [x] Review the existing failing regression; retain exact configured output/status topic assertions and online, online, offline lifecycle expectation.
- [x] Update multi-source and custom-prefix tests to expect only classification and status. Remove HA discovery/event-specific assertions; retain correlation coverage in Processor tests.
- [x] Move build_output_topic(config, source_id=''), build_status_topic(config, source_id), build_operation_status_topic(config, source_id) to mqtt_topics.py, preserving current topic semantics.
- [x] Remove discovery, fixed image/event publications, _build_event_payload and their unused imports. On reconnect publish online for known sources. Remove sw_version constructor argument and unused version lookup in main; update all callers/tests.
- [x] Run .venv/bin/python -m pytest tests/test_mqtt_client.py tests/test_main.py -q, inspect failures, then full suite.

## Task 2: Remove HA configuration and image authorization

Files: yaic/config.py, yaic/processor.py, yaic/runtime.py, docker-compose.yaml, tests/test_config.py, tests/test_processor.py, tests/test_runtime.py and affected callers.

- [x] Replace obsolete HA switch/header tests with an HTTP MockTransport regression: build processor with legacy HA_TOKEN set, request an HA-looking URL, and assert no Authorization header reaches transport and classification succeeds. Keep binary/base64/URL and event_id coverage.
- [x] Remove Config.ha_token, Config.ha_discovery_enabled and environment reads; remove Processor ha_token parameter/state and get_http_headers_for_url. Keep fetch_image_bytes(msg, timeout=5.0) generic and existing error/timeout behavior.
- [x] Remove HA_TOKEN plumbing from runtime and compose. Do not edit .env or unrelated dependencies.
- [x] Run .venv/bin/python -m pytest tests/test_config.py tests/test_processor.py tests/test_runtime.py tests/test_main.py tests/test_mqtt_client.py -q, then full suite. Preserve standalone/Tuya tests.

## Task 3: Documentation and final validation

Files: README.md, docs/standalone-tuya.md, AGENTS.md, CLAUDE.md; remove blueprints/automation/yaic/yaic_person_camera_to_mqtt_notify.yaml.

- [x] Remove active HA setup/discovery/blueprint instructions and stale module descriptions. Correct MQTT docs to configured output topic and source field. Document migration: old HA env vars ignored; auto-discovery and fixed image/event publications removed; existing retained broker messages are not automatically deleted; authenticated image retrieval needs bytes/base64 or signed URL.
- [x] Preserve historical reports/plans and unrelated untracked image URL note; clearly distinguish them in final audit.
- [x] Run rg for HA symbols in runtime, tests, compose and current documentation; inspect residual references for intentional regression/migration coverage.
- [x] Run full pytest and, if baseline optional dependency collection still blocks it, explicit suite excluding only tests/test_face_recognition.py and tests/test_processor_face.py. Run git diff --check. Review diff to verify preservation of prior work.
- [x] Report changed files, tests passed/failed, migration effects and any remaining limitation. Do not claim deployment or real-device validation.

## Execution evidence

- Task 1 regression failed on unwanted discovery/image/event topics before implementation, then MQTT/main: 9 passed.
- Task 2 HTTP MockTransport regression failed on Authorization forwarding before implementation; configuration regression failed on legacy fields. Both now pass.
- Targeted config/processor/runtime/main/MQTT: 20 passed, 2 runtime face factory tests fail because chromadb is absent.
- Full pytest: collection blocked in test_face_recognition.py (numpy absent) and test_processor_face.py (chromadb absent).
- Explicit reduced suite ignoring only those files: 80 passed, 2 failed (the same runtime face factory tests, missing chromadb).
- Additional non-face subset deselecting those two tests: 80 passed, 2 deselected. No dependencies were faked and no tests were silently skipped.
- git diff --check passed. Runtime/compose/current docs audit leaves HA names only in migration and regression coverage. Historical docs and docs/yaic_image_url_support.md intentionally preserved.
- No commits, deployment, live inference, physical device calls or secret changes.
- Fresh independent final review: clean, no important findings; reviewer independently ran 20 targeted tests and diff check.
