"""Compressed Judge Agent — unified single-pass bias scoring, stance classification, and claim judging."""
import json
import logging
from typing import List, Dict

from google import genai
from google.genai import types
from models.schemas import (
    ClaimSchema, ClaimSourcesResult, BiasResult,
    JudgeResult, ClaimVerdictSchema, FramingFlag
)
from services.gemini import execute_gemini_call
from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an elite fact-checking editor and media bias analyst.
Your job is to analyze the provided article text, classify the stances of evidence sources for each claim, evaluate media bias, and produce final verdicts.

You will be given:
1. The original article text.
2. A list of factual claims extracted from the article.
3. For each claim, a list of search sources containing snippets and titles.

Your output must complete three tasks in a single pass:

Task 1: Source Stance Classification
For each claim and its associated sources, classify the stance of the source snippet relative to the claim as:
- "SUPPORTS": the source provides evidence that the claim is true
- "REFUTES": the source provides evidence that the claim is false
- "NEUTRAL": the source discusses the topic but takes no stance
- "UNCLEAR": the snippet is insufficient to determine stance

Task 2: Media Bias Analysis
Analyze the article text for:
- Loaded language (emotionally charged words)
- Framing bias (one-sided emphasis, omission of counterarguments)
- Tone (neutral vs persuasive)
- Score bias from 0 (completely neutral) to 100 (heavily biased) and direction (left_leaning, right_leaning, pro_establishment, anti_establishment, neutral)

Task 3: Veracity Judgment (STRICT EVIDENCE REQUIREMENT)
- Synthesize all evidence to determine the verdict of each claim. YOU MUST ONLY base this on the provided external sources:
  - SUPPORTED: majority of quality external sources support. MUST NOT be used if 0 sources are provided.
  - REFUTED: majority of quality external sources refute. MUST NOT be used if 0 sources are provided.
  - CONTESTED: external sources split between support and refutation. MUST NOT be used if 0 sources are provided.
  - UNVERIFIABLE: no usable external sources, or 0 sources were provided. This is the mandatory fallback for un-sourced claims.
- Formulate the overall article verdict: MOSTLY_TRUE, MIXTURE, MOSTLY_FALSE, or UNVERIFIABLE. If all claims are UNVERIFIABLE, the overall verdict MUST be UNVERIFIABLE.
- Calculate overall confidence (0.0 to 1.0), applying a confidence penalty of up to 0.15 if overall bias_score > 70.

Output JSON only using this schema:
{
  "bias": {
    "bias_score": integer (0-100),
    "bias_direction": "left_leaning|right_leaning|pro_establishment|anti_establishment|neutral",
    "framing_flags": [
      {"type": "string", "description": "string", "examples": ["string"], "severity": "low|medium|high"}
    ],
    "loaded_terms": ["string"],
    "summary": "string"
  },
  "claim_verdicts": [
    {
      "claim_id": "string",
      "verdict": "SUPPORTED|REFUTED|CONTESTED|UNVERIFIABLE",
      "confidence": float (0.0-1.0),
      "reasoning": "string",
      "key_source_indices": [integer],
      "source_stances": [
        {
          "source_index": integer,
          "stance": "SUPPORTS|REFUTES|NEUTRAL|UNCLEAR",
          "reason": "string (one sentence)"
        }
      ]
    }
  ],
  "overall_verdict": "MOSTLY_TRUE|MIXTURE|MOSTLY_FALSE|UNVERIFIABLE",
  "overall_confidence": float (0.0-1.0),
  "overall_summary": "string"
}"""

async def run_compressed_judge(
    claims: List[ClaimSchema],
    sources_by_claim: Dict[str, ClaimSourcesResult],
    article_text: str,
    article_url: str | None = None
) -> tuple[BiasResult, JudgeResult, Dict[str, List[str]]]:
    """
    Runs a single compressed judgment call performing stance classification,
    bias analysis, and claim judgment in one pass.
    
    Returns:
        tuple (BiasResult, JudgeResult, Dict[claim_id -> List[stance_strings]])
    """
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
                    "quality_score": s.quality_score or 0.0,
                })
        claims_payload.append({
            "claim_id": cid,
            "text": claim.text,
            "sources": sources_list,
        })

    user_payload = {
        "article_text": article_text[:20000],
        "article_url": article_url or "N/A",
        "claims": claims_payload
    }

    async def call_compressed(client: genai.Client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=json.dumps(user_payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                response_mime_type="application/json",
            )
        )

    try:
        response = await execute_gemini_call(call_compressed)
        data = json.loads(response.text)
    except Exception as e:
        logger.error("Compressed judge call failed: %s. Falling back to recovery logic.", e)
        # Fallback handling
        from utils.verdict_calc import compute_fallback_verdict
        dummy_bias = BiasResult(
            bias_score=50, bias_direction="neutral",
            framing_flags=[], loaded_terms=[],
            summary="Bias scoring failed. Fallback default used."
        )
        fallback_judge = compute_fallback_verdict(claims, sources_by_claim, dummy_bias)
        fallback_stances = {}
        for claim in claims:
            cid = claim.claim_id or ""
            cs = sources_by_claim.get(cid)
            num_sources = len(cs.sources) if cs else 0
            fallback_stances[cid] = ["UNCLEAR"] * num_sources
        return dummy_bias, fallback_judge, fallback_stances

    # 1. Parse BiasResult
    bias_data = data.get("bias", {})
    flags = [FramingFlag(**f) for f in bias_data.get("framing_flags", [])]
    bias_result = BiasResult(
        bias_score=max(0, min(100, int(bias_data.get("bias_score", 50)))),
        bias_direction=bias_data.get("bias_direction", "neutral"),
        framing_flags=flags,
        loaded_terms=bias_data.get("loaded_terms", []),
        summary=bias_data.get("summary", ""),
    )

    # 2. Parse Claim Verdicts & Stances
    claim_verdicts = []
    stances_by_claim = {}
    
    for cv in data.get("claim_verdicts", []):
        cid = cv.get("claim_id", "")
        verdict = cv.get("verdict", "UNVERIFIABLE")
        confidence = max(0.0, min(1.0, float(cv.get("confidence", 0.5))))
        reasoning = cv.get("reasoning", "")
        key_source_indices = cv.get("key_source_indices", [])
        
        claim_verdicts.append(ClaimVerdictSchema(
            claim_id=cid,
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            key_source_indices=key_source_indices
        ))
        
        # Stance classification mappings
        stances_list = []
        source_stances_raw = cv.get("source_stances", [])
        source_stances_raw.sort(key=lambda x: x.get("source_index", 0))
        for s_stance in source_stances_raw:
            stances_list.append(s_stance.get("stance", "UNCLEAR"))
        
        stances_by_claim[cid] = stances_list

    judge_result = JudgeResult(
        overall_verdict=data.get("overall_verdict", "UNVERIFIABLE"),
        overall_confidence=max(0.0, min(1.0, float(data.get("overall_confidence", 0.5)))),
        overall_summary=data.get("overall_summary", ""),
        claim_verdicts=claim_verdicts
    )

    return bias_result, judge_result, stances_by_claim
