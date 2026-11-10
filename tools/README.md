# Tools

Utility scripts for local development and manual verification.

## `publish_e2e_images.py`

Publishes every file from `tests/e2e/images` to a single MQTT topic as raw binary payload.
By default it reads `MQTT_HOST`, `MQTT_PORT`, and `MQTT_TOPIC_IN` from the repository `.env`.
If `MQTT_TOPIC_IN` contains `+`, the script replaces it with `--source-id` (default: `e2e`).

Example:

```bash
poetry run python tools/publish_e2e_images.py \
  --source-id front-door
```

Dry-run example:

```bash
poetry run python tools/publish_e2e_images.py \
  --source-id front-door \
  --dry-run
```

Options:

- `--broker`, `--port`, `--topic` override values loaded from `.env`
- `--source-id` replaces `+` in `MQTT_TOPIC_IN`. Default: `e2e`
- `--images-dir` overrides the source directory. Default: `tests/e2e/images`
- `--delay` controls pause between publishes. Default: `0.5`
- `--qos` sets MQTT QoS. Default: `1`

## `e2e_photo_to_description.py`

Runs a user-level E2E scenario:

1. Publish image(s) to YAIC input topic.
2. Wait for classification response on YAIC output topic.
3. Print a compact description per image.

Defaults are loaded from `.env`:

- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_TOPIC_IN`
- `MQTT_TOPIC_OUT`

Example:

```bash
poetry run python tools/e2e_photo_to_description.py \
  --source-id front-door
```

Single image:

```bash
poetry run python tools/e2e_photo_to_description.py \
  --source-id front-door \
  --image tests/e2e/images/163c26258869eab946d93ae62e8bdc05.jpg
```

Dry run:

```bash
poetry run python tools/e2e_photo_to_description.py \
  --source-id front-door \
  --dry-run
```

## `test-in-container.sh`

Run pytest in a disposable Python 3.12 container with persistent dependencies:

```bash
./tools/test-in-container.sh
./tools/test-in-container.sh tests/test_mqtt_client.py -q
./tools/tests/test-in-container_smoke.sh
```

The host directory `${XDG_CACHE_HOME:-$HOME/.cache}/yaic-tests` is bind-mounted
at `/cache`. The container runs with the caller's UID/GID so pip can use
the host-owned cache. It holds both the pip download cache (`pip/`) and installed virtual
environments (`envs/`). A temporary snapshot of `yaic/`, `tests/`, `tools/` and build metadata is
mounted read-only; `.env*`, `auth.json`, Git metadata and local environments are
excluded. No `.env` file, broker,
credentials, camera, or VLM configuration is passed to the container.

The default `tools/Dockerfile.tests` builds a small Python 3.12 test image with
native build/runtime libraries. Docker caches that OS layer between runs; it
does not fetch face models.

The first run resolves the package constraints in `pyproject.toml` and installs
pytest 7.x. This helper does not claim a Poetry lockfile installation. Subsequent
runs with unchanged dependency files and Python runtime reuse the installed
virtual environment and skip pip entirely. Changes to `pyproject.toml`,
`poetry.lock`, the helper, Python version or platform select a separate environment.
Current source is copied from the checkout on every run, so source edits do not
require reinstalling dependencies.

Set `YAIC_TEST_REFRESH=1` for an explicit dependency refresh within the current
constraints. If installation is interrupted, the environment is not marked ready
and the next run retries using the existing pip cache. Override `YAIC_TEST_CACHE`
with an absolute host path or `YAIC_TEST_IMAGE` with a compatible Python image.
A custom image must provide any required native libraries and build tools. Cached files can be
removed locally when no test run is active; they are never committed.

To verify reuse, run the same command twice. The second prints
`Reusing test dependencies from persistent mount (no pip install)` and directly
starts pytest, without dependency downloads.
