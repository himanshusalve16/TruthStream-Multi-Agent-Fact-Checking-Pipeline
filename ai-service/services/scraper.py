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

SCRAPE_TIMEOUT = 4.0
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


async def _validate_url(url: str) -> bool:
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
            loop = asyncio.get_running_loop()
            ip = await loop.run_in_executor(None, socket.gethostbyname, hostname)
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


def _process_response(response: httpx.Response, url: str) -> tuple[str, str]:
    """
    Shared response-processing logic for both the shared-client and fresh-client paths.
    Returns (text, status).
    """
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

    return text, "success"


async def scrape_url(
        url: str,
        redis=None,
        ttl: int = 21600,  # 6 hours
        http_client: Optional[httpx.AsyncClient] = None,
) -> tuple[str, str]:
    """
    Fetch and scrape a URL. Returns (text, fetch_status).
    fetch_status: success|timeout|blocked|empty|ssrf_blocked|error|non_html|http_NNN

    Fixed: previously the shared http_client path (the common case) missed all
    status-code checks, content-type gating, and Redis caching because they were
    nested inside the 'else' branch. Now all response handling runs on both paths.
    """
    if not await _validate_url(url):
        return "", "ssrf_blocked"

    # Check Redis cache
    cache_key = f"scrape_v2:{hashlib.md5(url.encode()).hexdigest()}"
    if redis:
        try:
            cached_raw = await redis.get(cache_key)
            if cached_raw:
                import json
                cached = json.loads(cached_raw.decode())
                logger.debug("Scrape cache hit: %s", url)
                return cached.get("text", ""), cached.get("status", "success")
        except Exception:
            pass

    text = ""
    status = "error"

    try:
        if http_client is not None:
            response = await http_client.get(url, timeout=SCRAPE_TIMEOUT)
        else:
            async with httpx.AsyncClient(
                    timeout=SCRAPE_TIMEOUT,
                    headers={"User-Agent": BOT_USER_AGENT},
                    follow_redirects=True,
                    max_redirects=3,
            ) as client:
                response = await client.get(url)

        # ── Unified response processing (runs for both client paths) ──────────
        if response.status_code in (401, 402, 403):
            text, status = response.text[:500], "blocked"
        elif response.status_code >= 400:
            text, status = "", f"http_{response.status_code}"
        else:
            content_type = response.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type:
                text, status = "", "non_html"
            else:
                loop = asyncio.get_running_loop()
                extracted = await loop.run_in_executor(None, _extract_text, response.text, url)
                if not extracted or len(extracted) < 50:
                    text, status = "", "empty"
                else:
                    text, status = extracted, "success"
        # ── End unified processing ─────────────────────────────────────────────

        logger.debug("Scrape %s → status=%s len=%d", url, status, len(text))

    except httpx.TimeoutException:
        status = "timeout"
        logger.warning("Scrape timeout: %s", url)
    except httpx.RequestError as e:
        logger.warning("Scrape request error for %s: %s", url, e)
        status = "error"
    except Exception as e:
        logger.error("Scrape unexpected error for %s: %s", url, e)
        status = "error"

    # Cache outcome in Redis (success: 6h, failure: 1h to avoid hammering dead URLs)
    if redis:
        try:
            import json
            cache_ttl = ttl if status == "success" else 3600
            await redis.setex(cache_key, cache_ttl, json.dumps({
                "text": text,
                "status": status
            }))
        except Exception:
            pass

    return text, status


def _parse_and_clean_article(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["nav", "footer", "header", "aside",
                              "script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


async def _fetch_article_url_once(url: str, http_client: Optional[httpx.AsyncClient] = None) -> tuple[str, str]:
    """Single attempt to fetch article text."""
    if http_client is not None:
        response = await http_client.get(url, timeout=5.0)
        response.raise_for_status()
    else:
        async with httpx.AsyncClient(
                timeout=5.0,  # Cap timeout to 5.0 seconds
                headers={"User-Agent": BOT_USER_AGENT},
                follow_redirects=True,
                max_redirects=3,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(None, _parse_and_clean_article, response.text)
    return text, "success"


async def fetch_article_url(url: str, http_client: Optional[httpx.AsyncClient] = None) -> tuple[str, str]:
    """
    Fetch a full article URL for analysis with bounded, rapid retries.
    Returns (raw_html_text, fetch_status).
    """
    if not await _validate_url(url):
        raise ValueError(f"URL failed SSRF validation: {url}")

    last_error: Exception | None = None

    for attempt in range(2):  # Max 2 attempts total
        try:
            return await _fetch_article_url_once(url, http_client)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = TimeoutError(f"Article fetch timed out or network error: {url}")
            logger.warning("Article fetch attempt %d failed for %s: %s", attempt + 1, url, e)
        except httpx.HTTPStatusError as e:
            last_error = ValueError(f"HTTP {e.response.status_code} fetching {url}")
            logger.warning("Article fetch attempt %d HTTP error for %s: %s", attempt + 1, url, e)
            # Skip retry on standard client errors (400-499) except request timeout (408)
            if e.response.status_code < 500 and e.response.status_code != 408:
                break
        except Exception as e:
            last_error = e
            logger.warning("Article fetch attempt %d failed for %s: %s", attempt + 1, url, e)
            break

        if attempt < 1:
            await asyncio.sleep(1.0)  # Wait only 1 second before retry

    if isinstance(last_error, TimeoutError):
        raise last_error
    if isinstance(last_error, ValueError):
        raise last_error
    raise ValueError(f"Could not fetch article: {last_error or 'Unknown error'}")
