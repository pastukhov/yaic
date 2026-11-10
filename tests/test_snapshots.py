import io
import logging
import httpx
import pytest
from PIL import Image
from yaic.snapshots import fetch_snapshot, SnapshotError


def image_bytes():
    out = io.BytesIO()
    Image.new('RGB', (2, 2)).save(out, format='PNG')
    return out.getvalue()


def setup_client(monkeypatch, response):
    original = httpx.Client
    requests = []
    def handle(request):
        requests.append(request)
        if isinstance(response, Exception): raise response
        return response
    monkeypatch.setattr('yaic.snapshots.httpx.Client', lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    return requests


def test_validated_stream_no_token_or_url_logs(monkeypatch, caplog):
    requests = setup_client(monkeypatch, httpx.Response(200, content=image_bytes()))
    with caplog.at_level(logging.DEBUG):
        assert fetch_snapshot('https://example.test/image?secret=private') == image_bytes()
    assert 'authorization' not in requests[0].headers
    assert 'private' not in caplog.text


@pytest.mark.parametrize('response', [httpx.Response(403), httpx.Response(302, headers={'location':'http://example.test/'}), httpx.Response(200, content=b'not image'), httpx.ReadTimeout('private signed URL')])
def test_safe_rejections(monkeypatch, response):
    setup_client(monkeypatch, response)
    with pytest.raises(SnapshotError) as error:
        fetch_snapshot('https://example.test/?secret=private')
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('headers', [{}, {'content-length':'1'}, {'content-length':'99999999'}])
def test_stream_limit(monkeypatch, headers):
    setup_client(monkeypatch, httpx.Response(200, content=image_bytes(), headers=headers))
    with pytest.raises(SnapshotError): fetch_snapshot('https://example.test/', max_bytes=8)


@pytest.mark.parametrize('url', ['file:///tmp/a', 'http://user:password@example.test/', 'garbage'])
def test_bad_schemes_and_credentials(url):
    with pytest.raises(SnapshotError): fetch_snapshot(url)


def test_truncated_jpeg_is_not_valid_image(monkeypatch):
    out = io.BytesIO()
    Image.new('RGB',(30,30)).save(out,format='JPEG')
    setup_client(monkeypatch,httpx.Response(200,content=out.getvalue()[:-8]))
    with pytest.raises(SnapshotError): fetch_snapshot('https://example.test/')


def test_slow_stream_deadline(monkeypatch):
    from yaic import snapshots
    now = [0.0]
    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'first'
            now[0] = 6
            yield b'last'
    monkeypatch.setattr(snapshots.time,'monotonic',lambda:now[0])
    setup_client(monkeypatch,httpx.Response(200,stream=SlowStream()))
    with pytest.raises(SnapshotError): fetch_snapshot('https://example.test/',timeout=5)
