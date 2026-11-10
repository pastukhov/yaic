# MQTT exchange and legacy Open Hub — implementation report

User-approved architecture: domofon publishes events and locally captured photos;
YAIC classifies MQTT images and publishes correlated results. The earlier unused
local subprocess bridge draft was removed before any CLI/event wiring. No Git
operations, secret edits, router changes, firmware/lock operations or deployment
of a persistent daemon occurred.

## Delivered

- `tools/open-hub.py`: legacy signed HTTPS API token/config, bounded `listen` and
  `offer`, verified MQTT TLS and exact source subscription. Credentials/SDP/topics
  remain in memory; output is metadata only. Offer responses match the generated
  session. Finally sends disconnect and closes MQTT/peer resources. Optional MQTT
  extra pins tested paho-mqtt2.2.0.
- `domofon_capture mqtt`: optional service preserving photo/video commands. Read-only
  LAN decoder/source are ported from YAIC with provenance, no runtime YAIC import.
  Human/ring events enter one bounded8-job photo worker; paired image notifications
  do not duplicate ring photos. TTL30s dedup/256 entries, queued-job TTL5s.
- Events: `domofon/{source}/event`; images: configured YAIC input template (default
  `yaic/input/{source}/image`); retained status/Last Will:
  `domofon/{source}/status`. Event and image JSON share UUID event_id. Images use
  image_b64/device/event_id, QoS1, retain=false. No frame archive/offline spool.
- Broker loss is fail-stop: automatic reconnect is disabled, a sanitized failure
  stops the service and returns nonzero. A supervisor may restart it after broker
  recovery. Intentional close does not set failure. This fixes the independent
  review P2 where online delivery could resume while retained status stayed offline.
- YAIC: source extraction honors configured one-plus input mask, existing binary
  input stays compatible, JSON optional event_id is validated and echoed. With
  HA_DISCOVERY_ENABLED=false, discovery and fixed HA image/event compatibility
  publications are skipped, avoiding private test frames in production HA topics.
  Default YAIC behavior remains unchanged.

Docker installs `.[mqtt]`. README documents read-only credentials, current UID/GID,
Linux host networking, host mount `/output`, optional TMPDIR=/output staging and
normal cleanup. The MQTT service does not archive snapshots. Saving persistent
files still uses photo/video arguments targeting the mounted output directory.

## Tests and review

Domofon default `python -m pytest -q`:39 passed. Added testpaths=['tests'] to avoid
collecting private reference SDKs. Tests cover metadata redaction/session matching,
exact topics, envelope shape, DP decoding/privacy, event/photo correlation and
nonretain, duplicate ring/image behavior, bounded burst queue, capture failure,
offline publish, shutdown while capturing, and broker-loss versus graceful stop.
Original capture/fingerprint/transaction tests remain green.

YAIC prepared Python3.11 full environment:
`.superpowers/sdd/2026-11-08-standalone-tuya/venv/bin/python -m pytest -q`:
105 passed. Default `.venv` lacks optional numpy/chromadb and could not collect face
unit tests at baseline; no heavy dependency installation or unrelated change was
made. New template/isolation/event_id tests were observed failing before fixes.

Independent review found one P2 reconnect/status issue. Its fail-stop fix and
idle-loss/graceful regression were observed RED→GREEN. See mqtt-exchange-review.md.

## Device / broker evidence

1. Legacy tool offer (`--timeout20`) succeeded over verified TLS/exact source topic.
   Matching answer and candidates received, disconnect sent. Evidence:
   `docs/evidence/open-hub-tool-offer.jsonl`. No media acceptance is inferred from
   this control-plane probe.
2. First real MQTT/YAIC acceptance timed out waiting for classification; processes
   were stopped. A targeted diagnostic proved the capture side: real LAN listener
   status succeeded and made9 receive calls while the real photo session produced
   JPEG640x360,35930 bytes on the isolated broker topic. The human event and photo
   shared event_id, retain=false. YAIC published processing then error. No listener
   pause/serialization workaround was introduced because concurrent capture worked.
3. A static saved-image diagnostic through the existing key/default endpoint gave
   HTTP401. The user confirmed this key belongs to another provider; this is a
   provider/endpoint mismatch, not evidence that the key itself is invalid. No key
   or response body was logged. Correct endpoint/model are pending user input.
4. Result wiring was separately verified using a saved JPEG, real broker, real
   YAIC MQTT client and Processor, and a deterministic local HTTP stub with dummy
   key. Event/photo/result shared event_id; output label empty/count0 is a STUB
   value, not real inference. All process cleanup passed. Evidence:
   `docs/evidence/mqtt-exchange-stub-e2e.json` (failures=[]).

All live tests used unique domofon-test/<random> topic prefixes for input, output,
status and logs; no production image topic or existing production YAIC consumer
was used. Test retained metadata was cleared. Photos/results were nonretained.
The original diagnostic observer emitted invalid_message entries for scalar
online/offline status and retained-clear messages; these were probe parsing noise.
The restored `mqtt-exchange-e2e.json` records that ignored-metadata count. The actual production error was YAIC
classification failure, separately confirmed as401. The final stub observer
correctly ignores those scalar/clear messages and passed without failures.

Physical human/ring activation was not tested: a synthetic known notification
entered the production consumer/queue while the real LAN reader was active.
Long endurance and all prior HD/auth-lifetime/cold-start/WAN limits remain untested.
No daemon or test backend remains running.

## Container status

The clean generic Dockerfile build was cancelled after its av35MB dependency
fetch stalled, including a retry with host networking. A validation overlay from
the previously verified local capture image completed with final source and the
added pinned paho dependency. Exact completed checks and the clean-build limitation
are recorded below.

## Final container verification and handoff

Validation overlay completed successfully from the previously verified local
capture image plus final application source and pinned paho2.2.0:
`domofon-capture:mqtt-validation`,
`sha256:7865d6a4e0512bbd291ee4dce8db5827f3b621d478589a88729431d94b855666`.
MQTT CLI help and non-root UID10001/dependency/no-secret audit passed with network
none. All39 tests passed inside an ephemeral overlay container in1.42s; tests and
the native-only Open Hub tool were mounted read-only for testing, and pytest was
installed only in that test container. No camera or real provider call was repeated
for container verification.

The generic Dockerfile clean-from-Python build was cancelled after its av35MB
fetch still made no reported progress after277s. This is a network/download limit,
not a successful clean rebuild; the source Dockerfile and optional dependency are
ready for a normal networked build. The overlay tag is the validated current MQTT
image; `domofon-capture:local` remains the prior standalone capture image until a
clean generic build finishes in a later run. No build process is intentionally
left running.

Final native tests39/39; YAIC prepared full tests105/105. Source bundle:
`docs/implementation/mqtt-exchange-source.tar.gz`, explicit application/config/test
files from both repos only, no secrets/captures/private binaries.

Evidence filename correction: a probe string-replacement mismatch initially let
the stub test overwrite the general result file. The successful stub JSON was
preserved at its intended filename; actual device metadata was restored from the
observed diagnostic output and explicitly labeled in mqtt-exchange-e2e.json.
No device test was fabricated or repeated to correct these filenames.

Remaining acceptance: real provider endpoint/model corresponding to the existing
key (user confirmed it is not an OpenRouter key). No key replacement/edit has been
made. Real inference is not claimed. Physical human/ring activation, endurance,
HD, auth lifetime and cold boot/WAN behavior remain unverified. No persistent
service is deployed; README contains explicit deployment commands and mount usage.
