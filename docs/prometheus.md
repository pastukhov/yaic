# Prometheus observations

Long-running MQTT and `listen-tuya` modes serve `GET /metrics` using the existing
FastAPI server (`API_HOST`, default `0.0.0.0`; `API_PORT`, default `8080`). Face
recognition is optional. `classify` starts no HTTP server. Scraping performs no
LAN, broker or VLM calls. Restrict access to the HTTP port through your network
configuration; the endpoint has no authentication.

```yaml
scrape_configs:
  - job_name: yaic
    static_configs:
      - targets: ['yaic:8080']
```

Counters reset on process restart. Prometheus supplies retention and rates.

The Docker image includes `prometheus.io/scrape=true`,
`prometheus.io/port=8080`, `prometheus.io/path=/metrics` and
`prometheus.io/scheme=http` labels, and exposes TCP port 8080 as image metadata.
Your Docker discovery configuration must map these labels to scrape targets;
Prometheus does not interpret them automatically. If you override `API_PORT`,
also override the container's `prometheus.io/port` label to match. `EXPOSE`
does not publish the port on the host.

| Metric | Meaning |
| --- | --- |
| `yaic_stage_total{stage,outcome}` | Completed pipeline, extraction, classification, face, role, snapshot-fetch and VLM transport stages; success/error |
| `yaic_stage_duration_seconds{stage}` | Elapsed seconds, including failures |
| `yaic_last_success_timestamp_seconds{stage}` | Wall time of last successful stage, absent before success |
| `yaic_vlm_requests_total{operation,outcome}` | Each HTTP attempt: success, HTTP error or transport error |
| `yaic_vlm_tokens_total{model,operation,direction}` | Reported nonnegative integer input/output tokens |
| `yaic_vlm_usage_missing_total{model,operation}` | Responses lacking either valid token field, including invalid JSON |
| `yaic_mqtt_connected` | Broker callback connection state |
| `yaic_mqtt_publish_total{kind,outcome}` | Enqueue result for output/status/operation/log, not broker acknowledgement |
| `yaic_tuya_queue_depth` | Waiting snapshot jobs |
| `yaic_tuya_snapshot_unavailable_total{reason}` | Missing snapshot source, full queue, expiry, shutdown or download failure |
| `yaic_tuya_events_total{kind}` | Accepted decoded events after deduplication |
| `yaic_device_connected{transport="lan"}` | LAN transport state; absent in MQTT-only mode |
| `yaic_device_observed_timestamp_seconds{transport="lan"}` | Last valid DP dictionary received |
| `yaic_device_setting{setting}` | Last validated numeric/boolean setting or device state |
| `yaic_device_setting_observed_timestamp_seconds{setting}` | Per-field observation wall time |

VLM operations are `classify`, `details`, `role`, `verify_identity`. Token usage is
recorded on every HTTP response before status checks or content parsing, including
responses rejected for response_format and subsequent retries. Explicit zero
creates a zero sample; missing usage increments a separate counter. Partial usage
counts valid fields and increments missing once. Usage is never estimated.
`model` is the configured VLM model, so `openrouter/auto` aggregates the models
chosen by that router. Arbitrary provider-returned model strings are not labels.
VLM stage duration measures HTTP transport and response observation; transport
exceptions and HTTP rejection count as errors and do not advance last success.
Request outcome separately distinguishes transport errors from HTTP errors. Pipeline and
classification outcomes include parsing and business-level exceptions.

## Verified intercom map

The implementation follows these existing local evidence sources, not a generic
Tuya camera schema:

- `домофон/src/domofon_capture/settings.py` and `settings_codec.py`: DP104
  timestamp overlay, DP134 motion detection, DP168 motion area enabled (strict
  booleans); DP169 one rectangle in integer percentages.
- `домофон/src/domofon_capture/device_state.py` and README sections “MQTT settings”
  / “Additional device state and events”: SD109 `total|used|free` in KiB, SD110
  codes 1 normal / 2 fault / 3 full / 4 formatting / 5 missing; panel239/240
  `Ring`/`Normal`; DP231 selected channel and validated channel IDs.

Exported fixed setting names: `timestamp_overlay`, `motion_detection`,
`motion_area_enabled`, `motion_area_{x,y,width,height}_percent`,
`sd_{total,used,free}_bytes`, `sd_status_code`, `panel_{1,2}_ring`,
`channel_selected`. Numeric codes keep the enum vocabulary bounded. Channel
names, source IDs, person identities, URLs and arbitrary strings never become
labels. Unsupported enum values and malformed reports remove that field and its
observation timestamp; fields not included in a report retain their last valid
observation. Compare observation timestamps with current time to assess staleness.
Disconnected state retains last observations with their original timestamps.

Only read-only SD109/110 are queried at connection. Writable settings and event
DPs are observed passively on the existing listener. The tested device22 firmware
resets writable booleans when queried with null, and alarm polling can replay
alarms. No writes, writable/null polls, UPDATEDPS or additional LAN connections
are introduced.

**Volume, melody and night mode are not exported:** no verified DP mapping or
readable-state contract for those settings was found in the local evidence.
They remain unknown, not zero or disabled. This release covers every setting in
the verified map above; it does not claim all settings visible in Smart Life.
MQTT-only mode observes image processing and broker health but does not consume
the bridge's settings/device-state topics, so it cannot expose LAN device state.
No hardware validation or production deployment is implied by unit tests.
