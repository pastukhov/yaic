# Repository Guidelines

## Project Structure & Module Organization
- `yaic/` — application package (MQTT client, Qwen API client, processor, entry points).
- `tests/` — pytest test suite (`test_*.py`).
- `Dockerfile`, `docker-compose.yaml` — container build and local stack with Mosquitto.
- `README.md`, `HA.md` — usage docs and integration notes.

## Build, Test, and Development Commands
- `poetry install` — install Python dependencies into the Poetry virtualenv.
- `poetry run yaic` — run the CLI after setting required env vars.
- `poetry run pytest` — run the test suite.
- `docker compose up --build` — build and run the app with Mosquitto locally.
- `docker build -t pastukhov/yaic:latest .` — build the Docker image.

## Coding Style & Naming Conventions
- Python: follow PEP 8 (4-space indentation, snake_case for functions/modules).
- Tests: name files `tests/test_*.py` and test functions `test_*`.
- Keep diffs minimal; avoid reformatting unrelated lines.

## Testing Guidelines
- Framework: pytest (`pytest` is listed under dev dependencies).
- Tests require an active Python virtualenv (Poetry or a manual venv) with dependencies installed.
- The virtualenv must always live in `.venv`.
- Run locally with `poetry install` then `poetry run pytest`.
- Run tests after every code change.
- Add tests for new behavior under `tests/` and keep fixtures close to usage.

## Commit & Pull Request Guidelines
- Git history is not available in this workspace, so no existing commit pattern can be inferred.
- Recommended: concise, imperative subjects (e.g., `config: add retry backoff`).
- PRs should include: purpose, summary of changes, and manual verification steps.

## Security & Configuration Tips
- Do not commit secrets (e.g., `QWEN_API_KEY`); prefer environment variables.
- Required runtime env vars are listed in `README.md` (MQTT and Qwen settings).
- Qwen uses the OpenAI-compatible DashScope endpoint; `QWEN_MODEL` is optional (defaults to `qwen-vl-plus`).
