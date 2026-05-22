"""Async web scraper using httpx + BeautifulSoup."""
import asyncio
import hashlib
import logging
import socket
import ipaddress
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT = 8.0
MAX_CONTENT_CHARS = 2000
BOT_USER_AGENT = "TruthStream-Bot/1.0 (+https://truthstream.app/bot)"

# Private IP ranges for SSRF protection
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return True  # Fail safe


def _validate_url(url: str) -> bool:
    """SSRF protection: validate scheme and resolve to public IP."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        # Resolve hostname
        hostname = parsed.hostname
        if not hostname:
            return False
        try:
            ip = socket.gethostbyname(hostname)
            if _is_private_ip(ip):
                logger.warning("SSRF blocked: %s resolves to private IP %s", url, ip)
                return False
        except socket.gaierror:
            return False
        return True
    except Exception:
        return False


def _extract_text(html: str, url: str) -> str:
    """Extract main article text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")

    # Remove boilerplate elements
    for tag in soup.find_all(["nav", "footer", "header", "aside", "script", "style",
                              "noscript", "iframe", "form", "button", "input"]):
        tag.decompose()

    # Prefer semantic content containers
    for selector in ["article", "main", '[role="main"]', ".article-body",
                     ".post-content", ".entry-content", "#content"]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text[:MAX_CONTENT_CHARS]

    # Fallback: body text
    body = soup.find("body")
    if body:
        return body.get_text(separator=" ", strip=True)[:MAX_CONTENT_CHARS]

    return soup.get_text(separator=" ", strip=True)[:MAX_CONTENT_CHARS]


async def scrape_url(
        url: str,
        redis=None,
        ttl: int = 21600,  # 6 hours
) -> tuple[str, str]:
    """
    Fetch and scrape a URL. Returns (text, fetch_status).
    fetch_status: success|timeout|blocked|empty|ssrf_blocked|error
    Uses Redis to cache results by URL hash.
    """
    if not _validate_url(url):
        return "", "ssrf_blocked"

    # Check Redis cache
    if redis:
        cache_key = f"scrape:{hashlib.md5(url.encode()).hexdigest()}"
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached.decode(), "success"
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(
                timeout=SCRAPE_TIMEOUT,
                headers={"User-Agent": BOT_USER_AGENT},
                follow_redirects=True,
                max_redirects=3,
        ) as client:
            response = await client.get(url)

            if response.status_code in (401, 402, 403):
                return response.text[:500], "blocked"

            if response.status_code >= 400:
                return "", f"http_{response.status_code}"

            content_type = response.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type:
                return "", "non_html"

            text = _extract_text(response.text, url)

            if not text or len(text) < 50:
                return "", "empty"

            # Cache in Redis
            if redis:
                try:
                    await redis.setex(cache_key, ttl, text)
                except Exception:
                    pass

            return text, "success"

    except httpx.TimeoutException:
        return "", "timeout"
    except httpx.RequestError as e:
        logger.warning("Scrape request error for %s: %s", url, e)
        return "", "error"
    except Exception as e:
        logger.error("Scrape unexpected error for %s: %s", url, e)
        return "", "error"


async def fetch_article_url(url: str) -> tuple[str, str]:
    """
    Fetch a full article URL for analysis. Returns (raw_html_text, fetch_status).
    Used for the main article input, not source snippets.
    Applies a longer 10s timeout.
    """
    if not _validate_url(url):
        raise ValueError(f"URL failed SSRF validation: {url}")

    try:
        async with httpx.AsyncClient(
                timeout=10.0,
                headers={"User-Agent": BOT_USER_AGENT},
                follow_redirects=True,
                max_redirects=5,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            # Remove boilerplate
            for tag in soup.find_all(["nav", "footer", "header", "aside",
                                      "script", "style", "noscript"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            return text, "success"

    except httpx.TimeoutException:
        raise TimeoutError(f"Article fetch timed out: {url}")
    except httpx.HTTPStatusError as e:
        raise ValueError(f"HTTP {e.response.status_code} fetching {url}")
