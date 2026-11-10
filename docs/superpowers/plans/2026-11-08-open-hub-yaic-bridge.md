# Open Hub tool and MQTT exchange implementation

User steering superseded the unused local subprocess bridge: domofon publishes
local events/photos to MQTT; YAIC consumes images and publishes classification.
No subprocess capture bridge is wired into YAIC. No Git/worktrees or secret edits.

- [x] Persist bounded legacy HTTPS Open Hub listen/offer tool, exact MQTT topic,
  verified TLS, matched sessions, metadata-only logs, memory-only credentials.
- [x] Add domofon mqtt service: bounded event queue/dedup, human/ring local photo,
  event_id envelope, nonretained images, retained online/offline Last Will.
- [x] Port only minimal read-only LAN decoder/listener from YAIC, with provenance;
  no runtime cross-repository import. Preserve photo/video commands and mounts.
- [x] YAIC honors configured input template, preserves binary compatibility and
  echoes validated optional event_id; HA-disabled mode skips fixed HA image/event
  channels so isolated private tests do not leak into production topics.
- [x] Meaningful RED→GREEN tests, default domofon testpaths, full prepared YAIC suite.
- [x] Fix independent P2 with fail-stop broker-disconnect behavior and sanitized
  service failure; distinguish graceful shutdown with regression tests.
- [x] Bounded real LAN listener+capture->isolated broker hardware test and legacy
  Open Hub offer. Capture and metadata exchange passed; real VLM endpoint returned401.
- [x] Saved-JPEG/stub-backend roundtrip through real YAIC Processor and broker,
  explicitly separate from actual inference. Preserve host mount and no archive.
- [x] Validation overlay build/help,39 container tests and implementation report.
  Generic clean build remains network-limited (av35MB download); cancelled after
  prolonged stall. Do not claim clean-from-base build acceptance.
- [ ] Real VLM acceptance after correct provider endpoint/model is supplied.

Physical human/ring trigger remains untested: acceptance injects a synthetic known
notification through the production consumer while the real LAN reader is active.
No router/device settings, physical actions, long-running deployment or secret
changes. Only unique isolated test topics; stop processes and clear test retained
metadata afterward. HD/auth longevity/cold boot/WAN independence remain prior limits.
