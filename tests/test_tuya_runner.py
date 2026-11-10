import io
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock
from yaic.tuya_events import TuyaEvent
from yaic.tuya_runner import TuyaRunner


class Source:
    def __init__(self, events): self.events = events
    def run(self, callback, stop):
        for event in self.events: callback(event)


def payloads(output): return [json.loads(line) for line in output.getvalue().splitlines()]


def test_event_only_never_fetches():
    output = io.StringIO()
    fetch = Mock(side_effect=AssertionError)
    TuyaRunner(Source([TuyaEvent('human_detected','door')]), output=output, fetch=fetch).run(threading.Event())
    assert payloads(output)[0]['event_type'] == 'human_detected'
    fetch.assert_not_called()


def test_missing_human_snapshot():
    output = io.StringIO()
    processor = Mock()
    TuyaRunner(Source([TuyaEvent('human_detected','door')]), processor=processor, output=output).run(threading.Event())
    assert payloads(output)[-1]['event_type'] == 'snapshot_unavailable'
    processor.process_message.assert_not_called()


def test_classifies_with_context_and_private_url():
    output = io.StringIO()
    processor = Mock()
    processor.process_message.return_value = SimpleNamespace(payload={'label':'person', 'source':'door'})
    fetch = Mock(return_value=b'image bytes')
    event = TuyaEvent('doorbell_image','door', snapshot_url='https://example.test/?private=yes')
    TuyaRunner(Source([event]), processor=processor, output=output, fetch=fetch).run(threading.Event())
    processor.process_message.assert_called_once_with(b'image bytes','door')
    last = payloads(output)[-1]
    assert last['event_type'] == 'classified'
    assert last['trigger']['event_type'] == 'doorbell_image'
    assert 'private' not in output.getvalue()


def test_failed_download_does_not_classify():
    output = io.StringIO()
    processor = Mock()
    fetch = Mock(side_effect=RuntimeError('private URL'))
    TuyaRunner(Source([TuyaEvent('human_detected','door')]), processor=processor, snapshot_url='https://example.test/', output=output, fetch=fetch).run(threading.Event())
    assert payloads(output)[-1]['event_type'] == 'snapshot_unavailable'
    assert 'private' not in output.getvalue()
    processor.process_message.assert_not_called()


def test_dedup_expiry_and_ring_idle_transition():
    output = io.StringIO()
    clock = iter([0,1,2,3,35])
    ring = TuyaEvent('doorbell_ring','door', dedup_key='same')
    events = [ring, ring, TuyaEvent('doorbell_idle','door',dedup_key='idle'),ring,ring]
    TuyaRunner(Source(events), output=output, clock=lambda:next(clock)).run(threading.Event())
    assert [p['event_type'] for p in payloads(output)] == ['doorbell_ring','doorbell_idle','doorbell_ring','doorbell_ring']


def test_two_panels_do_not_suppress_each_other():
    from yaic.tuya_events import decode_events
    events = decode_events({'dps':{'239':'Ring','240':'Ring'}},'door')
    events += decode_events({'dps':{'239':'Normal','240':'Ring'}},'door')
    output = io.StringIO()
    TuyaRunner(Source(events), output=output).run(threading.Event())
    assert [(p['event_type'],p['panel']) for p in payloads(output)] == [('doorbell_ring',1),('doorbell_ring',2),('doorbell_idle',1)]


def test_backpressure_expired_backlog_and_independent_event_output():
    started = threading.Event()
    release = threading.Event()
    now = [0.0]
    processor = Mock()
    def classify(image, source):
        started.set()
        assert release.wait(3)
        return SimpleNamespace(payload={'label':'person','source':source})
    processor.process_message.side_effect = classify
    class Burst:
        def run(self, callback, stop):
            callback(TuyaEvent('human_detected','door',dedup_key='first'))
            assert started.wait(3)
            for index in range(10):
                callback(TuyaEvent('human_detected','door',dedup_key=str(index)))
            callback(TuyaEvent('doorbell_ring','door'))
            now[0] = 6
            release.set()
    output = io.StringIO()
    fetch = Mock(return_value=b'image')
    TuyaRunner(Burst(), processor=processor, snapshot_url='http://example.test/', output=output, fetch=fetch, clock=lambda:now[0]).run(threading.Event())
    rows = payloads(output)
    assert len([p for p in rows if p['event_type']=='human_detected']) == 11
    assert len([p for p in rows if p.get('reason')=='queue_full']) == 2
    assert len([p for p in rows if p.get('reason')=='snapshot_job_expired']) == 8
    assert len([p for p in rows if p['event_type']=='doorbell_ring']) == 1
    assert processor.process_message.call_count == 1
    assert fetch.call_count == 1


def test_fake_end_to_end_decoded_human_with_real_processor():
    import base64
    from yaic.processor import Processor
    from yaic.tuya_events import decode_events
    from yaic.vlm_client import ClassificationResult, PersonSummary
    vlm = Mock()
    vlm.classify_image.return_value = ClassificationResult(label='cat',confidence=.9,person=PersonSummary(count=0,description=None,details=(),age_summary=None,gender_summary=None,role_summary=None))
    event, = decode_events({'dps':{'185':base64.b64encode(b'{"cmd":"ipc_human"}').decode()}},'door')
    output = io.StringIO()
    TuyaRunner(Source([event]), processor=Processor(vlm), snapshot_url='http://example.test/',output=output, fetch=lambda _:b'\xffsynthetic-image').run(threading.Event())
    result = payloads(output)[-1]
    assert result['label'] == 'cat'
    assert result['source'] == 'door'
    assert result['trigger']['event_type'] == 'human_detected'
    vlm.classify_image.assert_called_once_with(b'\xffsynthetic-image')


def test_shutdown_drops_pending_and_waits_for_active_inference():
    started = threading.Event()
    release = threading.Event()
    stop = threading.Event()
    source_stopped = threading.Event()
    processor = Mock()
    def classify(*args):
        started.set()
        assert release.wait(3)
        return SimpleNamespace(payload={'source':'door','label':'cat'})
    processor.process_message.side_effect = classify
    class Shutdown:
        def run(self, callback, signal):
            callback(TuyaEvent('human_detected','door',dedup_key='one'))
            assert started.wait(3)
            callback(TuyaEvent('human_detected','door',dedup_key='two'))
            signal.set()
            source_stopped.set()
    output = io.StringIO()
    runner = TuyaRunner(Shutdown(),processor=processor,snapshot_url='http://example.test/',output=output,fetch=lambda _:b'image')
    thread = threading.Thread(target=runner.run,args=(stop,))
    thread.start()
    assert source_stopped.wait(3)
    release.set()
    thread.join(3)
    assert not thread.is_alive()
    assert processor.process_message.call_count == 1
    assert any(row.get('reason')=='shutdown' for row in payloads(output))


def test_closed_output_does_not_deadlock_worker():
    class Closed:
        def write(self, text): raise BrokenPipeError('closed')
    runner = TuyaRunner(Source([TuyaEvent('human_detected','door')]),processor=Mock(),snapshot_url='http://example.test/',output=Closed())
    failures = []
    def run():
        try: runner.run(threading.Event())
        except Exception as exc: failures.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    thread.join(2)
    assert not thread.is_alive()
    assert isinstance(failures[0],BrokenPipeError)
