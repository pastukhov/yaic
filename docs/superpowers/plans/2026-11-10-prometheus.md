# Prometheus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose bounded, read-only Prometheus observations for YAIC health, VLM usage and verified intercom state.

**Architecture:** A shared Metrics object owns an isolated CollectorRegistry. FastAPI serves that registry independently of face support; instrumentation observes existing calls and passive LAN reports.

**Tech Stack:** Python, prometheus-client, FastAPI, pytest.

**Spec:** docs/superpowers/specs/2026-11-10-prometheus-design.md

## Global Constraints

Preserve existing uncommitted work and private deployment configuration. No HTTP server in one-shot mode. Never poll writable Tuya DPs. Unknown observations are absent. No private or arbitrary device labels.

## Review Focus

- Provider responses with malformed content still contribute reported usage.
- Missing usage differs from explicit zero; response-format retries count independently.
- Invalid device values remove previous observations; timestamps reveal staleness.
- MQTT-only runtime exposes no fabricated device observations.
- HTTP metrics works without optional face dependencies.

### Task 1: Registry and state observations

Files: create `yaic/metrics.py`, `tests/test_metrics.py`; modify `pyproject.toml`, `poetry.lock`.
Interface: `Metrics(registry=None)`, `metrics` singleton; context `stage(name)` and `observe_device(response)`.
- [x] Write and run failing tests for independent registries, missing/zero usage, state validation and timestamps.
- [x] Implement bounded counters/histograms and verified state codecs.
- [x] Run `.venv/bin/python -m pytest tests/test_metrics.py -q`.

### Task 2: Instrument runtime

Files: modify `yaic/vlm_client.py`, `processor.py`, `mqtt_client.py`, `tuya_source.py`, `tuya_runner.py`, `api.py`, `main.py`; extend metric tests.
Interfaces: optional `metrics` injection on instrumented classes; `/metrics` exports shared registry.
- [x] Write and run failing tests for usage before parsing, retry accounting, safe polling and face-independent scraping.
- [x] Instrument provider response boundaries, processing stages, MQTT results, queue outcomes, passive device state.
- [x] Start existing HTTP server in long-running modes only.
- [x] Run targeted suite then full `.venv/bin/python -m pytest -q`; use existing container helper if local optional deps unavailable.

### Task 3: Documentation and verification

Files: create `docs/prometheus.md`; update this checklist.
- [x] Document exact DP evidence, unavailable settings, labels, timestamps, MQTT limits and scrape configuration.
- [x] Verify full suite, inspect delta and report to parent for independent review.

## Execution rulings

Implementation in existing dirty workspace explicitly authorized; no commits to avoid including preexisting changes. Parent performs final independent review. Initial git diff saved privately to `/tmp/yaic-before-prometheus.patch`. Local venv missing numpy/chromadb at baseline; prometheus-client installed for targeted tests.

## Verification ledger

Task 1: complete; registry/usage/state tests RED→GREEN. Task 2: complete; HTTP, usage retry and safe polling tests RED→GREEN. Task 3: complete; evidence and limitations documented.

Ruling: use configured model as bounded model label; provider-returned strings untrusted, auto routing aggregates actual models. Cost: no per-provider-model breakdown when configured auto.

Review correction: VLM stage outcome includes HTTP rejection; explicit outcome observation preserves response-format fallback and usage accounting while preventing failed HTTP requests from advancing last success.

Parent review DP231 malformed JSON shape finding fixed RED→GREEN. Final full container suite: 126 passed in 1.15s on Python 3.12. Local full suite cannot collect due to baseline missing numpy/chromadb on Python 3.14. Targeted local coverage passes. No hardware validation or deployment.

Final targeted local verification: 62 passed. `git diff --check`: clean. HTTP rejection regression RED→GREEN; 400→200 fallback records error then success, rejected-only requests leave last success absent.
