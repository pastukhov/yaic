# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
poetry install              # install dependencies
.venv/bin/python -m pytest                          # run all tests
.venv/bin/python -m pytest tests/test_vlm_client.py # run a single test file
.venv/bin/python -m pytest -k "test_name"            # run a single test by name
docker compose up --build                                                        # prod: external MQTT from .env
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build     # dev: includes local Mosquitto (YAIC + broker)
.venv/bin/python tools/e2e_photo_to_description.py   # run e2e scenario (requires running stack)
```

The virtualenv must live in `.venv`. The shebang inside `.venv/bin/pytest` is broken (points to old path), so always invoke pytest via `.venv/bin/python -m pytest`. There is no linter configured; the project has no `ruff`, `mypy`, or similar tool in `pyproject.toml`.

## Architecture

YAIC is a single-process service that subscribes to MQTT, classifies images via a VLM API, and publishes results back to MQTT with Home Assistant auto-discovery.

**Data flow:**

```
MQTT broker
  → MqttClient._on_message()         (mqtt_client.py)
  → Processor.process_message()       (processor.py)
  → VlmClient.classify_image()        (vlm_client.py)  ← HTTP to VLM API
  ← ClassificationResult
  → publish to output/image/event topics
```

**Key design points:**

- `VlmClient` (`vlm_client.py`) speaks OpenAI-compatible chat completions. It sends images as data URLs (`data:image/jpeg;base64,...`) in `image_url.url`. If the first response has label `"person"` but no person details, a second request is made with a dedicated detail prompt. All API coupling is isolated here. Default endpoint is OpenRouter (`OPENROUTER_ENDPOINT`), default model is `openrouter/auto` (`DEFAULT_MODEL`) — OpenRouter selects the best available vision model automatically.
- `VlmClient._post_image` retries on network errors with exponential backoff. On HTTP 400 it silently retries without `response_format` (some backends reject it). Responses may contain `<think>...</think>` blocks or markdown fences — these are stripped before JSON parsing; `_recover_json_payload` is the last-resort regex fallback.
- `Processor` is a thin orchestration layer: extracts image bytes from raw binary or JSON-wrapped (`{"image_b64": ..., "device": ...}`) MQTT payloads, calls `VlmClient`, and packages the result.
- `MqttClient` manages broker lifecycle (auto-reconnect, SIGTERM/SIGINT), dispatches messages, publishes classification results to `yaic/output/<source_id>/classification`, the last image to `yaic/image/<source_id>/last` (retained), and an event to `yaic/event/<source_id>`. Logs are streamed to MQTT via `_MqttLogHandler`. It also subscribes to `<status_prefix>/+` so registering a device from its status topic triggers HA discovery without needing to classify an image first.
- `ha_discovery.py` builds Home Assistant MQTT Discovery payloads (10 entities per source: 6 sensors, 1 binary sensor, 1 camera, 1 event). Discovery is published on connect and on first message from each new source. Topic helpers (`build_output_topic`, `build_status_topic`, etc.) are used by both `mqtt_client.py` and `ha_discovery.py`.
- `config.py` loads everything from environment variables and fails fast with a list of missing names.

**HA Blueprint** (`blueprints/automation/yaic/`): end-to-end Home Assistant automation — takes a camera snapshot, waits a configurable delay, publishes the image as `{"image_b64":..., "device":...}` JSON to MQTT, waits for the classification result on `yaic/output/<source_id>/classification`, then fires a user-supplied notify action with `_result_text`, `_notify_image`, etc. as template variables.

## MQTT topic structure

| Direction | Topic pattern |
|-----------|---------------|
| Input | `yaic/input/<source_id>/image` |
| Output | `yaic/output/<source_id>/classification` |
| Last image | `yaic/image/<source_id>/last` (retained) |
| Event | `yaic/event/<source_id>` |
| Status | `yaic/status/<source_id>` |
| Operation status | `yaic/status/<source_id>/operation` |
| Logs | `MQTT_TOPIC_LOG` (env var) |

## Required environment variables

| Variable | Notes |
|----------|-------|
| `MQTT_HOST` | broker address |
| `MQTT_TOPIC_IN` | input subscription topic |
| `MQTT_TOPIC_OUT` | output topic prefix |
| `MQTT_TOPIC_STATUS` | status topic prefix |
| `MQTT_TOPIC_LOG` | log streaming topic |
| `VLM_API_KEY` | bearer token (OpenRouter API key for cloud, any string for local) |
| `VLM_ENDPOINT` | optional, OpenAI-compatible base URL (default: `https://openrouter.ai/api/v1/chat/completions`) |
| `YAIC_LANGUAGE` | ISO 639 language code for free-text fields in output |
| `VLM_MODEL` | optional, model name (default: `openrouter/auto`) |
| `MQTT_PORT` | optional, default `1883` |
| `YAIC_INFERENCE_TIMEOUT` | optional, seconds (default: `60`) |
| `YAIC_INFERENCE_TEMPERATURE` | optional, float (default: `0.1`) |
| `LOG_LEVEL` | optional, default `INFO` |
