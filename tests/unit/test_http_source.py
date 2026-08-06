import warnings
import unittest
from unittest.mock import patch

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from wuxing.sources.http import RequestsHttpClient


class _Response:
    status_code = 200
    content = b"ok"
    apparent_encoding = None
    encoding = "utf-8"

    @staticmethod
    def raise_for_status():
        return None


class _Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        if kwargs["verify"] is False:
            warnings.warn("certificate check bypassed", InsecureRequestWarning)
        return self.response


class RequestsHttpClientTlsTests(unittest.TestCase):
    def test_requests_verify_certificates_without_emitting_insecure_warning(self):
        session = _Session(response=_Response())
        client = RequestsHttpClient()

        with patch.object(client, "create_session", return_value=session):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", InsecureRequestWarning)
                self.assertEqual(client.fetch_text("https://127.0.0.1/test", 5), "ok")

        self.assertTrue(session.calls[0][1]["verify"])
        self.assertEqual(caught, [])

    def test_certificate_failure_keeps_curl_fallback(self):
        session = _Session(error=requests.exceptions.SSLError("certificate verify failed"))
        client = RequestsHttpClient()

        with patch.object(client, "create_session", return_value=session):
            with patch.object(client, "_fetch_with_curl", return_value="curl text") as fallback:
                self.assertEqual(client.fetch_text("https://127.0.0.1/test", 5), "curl text")

        self.assertTrue(session.calls[0][1]["verify"])
        fallback.assert_called_once_with("https://127.0.0.1/test", 5)


if __name__ == "__main__":
    unittest.main()
