"""Unit tests for source quality scoring heuristics."""
from utils.quality import score_source, is_paywalled, TRUSTED_DOMAINS, LOW_QUALITY_DOMAINS


def test_trusted_domain_scores_high():
    score = score_source(
        domain="reuters.com",
        url="https://reuters.com/article",
        snippet="A" * 120,
        fetch_status="success",
        search_rank=1,
    )
    assert score >= 0.6


def test_low_quality_domain_penalty():
    domain = next(iter(LOW_QUALITY_DOMAINS))
    score = score_source(
        domain=domain,
        url=f"https://{domain}/x",
        snippet="short",
        fetch_status="success",
        search_rank=5,
    )
    assert score < 0.5


def test_paywall_detection():
    assert is_paywalled(snippet="Subscribe to read this article") is True
    assert is_paywalled(snippet="Open access article text") is False


def test_trusted_domains_set_not_empty():
    assert "reuters.com" in TRUSTED_DOMAINS
    assert len(LOW_QUALITY_DOMAINS) > 0
