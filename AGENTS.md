# Repository Guidelines

## Project Structure & Module Organization
- `yaic/` — application package (MQTT client, VLM API client, processor, entry points).
- `tests/` — pytest test suite (`test_*.py`).
- `Dockerfile`, `docker-compose.yaml` — container build and local stack with Mosquitto.
- `README.md` — usage docs and integration notes.
- `yaic-compose.service` — systemd unit for running docker compose.

## Build, Test, and Development Commands
- `poetry install` — install Python dependencies into the Poetry virtualenv.
- `poetry run yaic` — run the CLI after setting required env vars.
- `/home/artem/repos/yaic/.venv/bin/python -m pytest` — run the test suite (shebang in venv is broken, use python -m pytest directly).
- `docker compose up --build` — build and run the app with Mosquitto locally.
- `docker build -t pastukhov/yaic:latest .` — build the Docker image.

## Coding Style & Naming Conventions
- Python: follow PEP 8 (4-space indentation, snake_case for functions/modules).
- Tests: name files `tests/test_*.py` and test functions `test_*`.
- Keep diffs minimal; avoid reformatting unrelated lines.

## Testing Guidelines
- Framework: pytest (`pytest` is listed under dev dependencies).
- The virtualenv must always live in `.venv`.
- Run locally with `poetry install` then `.venv/bin/python -m pytest`.
- Run tests after every code change.
- Add tests for new behavior under `tests/` and keep fixtures close to usage.

## Commit & Pull Request Guidelines
- Recommended: concise, imperative subjects (e.g., `config: add retry backoff`).
- PRs should include: purpose, summary of changes, and manual verification steps.

## Security & Configuration Tips
- Do not commit secrets (e.g., `VLM_API_KEY`); prefer environment variables.
- Required runtime env vars are listed in `README.md` (MQTT and VLM settings).
- `VLM_ENDPOINT` defaults to OpenRouter; `VLM_MODEL` defaults to `openrouter/auto`.
