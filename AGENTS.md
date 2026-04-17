# Repository Guidelines

## Project Structure
- `yaic/` — application package: `mqtt_client`, `vlm_client`, `processor`, `ha_discovery`, `config`, `main`, `api` (FastAPI), `face_recognition`, `role_classifier`.
- `tests/` — pytest suite (`test_*.py`).
- `tools/` — E2E test helpers.
- `blueprints/automation/yaic/` — Home Assistant automation blueprint.
- `Dockerfile`, `docker-compose.yaml` — container build and local stack (Mosquitto + ChromaDB).

## Commands
- `poetry install --with dev` — install deps (include `--with dev` for test dependencies).
- `poetry run yaic` — run CLI (env vars must be set).
- `.venv/bin/python -m pytest` — run tests (venv shebang is broken, always use `python -m pytest`).
- `docker compose up --build` — build and run app + Mosquitto + ChromaDB locally.
- `docker build -t ghcr.io/pastukhov/yaic:latest .` — build Docker image (use GHCR, not Docker Hub).

## Testing
- Use `.venv/bin/python -m pytest`, never rely on `pytest` shebang or `poetry run pytest`.
- Run tests after every code change.
- Add tests under `tests/test_*.py`; test functions named `test_*`.

## Face Recognition (Optional)
- Disabled when `CHROMA_HOST` is empty (default); app runs in MQTT+VLM-only mode.
- When enabled: starts FastAPI server on `API_HOST:API_PORT` (default `0.0.0.0:8080`).
- Env vars: `CHROMA_HOST`, `CHROMA_PORT`, `FACES_DIR`, `FACE_SIMILARITY_HIGH` (default 0.85), `FACE_SIMILARITY_LOW` (default 0.60), `CLASSIFY_STRANGER_ROLE`, `FACE_INDEX_ON_STARTUP`, `API_HOST`, `API_PORT`.
- Dockerfile pre-downloads InsightFace `buffalo_l` model to avoid cold-start delay.

## Required Env Vars
- Required: `MQTT_HOST`, `MQTT_TOPIC_IN`, `MQTT_TOPIC_OUT`, `MQTT_TOPIC_STATUS`, `MQTT_TOPIC_LOG`, `YAIC_LANGUAGE`.
- Optional: `VLM_API_KEY` (default "none"), `VLM_ENDPOINT` (default OpenRouter), `VLM_MODEL` (default `openrouter/auto`), `MQTT_PORT`, `YAIC_INFERENCE_TIMEOUT`, `YAIC_INFERENCE_TEMPERATURE`, `LOG_LEVEL`, `HA_TOKEN`.
- `VLM_MODEL=openrouter/auto` lets OpenRouter pick the best vision model.

## Architecture Notes
- `MqttClient` — MQTT lifecycle, HA discovery, log streaming, topic helpers shared with `ha_discovery`.
- `Processor` — thin orchestrator: extracts image bytes from raw binary or `{"image_b64": ..., "device": ...}` JSON, calls VLM, packages result.
- `Config` fails fast with a list of missing required env vars.
- Logging output is JSON-formatted to stdout.

## Coding Style
- PEP 8, 4-space indentation, snake_case. Keep diffs minimal.
- Do not commit secrets; use environment variables.
