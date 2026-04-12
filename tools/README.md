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
