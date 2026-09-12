from __future__ import annotations

import subprocess
import threading
import time

import requests
from requests.adapters import HTTPAdapter

from wuxing.domain.errors import FetchError


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class RequestsHttpClient:
    def __init__(self):
        self._cache: dict[str, str] = {}
        self._lock = threading.RLock()
        self._local = threading.local()

    @staticmethod
    def create_session() -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = self.create_session()
            self._local.session = session
        return session

    def fetch_text(self, url: str, timeout: int) -> str:
        with self._lock:
            cached = self._cache.get(url)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        session = self._session()
        for attempt in range(3):
            try:
                response = session.get(url, timeout=timeout, verify=True)
                if response.status_code in {502, 503, 504}:
                    raise requests.HTTPError(
                        f"HTTP {response.status_code}: Bad Gateway", response=response
                    )
                response.raise_for_status()
                text = self._decode_response(response)
                with self._lock:
                    self._cache[url] = text
                return text
            except Exception as exc:
                last_error = exc
                if self._should_use_curl(exc):
                    try:
                        text = self._fetch_with_curl(url, timeout)
                        with self._lock:
                            self._cache[url] = text
                        return text
                    except Exception as curl_error:
                        last_error = curl_error
                        break
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        raise FetchError(f"HTTP抓取失败：{type(last_error).__name__}: {last_error}") from last_error

    @staticmethod
    def _decode_response(response: requests.Response) -> str:
        raw = response.content
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig", errors="ignore")
        encoding = response.apparent_encoding or response.encoding or "utf-8"
        return raw.decode(encoding, errors="ignore")

    @staticmethod
    def _should_use_curl(error: Exception) -> bool:
        value = f"{type(error).__name__}: {error}".lower()
        return any(marker in value for marker in (
            "ssl", "tls", "handshake", "certificate", "connection aborted",
            "filenotfounderror", "no such file or directory", "wrong version number",
        ))

    @staticmethod
    def _fetch_with_curl(url: str, timeout: int) -> str:
        command = [
            "curl.exe",
            "-L",
            "-k",
            "--ssl-no-revoke",
            "--http1.1",
            "--compressed",
            "--connect-timeout",
            str(max(3, min(timeout, 10))),
            "--max-time",
            str(max(5, timeout)),
            "-A",
            DEFAULT_HEADERS["User-Agent"],
            url,
        ]
        completed = subprocess.run(command, capture_output=True, timeout=max(8, timeout + 3))
        if completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="ignore").strip()
            raise FetchError(f"curl exit {completed.returncode}: {message}")
        return completed.stdout.decode("utf-8", errors="ignore")
