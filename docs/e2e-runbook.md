# E2E Runbook (Photo -> Description)

This runbook documents the operational flow used to validate YAIC end-to-end with Pyramid.

## Preconditions

- YAIC service is running (`docker compose up -d yaic`).
- MQTT broker is reachable (`MQTT_HOST`, `MQTT_PORT`).
- Pyramid endpoint is reachable (`QWEN_ENDPOINT`).
- A VLM model is loaded and listed at `/v1/models`.

## Verify model availability

```bash
curl -s http://192.168.11.128:8000/v1/models | jq -r '.data[].id'
```

Use exact model ID casing from this list.

## Start YAIC with explicit model

```bash
QWEN_MODEL=internvl3-1B-448-ax650 docker compose up -d --build --force-recreate yaic
```

Confirm container env:

```bash
docker inspect yaic-yaic-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | rg '^QWEN_MODEL=|^QWEN_ENDPOINT='
```

## Run E2E on all fixtures

```bash
poetry run python tools/e2e_photo_to_description.py \
  --source-id front-door \
  --timeout 240
```

Images are read from `tests/e2e/images` by default.

## Read YAIC logs

```bash
docker compose logs --tail=300 yaic
```

## Common failures

- `Unsupported model` (HTTP 400):
  - Model is not currently loaded in Pyramid runtime.
- `Insufficient Memory Resource` (HTTP 503):
  - Selected model does not fit available memory.
- `ReadTimeout` from YAIC:
  - Inference did not finish before `YAIC_INFERENCE_TIMEOUT`.
  - Increase timeout or switch to lighter model.
- E2E tool timeout without output:
  - Check `yaic/status/<source>/operation` and `yaic/log` topics.
  - If status is `error`, inspect YAIC logs for the upstream API error.
