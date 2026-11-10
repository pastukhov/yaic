# yaic — Yet Another Image Classifier

yaic classifies images through an OpenAI-compatible VLM API (default: OpenRouter).
It can classify a local file, listen to read-only Tuya LAN events, or run the MQTT service.

Executable app name: `yaic`
Docker image name: `pastukhov/yaic:latest`

## Standalone commands (no Home Assistant or MQTT required)

```bash
YAIC_LANGUAGE=en poetry run yaic classify --image /path/to/frame.jpg --source-id front-door
poetry run yaic listen-tuya --device-config /private/device.json --source-id front-door
```

Add `--classify` to the listener to enable VLM. Human snapshots require an explicit
`YAIC_SNAPSHOT_URL`; DP185 resource downloads are unresolved. DP154 may provide a
signed cloud snapshot, whose real image encoding remains unverified. Event-only
mode makes no VLM or image-download requests. Standalone output is JSONL on stdout;
diagnostics are on stderr. See [setup, output and physical limitations](docs/standalone-tuya.md).

## Local MQTT run

Install deps with Poetry:

```bash
poetry install
```

Set required environment variables and start:

```bash
export MQTT_HOST=localhost
export MQTT_TOPIC_IN=yaic/input/+/image
export MQTT_TOPIC_OUT=yaic/output
export MQTT_TOPIC_STATUS=yaic/status
export MQTT_TOPIC_LOG=yaic/log
export VLM_API_KEY=sk-or-...        # OpenRouter API key
export YAIC_LANGUAGE=en
poetry run yaic
```

## Docker run

Build and run with compose (includes Mosquitto):

```bash
docker compose up --build
```

Or build/push the image name used by this project:

```bash
docker build -t pastukhov/yaic:latest .
```

## systemd

Install and run the unit:

```bash
sudo cp yaic-compose.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yaic-compose
```

Inspect logs:

```bash
journalctl -u yaic-compose -f
```

## Environment variables

Required MQTT variables below apply to the default MQTT service.
Standalone classification only requires `YAIC_LANGUAGE` and working VLM settings.


| Variable | Description | Required |
| --- | --- | --- |
| MQTT_HOST | broker host | yes |
| MQTT_PORT | broker port (default 1883) | no |
| MQTT_MAX_OUTPUT_BYTES | positive maximum serialized output size in UTF-8 bytes (default 16777216, 16 MiB) | no |
| MQTT_TOPIC_IN | input topic | yes |
| MQTT_TOPIC_OUT | output topic | yes |
| MQTT_TOPIC_STATUS | status topic prefix | yes |
| MQTT_TOPIC_LOG | log topic | yes |
| VLM_API_KEY | API key for the VLM provider (OpenRouter key for cloud, any string for local) | no |
| VLM_ENDPOINT | OpenAI-compatible endpoint (default: `https://openrouter.ai/api/v1/chat/completions`) | no |
| VLM_MODEL | model name (default: `openrouter/auto` — automatic selection) | no |
| YAIC_LANGUAGE | response language (ISO 639) | yes |
| YAIC_INFERENCE_TIMEOUT | VLM request timeout in seconds (default `60`) | no |
| YAIC_INFERENCE_TEMPERATURE | VLM temperature (default `0.1`) | no |
| LOG_LEVEL | logging level | no |

## Input and output

Input can be raw binary image bytes or JSON with a base64 payload:

```json
{
  "image_b64": "<base64>",
  "device": "cam-1"
}
```

Output is JSON on the output topic (fields may include people analytics):

```json
{
  "label": "person",
  "confidence": 0.93,
  "person": {
    "count": 2,
    "description": "two people",
    "details": [
      {
        "age_group": "young_adult",
        "gender": "male",
        "appearance": "asian_like",
        "role": "courier"
      }
    ],
    "age_summary": "2 adults",
    "gender_summary": "2 male",
    "role_summary": "courier, unknown"
  },
  "device": "cam-1",
  "source": "front-door",
  "image_b64": "<original image bytes as base64>"
}
```

If no people are present, the payload includes `person.count` set to 0:

```json
{
  "label": "unknown",
  "confidence": 0.0,
  "person": {"count": 0},
  "source": "front-door",
  "image_b64": "<original image bytes as base64>"
}
```

Every successful MQTT result includes `image_b64`, even when no people are present.
It contains the exact original bytes passed to classification, without a data-URL
prefix or another URL download. All existing metadata is preserved. Standalone
CLI JSONL output does not include the image.

Results use QoS 1 and `retain=False`. QoS 1 can deliver duplicates; persistent
sessions can still receive queued older messages. Operation `idle` means processing
finished and the MQTT client accepted publication, not that a subscriber received
it. Oversized results and immediate publish failures report operation `error`,
without publishing a fallback result that omits the image. The size limit applies
to the complete serialized JSON, including base64 and metadata; check broker and
consumer limits (including MQTT overhead) before deployment.

## Topics

All MQTT publications use configured topics:

- Input: `MQTT_TOPIC_IN`, with exactly one `+` segment for the source ID.
- Classification: exactly `MQTT_TOPIC_OUT` (for example `yaic/output`).
- Lifecycle status: `<MQTT_TOPIC_STATUS>/<source_id>` (`online`/`offline`, retained).
- Operation status: `<MQTT_TOPIC_STATUS>/<source_id>/operation` (JSON).
- Logs: exactly `MQTT_TOPIC_LOG` (JSON log records).

The classification payload includes `source`, optional `device`, and the original
validated `event_id` when supplied. Sources share the configured output topic.
Reconnection restores `online` for known sources; graceful shutdown sends `offline`.

JSON input also accepts `image_url` for generic HTTP(S) image retrieval. Sources
that require authentication should supply image bytes/base64 or a suitable signed
URL. YAIC does not forward Home Assistant credentials.

## Migration from Home Assistant integration

Home Assistant discovery, the bundled automation blueprint, retained last-image
copies on `yaic/image/<source_id>/last`, and compatibility events on
`yaic/event/<source_id>` have been removed. Consume classification JSON from
`MQTT_TOPIC_OUT` and use its `source` and optional `event_id` fields.
`HA_TOKEN` and `HA_DISCOVERY_ENABLED` are ignored and can be removed from deployment
configuration. Existing retained discovery/image messages in your broker are not
automatically deleted; remove them separately if no longer needed.

## People analytics

When label is `person`, the result includes count, details per person, and summary fields.
If the API does not provide these fields, yaic requests a richer response; otherwise it falls back to `unknown`.

## Notes

- MQTT uses QoS 1 and auto-reconnect.
- The output payload always includes `label`, `confidence`, and `person`.
- VLM requests are retried with exponential backoff on network errors.
- `VLM_MODEL=openrouter/auto` lets OpenRouter pick the best available vision model automatically.

## E2E scenario

Tools for manual scenario testing are under `tools/`.

1. Publish images from `tests/e2e/images`:

```bash
/home/artem/repos/yaic/.venv/bin/python tools/publish_e2e_images.py --source-id front-door
```

2. Full user flow (`photo -> description`):

```bash
/home/artem/repos/yaic/.venv/bin/python tools/e2e_photo_to_description.py \
  --source-id front-door \
  --timeout 240
```

The tool reads defaults from `.env` (`MQTT_HOST`, `MQTT_PORT`, `MQTT_TOPIC_IN`, `MQTT_TOPIC_OUT`).

### Local intercom MQTT producer

The standalone domofon app can publish events on `domofon/{source}/event` and
nonretained JSON photos on `yaic/input/{source}/image`. Input accepts the existing
binary image format or `{"image_b64":"...","device":"entrance","event_id":"..."}`.
An optional validated `event_id` is copied to the classification result on
`MQTT_TOPIC_OUT`; this correlates the result with the original intercom event.
The source is extracted from the configured `MQTT_TOPIC_IN` mask, which must have
one `+` segment (for example `yaic/input/+/image`). Custom isolated prefixes work.

Photos from domofon are never retained. Configure an actual provider endpoint and
vision model for the key; the default remains OpenRouter, so a key issued by a
different provider cannot be tested against that default endpoint.

Deploy YAIC through its existing Docker entry point, explicitly passing existing
configuration read-only via `--env-file` rather than editing/sourcing secrets:

```sh
docker build -t ghcr.io/pastukhov/yaic:latest .
docker run --rm --network host --env-file .env \
  -e YAIC_LANGUAGE=ru \
  ghcr.io/pastukhov/yaic:latest
```

Set `VLM_ENDPOINT` and `VLM_MODEL` in the deployment environment for your provider;
keep the existing `VLM_API_KEY` out of command arguments and logs. No MQTT service is
automatically started by the code changes. For private integration tests use a
unique input/output/status/log prefix so existing production subscribers cannot
consume test frames or duplicate inference. See the domofon README for capture
service, credentials mounts, bounded queue and lifecycle details.

For an isolated test environment with persistent mounted pip downloads and
installed dependencies, run `./tools/test-in-container.sh`. Repeated runs reuse
the same environment. See [cache location and dependency updates](tools/README.md#test-in-containersh).

### Язык результата определения роли

`YAIC_LANGUAGE` задаёт язык пользовательских текстов YAIC, в том числе
`person.role` (например, `сосед` при `ru`). `person.role_code` сохраняет стабильный
машинный код (`neighbor`). Автоматизации, сравнивающие роль с кодами из списка,
должны использовать `role_code`. Telegram-шлюзу переводить роли не требуется.
Эта настройка не переводит технические идентификаторы источников или метки API.
