"""Tests for the Crawler. All HTTP is mocked via the `responses` library."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import requests
import responses

from src.crawler import Crawler

BASE = "https://quotes.toscrape.com/"


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@responses.activate
def test_fetch_returns_html(cache_dir: Path) -> None:
    responses.add(responses.GET, BASE, body="<html>hello</html>", status=200)
    crawler = Crawler(cache_dir=cache_dir, delay=0)

    assert "hello" in crawler.fetch(BASE)
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_uses_cache_on_second_call(cache_dir: Path) -> None:
    responses.add(responses.GET, BASE, body="<html>once</html>", status=200)
    crawler = Crawler(cache_dir=cache_dir, delay=0)

    crawler.fetch(BASE)
    crawler.fetch(BASE)

    assert len(responses.calls) == 1, "second fetch should hit the cache"


@responses.activate
def test_fetch_bypasses_cache_when_disabled(cache_dir: Path) -> None:
    responses.add(responses.GET, BASE, body="<html>1</html>", status=200)
    responses.add(responses.GET, BASE, body="<html>2</html>", status=200)
    crawler = Crawler(cache_dir=cache_dir, delay=0, use_cache=False)

    crawler.fetch(BASE)
    crawler.fetch(BASE)

    assert len(responses.calls) == 2


@responses.activate
def test_fetch_retries_on_server_error(cache_dir: Path) -> None:
    responses.add(responses.GET, BASE, status=500)
    responses.add(responses.GET, BASE, status=500)
    responses.add(responses.GET, BASE, body="<html>ok</html>", status=200)
    crawler = Crawler(cache_dir=cache_dir, delay=0, max_retries=3)

    assert "ok" in crawler.fetch(BASE)
    assert len(responses.calls) == 3


@responses.activate
def test_fetch_raises_after_max_retries(cache_dir: Path) -> None:
    for _ in range(3):
        responses.add(responses.GET, BASE, status=500)
    crawler = Crawler(cache_dir=cache_dir, delay=0, max_retries=3)

    with pytest.raises(requests.HTTPError):
        crawler.fetch(BASE)


@responses.activate
def test_fetch_does_not_retry_404(cache_dir: Path) -> None:
    responses.add(responses.GET, BASE, status=404)
    crawler = Crawler(cache_dir=cache_dir, delay=0, max_retries=3)

    with pytest.raises(requests.HTTPError):
        crawler.fetch(BASE)
    assert len(responses.calls) == 1, "client errors must not be retried"


@responses.activate
def test_fetch_respects_politeness_window(cache_dir: Path) -> None:
    responses.add(responses.GET, BASE + "page/1/", body="<html>1</html>", status=200)
    responses.add(responses.GET, BASE + "page/2/", body="<html>2</html>", status=200)
    crawler = Crawler(cache_dir=cache_dir, delay=0.3)

    start = time.monotonic()
    crawler.fetch(BASE + "page/1/")
    crawler.fetch(BASE + "page/2/")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.3


def test_in_scope_accepts_paginated_and_author_pages(cache_dir: Path) -> None:
    crawler = Crawler(cache_dir=cache_dir, delay=0)
    assert crawler._in_scope("https://quotes.toscrape.com/")
    assert crawler._in_scope("https://quotes.toscrape.com/page/3/")
    assert crawler._in_scope("https://quotes.toscrape.com/author/Albert-Einstein/")


def test_in_scope_rejects_other_paths_and_hosts(cache_dir: Path) -> None:
    crawler = Crawler(cache_dir=cache_dir, delay=0)
    assert not crawler._in_scope("https://quotes.toscrape.com/tag/love/")
    assert not crawler._in_scope("https://quotes.toscrape.com/login")
    assert not crawler._in_scope("https://example.com/page/1/")


@responses.activate
def test_crawl_follows_in_scope_links_only(cache_dir: Path) -> None:
    home = """
    <html><body>
      <a href="/page/2/">next</a>
      <a href="/author/Some-Author/">author</a>
      <a href="/tag/love/">tag (out of scope)</a>
      <a href="https://external.example.com/">external</a>
    </body></html>
    """
    page2 = "<html><body><a href='/'>home</a></body></html>"
    author = "<html><body>About the author</body></html>"

    responses.add(responses.GET, BASE, body=home, status=200)
    responses.add(responses.GET, BASE + "page/2/", body=page2, status=200)
    responses.add(responses.GET, BASE + "author/Some-Author/", body=author, status=200)

    crawler = Crawler(cache_dir=cache_dir, delay=0)
    pages = crawler.crawl()

    assert set(pages) == {
        BASE,
        BASE + "page/2/",
        BASE + "author/Some-Author/",
    }


@responses.activate
def test_crawl_continues_when_a_page_fails(cache_dir: Path) -> None:
    home = '<html><body><a href="/page/2/">next</a></body></html>'
    responses.add(responses.GET, BASE, body=home, status=200)
    responses.add(responses.GET, BASE + "page/2/", status=404)

    crawler = Crawler(cache_dir=cache_dir, delay=0, max_retries=1)
    pages = crawler.crawl()

    assert BASE in pages
    assert BASE + "page/2/" not in pages


@responses.activate
def test_crawl_deduplicates_links(cache_dir: Path) -> None:
    home = """
    <html><body>
      <a href="/page/2/">a</a>
      <a href="/page/2/">b</a>
      <a href="/page/2/#fragment">c</a>
    </body></html>
    """
    responses.add(responses.GET, BASE, body=home, status=200)
    responses.add(responses.GET, BASE + "page/2/", body="<html></html>", status=200)

    crawler = Crawler(cache_dir=cache_dir, delay=0)
    crawler.crawl()

    page2_calls = [c for c in responses.calls if "page/2" in c.request.url]
    assert len(page2_calls) == 1