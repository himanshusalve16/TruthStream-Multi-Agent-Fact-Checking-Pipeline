"""Unit tests for judge fallback confidence logic."""
from utils.verdict_calc import compute_fallback_verdict
from models.schemas import ClaimSchema, ClaimSourcesResult, SourceSchema, BiasResult


def test_fallback_unverifiable_without_sources():
    claim = ClaimSchema(text="Test claim", claim_id="c1")
    bias = BiasResult(
        bias_score=30,
        bias_direction="neutral",
        framing_flags=[],
        loaded_terms=[],
        summary="Neutral",
    )
    result = compute_fallback_verdict([claim], {}, bias)
    assert result.claim_verdicts[0].verdict == "UNVERIFIABLE"
    assert result.claim_verdicts[0].confidence == 0.1


def test_fallback_supported_when_sources_support():
    claim = ClaimSchema(text="GDP grew 3%", claim_id="c1")
    sources = ClaimSourcesResult(
        claim_id="c1",
        sources=[
            SourceSchema(
                url="https://reuters.com/x",
                title="Report",
                domain="reuters.com",
                snippet="GDP grew 3% according to data",
                stance="SUPPORTS",
                quality_score=0.9,
                fetch_status="success",
            )
        ],
    )
    bias = BiasResult(
        bias_score=40,
        bias_direction="neutral",
        framing_flags=[],
        loaded_terms=[],
        summary="Low bias",
    )
    result = compute_fallback_verdict([claim], {"c1": sources}, bias)
    assert result.claim_verdicts[0].verdict == "SUPPORTED"
    assert result.claim_verdicts[0].confidence > 0.5
