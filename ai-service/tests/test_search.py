"""Tests for search provider selection and DuckDuckGo parsing."""
from unittest.mock import AsyncMock, patch

import pytest

from services import search as search_module


@pytest.mark.asyncio
async def test_search_web_uses_duckduckgo_when_serpapi_not_configured(monkeypatch):
    monkeypatch.setattr(search_module.settings, "serpapi_key", "replace-me")

    fake_results = [
        {"url": "https://example.com/a", "title": "A", "snippet": "snippet a", "rank": 1},
    ]
    with patch.object(search_module, "_search_duckduckgo", new_callable=AsyncMock, return_value=fake_results) as ddg:
        out = await search_module.search_web("test query", max_results=5)

    assert out == fake_results
    ddg.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_web_falls_back_to_duckduckgo_when_serpapi_empty(monkeypatch):
    monkeypatch.setattr(search_module.settings, "serpapi_key", "real-key")

    with patch.object(search_module, "_search_serpapi", new_callable=AsyncMock, return_value=[]):
        with patch.object(
            search_module,
            "_search_duckduckgo",
            new_callable=AsyncMock,
            return_value=[{"url": "https://x.com", "title": "T", "snippet": "S", "rank": 1}],
        ) as ddg:
            out = await search_module.search_web("claim text")

    assert len(out) == 1
    ddg.assert_awaited_once()


def test_normalize_ddg_redirect_url():
    redirect = (
        "https://duckduckgo.com/l/?uddg="
        "https%3A%2F%2Freuters.com%2Farticle&rut=abc"
    )
    assert search_module._normalize_ddg_url(redirect) == "https://reuters.com/article"


@pytest.mark.asyncio
async def test_duckduckgo_parses_html_results():
    html = """
    <html><body>
      <div class="result">
        <a class="result__a" href="https://example.com/news">Example headline</a>
        <a class="result__snippet">Short summary text.</a>
      </div>
    </body></html>
    """
    mock_response = type("R", (), {"status_code": 200, "text": html})()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await search_module._search_duckduckgo("test query", 5)

    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/news"
    assert results[0]["title"] == "Example headline"
    assert "summary" in results[0]["snippet"]


def test_rank_snippets_by_overlap():
    from agents.source_finder import rank_snippets_by_overlap
    claim = "The energy efficiency increased by fifteen percent"
    results = [
        {"url": "https://a.com", "title": "Random title", "snippet": "Unrelated snippet details about weather.", "rank": 1},
        {"url": "https://b.com", "title": "Energy efficiency metrics", "snippet": "New reports show energy efficiency increased by 15 percent over the last decade.", "rank": 2},
    ]
    ranked = rank_snippets_by_overlap(claim, results)
    
    assert len(ranked) == 2
    # The snippet with "energy efficiency" and "increased" should rank first (rank 2 results first)
    assert ranked[0]["url"] == "https://b.com"
    assert ranked[1]["url"] == "https://a.com"

