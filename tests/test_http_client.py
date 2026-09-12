from wuxing.sources.http import RequestsHttpClient


class _Response:
    status_code = 200
    content = b"ok"
    apparent_encoding = "utf-8"
    encoding = "utf-8"

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self):
        self.headers = {}
        self.urls = []

    def mount(self, *_args):
        return None

    def get(self, url, **_kwargs):
        self.urls.append(url)
        return _Response()


def test_http_client_reuses_session_for_multiple_urls(monkeypatch):
    created = []

    def create_session():
        session = _Session()
        created.append(session)
        return session

    monkeypatch.setattr(RequestsHttpClient, "create_session", staticmethod(create_session))
    client = RequestsHttpClient()

    assert client.fetch_text("https://example.test/one", 5) == "ok"
    assert client.fetch_text("https://example.test/two", 5) == "ok"
    assert len(created) == 1
    assert created[0].urls == [
        "https://example.test/one",
        "https://example.test/two",
    ]
