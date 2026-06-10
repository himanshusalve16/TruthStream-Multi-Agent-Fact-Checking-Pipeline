"""Judge Agent — synthesizes claims, sources, and bias into final verdicts."""
import json
import logging
from typing import List, Dict

from google import genai
from google.genai import types
from models.schemas import (
    ClaimSchema, ClaimSourcesResult, BiasResult,
    JudgeResult, ClaimVerdictSchema
)
from services.gemini import execute_gemini_call
from config import settings
from utils.verdict_calc import compute_fallback_verdict

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior fact-checking editor. Your job is to synthesize evidence \
and produce final verdicts.

For each claim, you are given:
- The claim text
- A list of sources with stance (SUPPORTS/REFUTES/NEUTRAL/UNCLEAR) and quality_score (0.0-1.0)
- A bias report on the original article

Rules for claim verdicts (STRICT EVIDENCE REQUIREMENT):
- SUPPORTED: majority of quality external sources (quality_score > 0.6) support. MUST NOT be used if no sources are provided.
- REFUTED: majority of quality external sources refute. MUST NOT be used if no sources are provided.
- CONTESTED: external sources split between support and refutation. MUST NOT be used if no sources are provided.
- UNVERIFIABLE: no usable external sources, or 0 sources were provided. This is the mandatory fallback for un-sourced claims.

Rules for overall verdict:
- MOSTLY_TRUE: >70% of checkable claims are SUPPORTED.
- MIXTURE: mixed results, no clear majority.
- MOSTLY_FALSE: >70% of checkable claims are REFUTED.
- UNVERIFIABLE: insufficient evidence to reach a verdict, or all claims are UNVERIFIABLE.

Apply a confidence penalty of up to 0.15 if article bias_score > 70.

Think step by step before producing JSON. Use a "reasoning" field for each claim verdict.

Output JSON only using this schema:
{
  "overall_verdict": "MOSTLY_TRUE|MIXTURE|MOSTLY_FALSE|UNVERIFIABLE",
  "overall_confidence": float (0.0-1.0),
  "overall_summary": "string (3-5 sentences)",
  "claim_verdicts": [
    {
      "claim_id": "string",
      "verdict": "SUPPORTED|REFUTED|CONTESTED|UNVERIFIABLE",
      "confidence": float (0.0-1.0),
      "reasoning": "string",
      "key_source_indices": [integer]
    }
  ]
}"""


async def run_judge(
        claims: List[ClaimSchema],
        sources_by_claim: Dict[str, ClaimSourcesResult],
        bias_result: BiasResult,
        article_text: str,
) -> JudgeResult:
    """
    Synthesize all evidence into final per-claim and overall verdicts.
    Falls back to computed verdicts if LLM fails.
    """
    # Build input payload for LLM
    claims_payload = []
    for claim in claims:
        cid = claim.claim_id or ""
        claim_sources = sources_by_claim.get(cid)
        sources_list = []
        if claim_sources:
            for i, s in enumerate(claim_sources.sources):
                sources_list.append({
                    "index": i,
                    "title": s.title or "",
                    "snippet": (s.snippet or "")[:200],
                    "stance": s.stance or "UNCLEAR",
                    "quality_score": s.quality_score or 0.0,
                })
        claims_payload.append({
            "claim_id": cid,
            "text": claim.text,
            "sources": sources_list,
        })

    user_content = json.dumps({
        "claims": claims_payload,
        "bias_report": {
            "bias_score": bias_result.bias_score,
            "bias_direction": bias_result.bias_direction,
            "summary": bias_result.summary,
        },
    }, ensure_ascii=False)

    async def call_judge(client: genai.Client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                response_mime_type="application/json",
            )
        )

    try:
        response = await execute_gemini_call(call_judge)
        raw = response.text
        data = json.loads(raw)

        claim_verdicts = [
            ClaimVerdictSchema(
                claim_id=v.get("claim_id", ""),
                verdict=v.get("verdict", "UNVERIFIABLE"),
                confidence=_clamp(float(v.get("confidence", 0.1))),
                reasoning=v.get("reasoning", ""),
                key_source_indices=v.get("key_source_indices", []),
            )
            for v in data.get("claim_verdicts", [])
        ]

        return JudgeResult(
            overall_verdict=data.get("overall_verdict", "UNVERIFIABLE"),
            overall_confidence=_clamp(float(data.get("overall_confidence", 0.1))),
            overall_summary=data.get("overall_summary", ""),
            claim_verdicts=claim_verdicts,
        )

    except Exception as e:
        logger.error("Judge agent failed: %s, using computed fallback", e)
        return compute_fallback_verdict(claims, sources_by_claim, bias_result)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


