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


@pytest.mark.asyncio
async def test_search_web_falls_back_to_bing_when_ddg_empty(monkeypatch):
    """When both SerpAPI and DDG return nothing, Bing is tried as last resort."""
    monkeypatch.setattr(search_module.settings, "serpapi_key", "replace-me")

    bing_results = [{"url": "https://bing-result.com/news", "title": "Bing news", "snippet": "bing snippet", "rank": 1}]
    with patch.object(search_module, "_search_duckduckgo", new_callable=AsyncMock, return_value=[]):
        with patch.object(search_module, "_search_bing", new_callable=AsyncMock, return_value=bing_results) as bing:
            out = await search_module.search_web("niche claim with no ddg results")

    assert len(out) == 1
    assert out[0]["url"] == "https://bing-result.com/news"
    bing.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_web_with_fallback_returns_primary_when_enough_results(monkeypatch):
    """If primary query returns >= min_primary_results, fallback is NOT tried."""
    monkeypatch.setattr(search_module.settings, "serpapi_key", "replace-me")

    primary_results = [
        {"url": f"https://r{i}.com", "title": f"T{i}", "snippet": f"S{i}", "rank": i}
        for i in range(5)
    ]
    with patch.object(search_module, "_search_duckduckgo", new_callable=AsyncMock, return_value=primary_results) as ddg:
        results, query_used = await search_module.search_web_with_fallback(
            primary_query="specific claim",
            fallback_query="broad topic",
            max_results=10,
            min_primary_results=3,
        )

    # Only called once — for the primary query
    assert ddg.call_count == 1
    assert len(results) == 5


@pytest.mark.asyncio
async def test_search_web_with_fallback_merges_when_primary_insufficient(monkeypatch):
    """If primary < min_primary_results, fallback is tried and unique results merged."""
    monkeypatch.setattr(search_module.settings, "serpapi_key", "replace-me")

    primary = [{"url": "https://a.com", "title": "A", "snippet": "S", "rank": 1}]
    fallback = [
        {"url": "https://b.com", "title": "B", "snippet": "S2", "rank": 1},
        {"url": "https://a.com", "title": "A dup", "snippet": "S", "rank": 2},  # duplicate — should not be added
    ]

    call_count = {"n": 0}

    async def fake_search(query, max_results=10, redis=None, http_client=None):
        call_count["n"] += 1
        return primary if call_count["n"] == 1 else fallback

    with patch.object(search_module, "search_web", new=fake_search):
        results, query_used = await search_module.search_web_with_fallback(
            primary_query="very specific narrow claim",
            fallback_query="broad fallback",
            min_primary_results=3,
        )

    urls = {r["url"] for r in results}
    assert "https://a.com" in urls
    assert "https://b.com" in urls
    assert len(results) == 2  # a.com duplicate from fallback not added


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


def test_build_claim_query_does_not_use_site_operators():
    """The new query builder should not add site-restricted operators."""
    q = search_module.build_claim_query(
        "The government spent $4 billion on renewable energy last year",
        claim_type="statistic"
    )
    assert "site:" not in q
    assert "fact check" not in q
    assert any(word in q.lower() for word in ["billion", "renewable", "energy"])


def test_build_fallback_query_returns_short_entity_query():
    q = search_module.build_fallback_query(
        "Prime Minister Narendra Modi announced a new economic policy at the G20 summit in New Delhi"
    )
    # Should be short and entity-based
    assert len(q.split()) <= 7
    assert any(word in q for word in ["Prime", "Minister", "Narendra", "Modi", "G20", "Delhi"])


def test_rank_snippets_by_overlap():
    from agents.source_finder import rank_snippets_by_overlap
    claim = "The energy efficiency increased by fifteen percent"
    results = [
        {"url": "https://a.com", "title": "Random title", "snippet": "Unrelated snippet details about weather.", "rank": 1},
        {"url": "https://b.com", "title": "Energy efficiency metrics", "snippet": "New reports show energy efficiency increased by 15 percent over the last decade.", "rank": 2},
    ]
    ranked = rank_snippets_by_overlap(claim, results)

    assert len(ranked) == 2
    assert ranked[0]["url"] == "https://b.com"
    assert ranked[1]["url"] == "https://a.com"
