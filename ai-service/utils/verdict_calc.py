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
    Fallback verdict calculation when the judge LLM is unavailable.
    Uses the mathematically grounded consensus and grounding confidence model:
    C_final = (w_agreement * A + w_credibility * Q + w_freshness * F) * G * (1 - P_b) * (1 - P_c)
    """
    import re
    claim_verdicts = []

    for claim in claims:
        cid = claim.claim_id or ""
        result = sources_by_claim.get(cid)
        sources = result.sources if result else []

        # Filter out neutral/unclear sources for weighted calculation
        supports = [s for s in sources if s.stance == "SUPPORTS"]
        refutes = [s for s in sources if s.stance == "REFUTES"]
        
        support_w = sum(s.quality_score or 0.0 for s in supports)
        refute_w = sum(s.quality_score or 0.0 for s in refutes)
        total_w = support_w + refute_w

        if len(sources) == 0:
            verdict = "UNVERIFIABLE"
            confidence = 0.0
            reasoning = "No source evidence was retrieved to cross-reference."
        else:
            # 1. Stance Agreement Score (A)
            # A = |S - R| / (S + R + N + 0.1)
            num_s = len(supports)
            num_r = len(refutes)
            num_n = len([s for s in sources if s.stance in ("NEUTRAL", "UNCLEAR")])
            agreement = abs(num_s - num_r) / (num_s + num_r + num_n + 0.1)

            # 2. Source Quality/Credibility (Q)
            avg_quality = sum(s.quality_score or 0.0 for s in sources) / len(sources) if len(sources) > 0 else 0.0

            # 3. Grounding Quality (G) via word overlap between claim and snippets
            claim_words = set(re.findall(r'\w+', claim.text.lower()))
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
            claim_words = claim_words - stop_words
            
            max_grounding = 0.0
            for s in sources:
                snippet_text = (s.snippet or "").lower()
                snippet_words = set(re.findall(r'\w+', snippet_text))
                overlap = len(claim_words.intersection(snippet_words))
                g_score = overlap / len(claim_words) if len(claim_words) > 0 else 0.0
                if g_score > max_grounding:
                    max_grounding = g_score
            grounding = max(0.1, min(1.0, max_grounding)) # clamp to min 0.1

            # Weight parameters
            w_a, w_q, w_f = 0.5, 0.4, 0.1
            freshness = 1.0 # default baseline freshness

            # Base Confidence
            base_conf = (w_a * agreement + w_q * avg_quality + w_f * freshness) * grounding

            # 4. Bias Penalty (P_b)
            bias_val = bias_result.bias_score if bias_result else 50
            p_bias = 0.2 * ((bias_val - 50) / 50.0) if bias_val > 50 else 0.0

            # 5. Contradiction Penalty (P_c)
            p_contradiction = 0.0
            if num_s > 0 and num_r > 0:
                diff_ratio = abs(num_s - num_r) / (num_s + num_r)
                if diff_ratio < 0.2:
                    p_contradiction = 0.3

            # Apply final formula
            confidence = base_conf * (1.0 - p_bias) * (1.0 - p_contradiction)
            confidence = max(0.0, min(1.0, confidence))

            # Determine Verdict
            if num_s == 0 and num_r == 0:
                verdict = "UNVERIFIABLE"
                reasoning = "Retrieved sources were neutral or unclear."
            elif p_contradiction > 0.0:
                verdict = "CONTESTED"
                reasoning = "Retrieved sources contain highly conflicting stances."
            elif support_w > refute_w:
                verdict = "SUPPORTED"
                reasoning = "Majority of credible sources support the claim."
            else:
                verdict = "REFUTED"
                reasoning = "Majority of credible sources refute the claim."

        claim_verdicts.append(ClaimVerdictSchema(
            claim_id=cid,
            verdict=verdict,
            confidence=round(confidence, 3),
            reasoning=reasoning,
            key_source_indices=[],
        ))

    supported = sum(1 for v in claim_verdicts if v.verdict == "SUPPORTED")
    refuted = sum(1 for v in claim_verdicts if v.verdict == "REFUTED")
    unverifiable = sum(1 for v in claim_verdicts if v.verdict == "UNVERIFIABLE")
    total = len(claim_verdicts)

    if total == 0 or unverifiable == total:
        overall = "UNVERIFIABLE"
        overall_conf = 0.0
    elif supported / total > 0.7:
        overall = "MOSTLY_TRUE"
        overall_conf = 0.7
    elif refuted / total > 0.7:
        overall = "MOSTLY_FALSE"
        overall_conf = 0.7
    else:
        overall = "MIXTURE"
        overall_conf = 0.4

    return JudgeResult(
        overall_verdict=overall,
        overall_confidence=round(overall_conf, 2),
        overall_summary="Verdict computed from weighted consensus and grounding scores. Manual review recommended.",
        claim_verdicts=claim_verdicts,
    )

