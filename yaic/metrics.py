"""Bounded process-local observations. Scrapes never contact external services."""

from contextlib import contextmanager
import json
import re
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class Metrics:
    def __init__(self, registry=None, clock=time.time):
        self.registry = registry if registry is not None else CollectorRegistry()
        self.clock = clock

        def counter(name, doc, labels=()):
            return Counter("yaic_" + name, doc, labels, registry=self.registry)

        def gauge(name, doc, labels=()):
            return Gauge("yaic_" + name, doc, labels, registry=self.registry)

        self.tokens = counter(
            "vlm_tokens",
            "Provider reported tokens",
            ("model", "operation", "direction"),
        )
        self.missing = counter(
            "vlm_usage_missing",
            "Responses without complete valid token usage",
            ("model", "operation"),
        )
        self.calls = counter("vlm_requests", "HTTP attempts", ("operation", "outcome"))
        self.stages = counter(
            "stage", "Processing stage outcomes", ("stage", "outcome")
        )
        self.duration = Histogram(
            "yaic_stage_duration_seconds",
            "Stage elapsed time",
            ("stage",),
            registry=self.registry,
        )
        self.mqtt_connected = gauge("mqtt_connected", "MQTT connection state")
        self.publishes = counter(
            "mqtt_publish",
            "MQTT enqueue results, not delivery acknowledgements",
            ("kind", "outcome"),
        )
        self.device_connected = gauge(
            "device_connected", "Tuya LAN transport state", ("transport",)
        )
        self.device_seen = gauge(
            "device_observed_timestamp_seconds",
            "Last valid LAN state report",
            ("transport",),
        )
        self.last_success = gauge(
            "last_success_timestamp_seconds",
            "Last successful stage completion",
            ("stage",),
        )
        self.setting = gauge(
            "device_setting",
            "Last validated numeric or boolean observation",
            ("setting",),
        )
        self.setting_seen = gauge(
            "device_setting_observed_timestamp_seconds",
            "Observation wall time; unchanged until next report",
            ("setting",),
        )
        self.queue = gauge("tuya_queue_depth", "Queued snapshot jobs")
        self.drops = counter(
            "tuya_snapshot_unavailable", "Snapshot jobs unavailable", ("reason",)
        )
        self.events = counter("tuya_events", "Accepted decoded events", ("kind",))

    @contextmanager
    def stage(self, name):
        start = time.monotonic()
        observation = {"outcome": "success"}
        try:
            yield observation
        except BaseException:
            observation["outcome"] = "error"
            raise
        finally:
            outcome = observation["outcome"]
            self.duration.labels(name).observe(time.monotonic() - start)
            self.stages.labels(name, outcome).inc()
            if outcome == "success":
                self.last_success.labels(name).set(self.clock())

    def usage(self, data, model, operation):
        # Only configured model is a label, never provider-controlled response.model.
        usage = data.get("usage") if isinstance(data, dict) else None
        complete = True
        for key, alternate, direction in [
            ("prompt_tokens", "input_tokens", "input"),
            ("completion_tokens", "output_tokens", "output"),
        ]:
            value = (
                usage.get(key, usage.get(alternate))
                if isinstance(usage, dict)
                else None
            )
            if type(value) is int and value >= 0:
                self.tokens.labels(model, operation, direction).inc(value)
            else:
                complete = False
        if not complete:
            self.missing.labels(model, operation).inc()

    def _setting(self, name, value):
        if value is None:
            for metric in (self.setting, self.setting_seen):
                metric.remove(name)
            return
        self.setting.labels(name).set(value)
        self.setting_seen.labels(name).set(self.clock())

    def observe_device(self, response):
        if not isinstance(response, dict) or "Error" in response or "Err" in response:
            return
        dps = response.get("dps")
        if not isinstance(dps, dict):
            return
        self.device_connected.labels("lan").set(1)
        self.device_seen.labels("lan").set(self.clock())
        for dp, name in [
            ("104", "timestamp_overlay"),
            ("134", "motion_detection"),
            ("168", "motion_area_enabled"),
        ]:
            if dp in dps:
                self._setting(name, int(dps[dp]) if type(dps[dp]) is bool else None)
        if "109" in dps:
            raw = dps["109"]
            values = None
            if isinstance(raw, str) and re.fullmatch(
                r"[0-9]{1,16}\|[0-9]{1,16}\|[0-9]{1,16}", raw
            ):
                total, used, free = map(int, raw.split("|"))
                if total > 0 and used + free == total:
                    values = (total * 1024, used * 1024, free * 1024)
            for index, part in enumerate(("total", "used", "free")):
                self._setting(
                    "sd_" + part + "_bytes", values[index] if values else None
                )
        if "110" in dps:
            raw = dps["110"]
            self._setting(
                "sd_status_code", raw if type(raw) is int and 1 <= raw <= 5 else None
            )
        for dp, panel in [("239", "1"), ("240", "2")]:
            if dp in dps:
                raw = dps[dp]
                self._setting(
                    "panel_" + panel + "_ring",
                    int(raw == "Ring") if raw in ("Ring", "Normal") else None,
                )
        if "169" in dps:
            raw = dps["169"]
            match = (
                re.fullmatch(
                    r"\{num:1,region0:\{x:([0-9]{1,3}),xlen:([0-9]{1,3}),y:([0-9]{1,3}),ylen:([0-9]{1,3})\}\}\n?",
                    raw,
                )
                if isinstance(raw, str) and len(raw) <= 200
                else None
            )
            values = None
            if match:
                x, w, y, h = map(int, match.groups())
                if (
                    0 <= x < 100
                    and 0 <= y < 100
                    and 1 <= w <= 100 - x
                    and 1 <= h <= 100 - y
                ):
                    values = (x, y, w, h)
            for i, part in enumerate(("x", "y", "width", "height")):
                self._setting(
                    "motion_area_" + part + "_percent", values[i] if values else None
                )
        if "231" in dps:
            selected = None
            try:
                raw = dps["231"]
                data = (
                    json.loads(raw) if isinstance(raw, str) and len(raw) <= 2048 else {}
                )
                if not isinstance(data, dict):
                    raise ValueError("Invalid channel report")
                channels = data.get("chs")
                ids = (
                    [c.get("id") for c in channels if isinstance(c, dict)]
                    if isinstance(channels, list)
                    else []
                )
                cc = data.get("cc")
                if (
                    type(data.get("res")) is int
                    and data["res"] == 1
                    and type(data.get("err")) is int
                    and data["err"] == 0
                    and 1 <= len(ids) <= 4
                    and all(type(i) is int and i in (1, 2, 3, 4) for i in ids)
                    and len(set(ids)) == len(ids)
                    and type(cc) is int
                    and cc in ids
                ):
                    selected = cc
            except (ValueError, TypeError, RecursionError):
                pass
            self._setting("channel_selected", selected)


metrics = Metrics()
