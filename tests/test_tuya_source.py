import threading
from yaic.tuya_source import TuyaSource, READ_DPS


class Device:
    def __init__(self, stop):
        self.stop = stop
        self.closed = False
        self.calls = []
    def set_version(self, value): self.calls.append(('version', value))
    def set_socketPersistent(self, value): self.calls.append(('persistent', value))
    def set_socketTimeout(self, value): self.calls.append(('timeout', value))
    def set_socketRetryLimit(self, value): self.calls.append(('retry', value))
    def status(self):
        assert self.dps_to_request == dict.fromkeys(READ_DPS)
        return {'dps': {'239': 'Ring'}}
    def receive(self):
        self.stop.set()
        return None
    def close(self): self.closed = True


def test_readonly_settings_and_stop():
    stop = threading.Event()
    dev = Device(stop)
    construction = []
    def factory(*args, **kwargs):
        construction.append((args, kwargs))
        return dev
    source = TuyaSource({'id':'synthetic', 'ip':'192.0.2.1', 'local_key':'fake', 'version':'3.3'}, 'door', device_factory=factory)
    events = []
    source.run(events.append, stop)
    assert events[0].kind == 'doorbell_ring'
    assert dev.closed
    assert construction[0][1]['dev_type'] == 'device22'
    assert dev.calls == [('version',3.3), ('retry',1), ('timeout',2), ('persistent',True)]


def test_reconnect_backoff_and_idle_wait():
    stop = threading.Event()
    waits = []
    class Stop:
        def is_set(self): return stop.is_set()
        def wait(self, delay):
            waits.append(delay)
            if len(waits) == 3: stop.set()
    dev = Device(stop)
    attempts = []
    def factory(*args, **kwargs):
        attempts.append(1)
        if len(attempts) <= 2: raise OSError('private detail')
        return dev
    TuyaSource({'id':'fake','ip':'192.0.2.1','local_key':'fake'}, 'door', device_factory=factory).run(lambda e: None, Stop())
    assert waits == [1, 2, .1]
    assert dev.closed


def test_consumer_failure_is_not_retried():
    import pytest
    stop = threading.Event()
    dev = Device(stop)
    def broken(event):
        stop.set()
        raise BrokenPipeError('closed')
    with pytest.raises(RuntimeError,match='consumer'):
        TuyaSource({'id':'fake','ip':'192.0.2.1','local_key':'fake'},'door',device_factory=lambda *a,**k:dev).run(broken,stop)
    assert dev.closed
