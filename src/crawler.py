"""Polite web crawler with on-disk HTML caching and retries."""

from __future__ import annotations

import hashlib
import logging
import time
from collections import deque
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "COMP3011-CW2-SearchEngine/1.0 "
    "(University of Leeds coursework; educational use)"
)


class Crawler:
    """Breadth-first crawler restricted to a single host.

    Enforces a configurable politeness delay between successive live HTTP
    requests, retries transient (5xx, connection, timeout) failures with
    exponential backoff, and persists every successfully fetched page to
    a local cache directory so subsequent runs can rebuild the index
    without re-crawling.

    Args:
        base_url:    Root URL of the target site. Out-of-host links are
                     never followed.
        delay:       Minimum seconds between live HTTP requests. Defaults
                     to 6.0 to satisfy the coursework politeness window.
        cache_dir:   Directory in which to store fetched HTML.
        user_agent:  Value of the User-Agent header.
        max_retries: Number of attempts for transient failures.
        timeout:     Per-request timeout in seconds.
        use_cache:   If False, every fetch goes to the network.
    """

    def __init__(
        self,
        base_url: str = "https://quotes.toscrape.com/",
        delay: float = 6.0,
        cache_dir: str | Path = "cache",
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = 3,
        timeout: float = 10.0,
        use_cache: bool = True,
    ) -> None:
        self.base_url = base_url
        self.delay = delay
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.timeout = timeout
        self.use_cache = use_cache

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._last_request_time: float = 0.0
        self._base_host = urlparse(base_url).netloc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def crawl(self, seed: Optional[str] = None) -> dict[str, str]:
        """Crawl from ``seed`` (or ``base_url``) and return ``{url: html}``."""
        start = self._normalise(seed or self.base_url)
        frontier: deque[str] = deque([start])
        queued: set[str] = {start}
        visited: set[str] = set()
        pages: dict[str, str] = {}

        while frontier:
            url = frontier.popleft()
            if url in visited:
                continue
            visited.add(url)

            try:
                html = self.fetch(url)
            except requests.RequestException as exc:
                logger.warning("Skipping %s: %s", url, exc)
                continue

            pages[url] = html

            for link in self._extract_links(url, html):
                if link in queued or not self._in_scope(link):
                    continue
                queued.add(link)
                frontier.append(link)

        logger.info("Crawl complete: %d pages", len(pages))
        return pages

    def fetch(self, url: str) -> str:
        """Return the HTML body of ``url``, hitting the cache first."""
        url = self._normalise(url)

        if self.use_cache:
            cached = self._cache_read(url)
            if cached is not None:
                logger.debug("CACHE HIT  %s", url)
                return cached

        html = self._fetch_with_retries(url)
        self._cache_write(url, html)
        return html

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _fetch_with_retries(self, url: str) -> str:
        backoff = 1.0
        last_exc: Optional[BaseException] = None

        for attempt in range(1, self.max_retries + 1):
            self._wait_for_politeness()
            try:
                logger.info("GET %s (attempt %d/%d)", url, attempt, self.max_retries)
                resp = self._session.get(url, timeout=self.timeout)
                self._last_request_time = time.monotonic()

                if 500 <= resp.status_code < 600:
                    raise requests.HTTPError(
                        f"server error {resp.status_code} for {url}",
                        response=resp,
                    )
                resp.raise_for_status()
                return resp.text

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                logger.warning("Attempt %d failed for %s: %s", attempt, url, exc)
            except requests.HTTPError as exc:
                # Don't retry 4xx — the page genuinely doesn't exist or is
                # forbidden. Only 5xx and network errors are transient.
                if exc.response is not None and 400 <= exc.response.status_code < 500:
                    raise
                last_exc = exc
                logger.warning("Attempt %d failed for %s: %s", attempt, url, exc)

            if attempt < self.max_retries:
                time.sleep(backoff)
                backoff *= 2

        assert last_exc is not None
        raise last_exc

    def _wait_for_politeness(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        wait = self.delay - elapsed
        if wait > 0:
            logger.debug("Sleeping %.2fs for politeness", wait)
            time.sleep(wait)

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{digest}.html"

    def _cache_read(self, url: str) -> Optional[str]:
        path = self._cache_path(url)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _cache_write(self, url: str, html: str) -> None:
        self._cache_path(url).write_text(html, encoding="utf-8")

    # ------------------------------------------------------------------
    # URL handling
    # ------------------------------------------------------------------
    def _normalise(self, url: str) -> str:
        absolute = urljoin(self.base_url, url)
        defragged, _ = urldefrag(absolute)
        return defragged

    def _in_scope(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc != self._base_host:
            return False
        path = parsed.path
        if path in ("", "/"):
            return True
        if path.startswith("/page/"):
            return True
        if path.startswith("/author/"):
            return True
        return False

    def _extract_links(self, page_url: str, html: str) -> Iterator[str]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("a", href=True):
            yield self._normalise(urljoin(page_url, tag["href"]))