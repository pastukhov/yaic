# YAIC Prometheus metrics

## Intent

Expose processing health, intercom settings and VLM token consumption through
Prometheus. No JSON status endpoint or monitoring-stack deployment in this change.

## Approach

The user selected Prometheus only. Prometheus plus JSON would represent arbitrary
settings more naturally, but requires two interfaces. JSON/MQTT alone requires an
additional exporter for historical monitoring.

## Proposed behavior

- Serve `/metrics` independently of optional face recognition in long-running MQTT
  and Tuya listener modes. One-shot classification does not start a server.
- Count image-processing outcomes, measure pipeline and stage durations, expose
  MQTT connectivity/publication failures and Tuya queue/drop statistics.
- Count provider-reported input/output tokens by model and operation, including
  additional calls and retries with reported usage. Capture usage before parsing
  model content. Missing usage gets its own counter and is never estimated as zero.
  Metrics are cumulative within a process; Prometheus stores history across restarts.
- Export every verified, readable intercom setting: numeric gauges, boolean gauges,
  and bounded state labels for known textual modes. Discover the verified DP map
  before implementation; explicitly document settings not available through LAN.
  Do not guess mappings or write device settings.
- Expose device connectivity, last successful state observation and per-setting
  observation timestamps. Unknown values are absent, never fabricated as zero.
- Do not expose credentials, resource URLs, image content, personal identities,
  event IDs or arbitrary device strings as metric labels.

## Constraints and validation

Preserve existing uncommitted work and private deployment configuration. Keep
instrumentation separate from business decisions. Test scrape output, counter and
timer semantics on success/failure, missing usage, and setting updates/staleness.
Run the repository pytest suite. Hardware validation and production deployment are
separate from local test evidence.

## Builder decisions

Use the Python Prometheus client and the existing FastAPI HTTP server. Metric names,
buckets and bounded labels are implementation choices. Check available device-state
sources before adding connections; MQTT-only mode cannot claim local device state
unless it actually receives it.
