"""Pure-Python verdict computation (no LLM dependency)."""
from typing import Dict, List

from models.schemas import (
    BiasResult,
    ClaimSchema,
    ClaimSourcesResult,
    ClaimVerdictSchema,
    JudgeResult,
)


def compute_fallback_verdict(
        claims: List[ClaimSchema],
        sources_by_claim: Dict[str, ClaimSourcesResult],
        bias_result: BiasResult,
) -> JudgeResult:
    """
    Fallback verdict when the judge LLM is unavailable.
    Uses weighted source stance scoring (blueprint section 11.2).
    """
    claim_verdicts = []

    for claim in claims:
        cid = claim.claim_id or ""
        result = sources_by_claim.get(cid)
        sources = result.sources if result else []

        support_w = sum(s.quality_score or 0 for s in sources if s.stance == "SUPPORTS")
        refute_w = sum(s.quality_score or 0 for s in sources if s.stance == "REFUTES")
        total_w = support_w + refute_w

        if total_w == 0:
            verdict = "UNVERIFIABLE"
            confidence = 0.1
        elif abs(support_w - refute_w) / total_w < 0.2:
            verdict = "CONTESTED"
            confidence = 0.5
        elif support_w > refute_w:
            verdict = "SUPPORTED"
            confidence = support_w / total_w
        else:
            verdict = "REFUTED"
            confidence = refute_w / total_w

        if bias_result.bias_score > 70:
            confidence = max(0.05, confidence - 0.1)

        claim_verdicts.append(ClaimVerdictSchema(
            claim_id=cid,
            verdict=verdict,
            confidence=round(confidence, 3),
            reasoning="Computed from weighted source stance scores.",
            key_source_indices=[],
        ))

    supported = sum(1 for v in claim_verdicts if v.verdict == "SUPPORTED")
    refuted = sum(1 for v in claim_verdicts if v.verdict == "REFUTED")
    total = len(claim_verdicts)

    if total == 0:
        overall = "UNVERIFIABLE"
        overall_conf = 0.1
    elif supported / total > 0.7:
        overall = "MOSTLY_TRUE"
        overall_conf = 0.6
    elif refuted / total > 0.7:
        overall = "MOSTLY_FALSE"
        overall_conf = 0.6
    else:
        overall = "MIXTURE"
        overall_conf = 0.4

    return JudgeResult(
        overall_verdict=overall,
        overall_confidence=overall_conf,
        overall_summary="Verdict computed from weighted evidence scores. Manual review recommended.",
        claim_verdicts=claim_verdicts,
    )
