# yaic — Yet Another Image Classifier

yaic subscribes to an MQTT topic, receives an image, sends it to the OpenAI-compatible DashScope Qwen multimodal API, and publishes a classification result to another MQTT topic.
It also registers Home Assistant entities via MQTT Discovery and emits people analytics when persons are detected.

Executable app name: `yaic`
Docker image name: `pastukhov/yaic:latest`

## Local run

Install deps with Poetry:

```bash
poetry install
```

Set required environment variables and start:

```bash
export MQTT_HOST=localhost
export MQTT_TOPIC_IN=yaic/in
export MQTT_TOPIC_OUT=yaic/out
export MQTT_TOPIC_STATUS=yaic/status
export MQTT_TOPIC_LOG=yaic/log
export QWEN_API_KEY=your-key
export QWEN_ENDPOINT=https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions
export QWEN_MODEL=qwen-vl-plus
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

| Variable | Description | Required |
| --- | --- | --- |
| MQTT_HOST | broker host | yes |
| MQTT_PORT | broker port (default 1883) | no |
| MQTT_TOPIC_IN | input topic | yes |
| MQTT_TOPIC_OUT | output topic | yes |
| MQTT_TOPIC_STATUS | status topic prefix | yes |
| MQTT_TOPIC_LOG | log topic | yes |
| QWEN_API_KEY | Qwen API key | yes |
| QWEN_ENDPOINT | OpenAI-compatible DashScope endpoint | yes |
| QWEN_MODEL | Qwen model name (default `qwen-vl-plus`) | no |
| LOG_LEVEL | logging level | no |
| YAIC_LANGUAGE | response language (ISO 639) | yes |

## Input and output

Input can be raw binary image bytes or JSON with base64 payload:

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
  "device": "cam-1"
}
```

If no people are present, the payload includes `person.count` set to 0:

```json
{
  "label": "unknown",
  "confidence": 0.0,
  "person": {"count": 0}
}
```

## Home Assistant Discovery

Discovery topics are published on startup with retain/QoS 1 and include:

- `homeassistant/sensor/yaic_<source_id>_classification/config`
- `homeassistant/sensor/yaic_<source_id>_confidence/config`
- `homeassistant/sensor/yaic_<source_id>_people_count/config`
- `homeassistant/sensor/yaic_<source_id>_people_description/config`
- `homeassistant/sensor/yaic_<source_id>_people_age/config`
- `homeassistant/sensor/yaic_<source_id>_people_gender/config`
- `homeassistant/sensor/yaic_<source_id>_people_roles/config`
- `homeassistant/binary_sensor/yaic_<source_id>_person_detected/config`
- `homeassistant/camera/yaic_<source_id>_last_image/config`
- `homeassistant/event/yaic_<source_id>_event/config`

Camera publishes last image to `yaic/image/<source_id>/last` with retain enabled.
Event payloads are published to `yaic/event/<source_id>` on every classification.

## Topics

Multi-source topic structure:

- Input: `yaic/input/<source_id>/image`
- Output: `yaic/output/<source_id>/classification`
- Last image: `yaic/image/<source_id>/last`
- Event stream: `yaic/event/<source_id>`
- Status: `yaic/status/<source_id>` (`online`/`offline` with retain)
- Operation status: `yaic/status/<source_id>/operation` (JSON with status and timestamp)
- Logs: `yaic/log` (JSON log records)

Incoming payloads include `device`/`source_id`; outgoing payloads include `source_id`.

## Home Assistant Blueprint

Blueprint to snapshot a camera, publish it to YAIC, and send notifications:

- `blueprints/automation/yaic/yaic_person_camera_to_mqtt_notify.yaml`

It snapshots the selected camera, base64 encodes the image, publishes to the YAIC
input topic, and notifies selected targets.

Event payload example:

```json
{
  "event_type": "classified",
  "label": "person",
  "confidence": 0.93,
  "person_count": 2,
  "people": [
    {
      "age_group": "adult",
      "gender": "male",
      "appearance": "unknown",
      "role": "courier"
    }
  ],
  "timestamp": "2024-01-01T12:00:00+00:00"
}
```

## People analytics

When label is `person`, the result includes count, details per person, and summary fields.
If the API does not provide these fields, yaic requests a richer response; otherwise it falls back to `unknown`.

## Limitations and errors

- Qwen responses without required fields fall back to `unknown` and `0.0`.
- MQTT auto-reconnect is enabled; Qwen requests are retried with exponential backoff.
- The Qwen endpoint must accept OpenAI-compatible chat completions with image content.

## Notes

- MQTT uses QoS 1 and auto-reconnect.
- The output payload always includes `label`, `confidence`, and `person`.
