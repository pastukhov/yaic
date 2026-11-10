# Standalone YAIC and read-only Tuya events

YAIC has no Home Assistant integration. MQTT is optional for these commands. Install the project
with `poetry install --with dev`; Python 3.11 or newer is required. The current
package still installs face dependencies, but imports/initializes them only
when `CHROMA_HOST` is configured. No new web API is opened by standalone commands.

## One local image

```bash
export YAIC_LANGUAGE=en
# Configure VLM_ENDPOINT, VLM_MODEL and VLM_API_KEY for your provider if needed.
poetry run yaic classify --image /path/to/frame.jpg --source-id front-door
```

This invokes the existing Processor, including optional face and role recognition,
and writes one classification JSON object to stdout. `CHROMA_HOST` defaults to
empty (disabled). Diagnostics use stderr; command/configuration failures exit 1,
argument errors exit 2. `VLM_API_KEY` defaults to `none`, endpoint to OpenRouter;
classification requires a reachable, correctly configured vision provider.
No `MQTT_*` settings are required. Existing language/threshold semantics apply.

## Local Tuya event stream

Keep credentials in an external JSON file with restrictive permissions, outside
the repository. Its schema is `id`, `ip`, `local_key` (nonempty strings), and
`version` (3.3). Obtain your own device credentials separately; do not paste them
into logs or commit them.

```bash
poetry run yaic listen-tuya --device-config /private/device.json --source-id front-door
```

Event-only mode requires neither language nor VLM settings; it never constructs
a classifier or downloads a snapshot. JSONL stdout contains `event_type`, `source`,
`received_at` (UTC), optionally numeric `device_timestamp`, and panel 1/2 for DP239/240.
Kinds are `human_detected`, `doorbell_ring`, `doorbell_idle`, `doorbell_image`.
No signed URL, raw DP185 resources, key, or dedup fingerprint is public output.
Diagnostics go to stderr. Consumer/output failures stop ingestion.

TinyTuya 1.20.0 uses device22 / LAN 3.3, socket retry 1, timeout 2 s and a persistent
socket. The only initial query is a status request with null DP 109, 110, 136, 239,
240, 243, 244. Subsequent traffic is received passively. There are no DP writes,
lock operations, reset, OTA or speculative resource commands. Errors reconnect
with 1, 2, 4, ... 30 s interruptible backoff; ordinary receive timeout does not reconnect
and waits another 0.1 s to avoid spinning. No heartbeat was added; long-idle
connection liveness has not been validated on hardware.

## Optional classification

```bash
export YAIC_LANGUAGE=en
export YAIC_SNAPSHOT_URL=https://your-camera.example/current.jpg
poetry run yaic listen-tuya --device-config /private/device.json --source-id front-door --classify
```

For human events, the explicitly configured HTTP(S) snapshot endpoint must return
a fresh image. The device's DP185 resource descriptor is not resolved: its URL
construction/decryption is unknown. Without that endpoint, human events produce
`snapshot_unavailable` with reason `no_snapshot_source` and never call VLM.
A DP154 doorbell image uses its own signed HTTPS URL, separately from the human
endpoint. Do not reuse an expired URL from a recording. DP154 links may expire
within 60 s. Their real image encoding remains physically unverified.

The downloader sends no Authorization header, rejects redirects (including
HTTPS downgrades), URL credentials, compressed responses and non-images, caps
streamed bytes at 10 MiB, and verifies then decodes images with Pillow before VLM.
Images above 40 million pixels are rejected. HTTPX timeout is 5 s per network
operation, with a 5 s elapsed deadline checked between streamed chunks. A blocked
read can extend wall time by one read timeout; it is not a strict 5 s wall-clock
cancellation. Signed URLs/headers are suppressed from HTTPX/HTTPCore request logs;
errors use generic messages and never echo exception URLs.

One classification worker handles at most 8 queued jobs; new excess jobs emit
`snapshot_unavailable`/`queue_full`. Jobs waiting more than 5 s are rejected as
`snapshot_job_expired` before download; this sacrifices events during slow
inference rather than fetching an old frame. The endpoint's own freshness is
still your responsibility. The reader emits events independently of inference.
Successful output is `event_type=classified` with the Processor payload and
`trigger` containing the public originating event. Download failures emit
`snapshot_unavailable`/`download_failed`; inference failures emit
`classification_failed`. Output lines from both threads are serialized.

Identical event content/timestamp is suppressed for 30 s with a 256-entry cache;
panels remain independent and Ring after Normal is eligible immediately. Later
repeats are eligible again. SIGINT/SIGTERM stop ingestion and close the socket
(after an active receive timeout), reject queued jobs as `shutdown`, and wait
for the non-daemon worker. Active VLM calls are not cancelled: existing configured
timeouts/retries and optional face/role calls can delay exit substantially.

## Existing MQTT mode

`poetry run yaic` remains the default MQTT service and requires its existing
MQTT settings plus `YAIC_LANGUAGE`. Classification is published exactly to
`MQTT_TOPIC_OUT`, with `source` and optional `event_id` in the JSON result.
Lifecycle and operation status use `MQTT_TOPIC_STATUS`; logs use `MQTT_TOPIC_LOG`.
The optional face management HTTP API still starts only in MQTT mode when Chroma
is configured. Home Assistant discovery, fixed image/event publications and the
bundled blueprint have been removed. Legacy `HA_TOKEN` and `HA_DISCOVERY_ENABLED`
settings are ignored; existing retained broker messages are not automatically
cleared. Generic image URLs receive no HA credentials: use bytes/base64 or a
suitable signed URL for authenticated image sources.

## Physical validation still needed

Synthetic tests prove event decoding, read-only transport configuration,
snapshot rejection and mocked event-to-Processor JSONL integration. They do not
prove physical snapshot acquisition or notifications to a phone. Obtain a fresh
DP154 event and validate its actual image; investigate official DP185 resource
resolution separately, then test a real person event using a fresh frame and the
configured classifier. DP154 snapshots are cloud-hosted; LAN event delivery does
not establish operation without WAN. No automatic live inference/device calls
are part of these tests.
