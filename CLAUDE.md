# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
poetry install              # install dependencies
poetry run pytest           # run all tests
poetry run pytest tests/test_qwen_client.py  # run a single test file
poetry run yaic             # run the service (requires env vars)
docker compose up --build   # run full stack with Mosquitto
```

The virtualenv must live in `.venv`.

## Architecture

YAIC is a single-process service that subscribes to MQTT, classifies images via a VLM API, and publishes results back to MQTT with Home Assistant auto-discovery.

**Data flow:**

```
MQTT broker
  → MqttClient._on_message()         (mqtt_client.py)
  → Processor.process_message()       (processor.py)
  → QwenClient.classify_image()       (qwen_client.py)  ← HTTP to VLM API
  ← ClassificationResult
  → publish to output/image/event topics
```

**Key design points:**

- `QwenClient` speaks OpenAI-compatible chat completions. It sends a base64-encoded image as `image_url` content, expects a JSON response, and does a second request if person details are missing. All API coupling is isolated here.
- `Processor` is a thin orchestration layer: extracts image bytes from raw or JSON-wrapped (`{"image_b64": ..., "device": ...}`) MQTT payloads, calls `QwenClient`, and packages the result.
- `MqttClient` manages broker lifecycle (auto-reconnect, SIGTERM/SIGINT), dispatches messages, publishes classification results to `yaic/output/<source_id>/classification`, the last image to `yaic/image/<source_id>/last` (retained), and an event to `yaic/event/<source_id>`. Logs are streamed to MQTT via `_MqttLogHandler`.
- `ha_discovery.py` builds Home Assistant MQTT Discovery payloads (10 entities per source: sensors, binary sensor, camera, event). Discovery is published on connect and on first message from each new source.
- `config.py` loads everything from environment variables and fails fast with a list of missing names.

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
| `QWEN_API_KEY` | bearer token (any string for local inference) |
| `QWEN_ENDPOINT` | OpenAI-compatible base URL, e.g. `http://192.168.11.128:8000/v1` |
| `YAIC_LANGUAGE` | ISO 639 language code for free-text fields in output |
| `QWEN_MODEL` | optional, model name (default: `qwen-vl-plus`) |
| `LOG_LEVEL` | optional, default `INFO` |
