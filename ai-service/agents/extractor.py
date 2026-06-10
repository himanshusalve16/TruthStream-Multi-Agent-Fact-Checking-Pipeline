"""Claim Extractor Agent — extracts verifiable factual claims from article text."""
import json
import logging

from google import genai
from google.genai import types

from models.schemas import ClaimSchema, ClaimExtractionResult
from services.gemini import execute_gemini_call
from config import settings
from utils.text import sanitize_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional fact-checker. Your task is to extract discrete, \
verifiable factual claims from the provided article.

Rules:
- Extract ONLY checkable factual claims: statistics, named events, attributed statements, specific dates/numbers.
- Do NOT extract: opinions, predictions, rhetorical questions, vague assertions.
- Each claim must be self-contained and understandable without the surrounding article.
- Maximum 8 candidate claims per article. Prioritize the most specific and checkable ones.
- Label each claim with a type: "statistic", "event", "attribution", or "definition".
- Rate checkability as "high" (specific, verifiable), "medium" (partially verifiable), or "low" (hard to verify).

Output JSON only. Use this schema:
{
  "claims": [
    {
      "text": "string",
      "context_quote": "string",
      "claim_type": "statistic|event|attribution|definition",
      "checkability": "high|medium|low"
    }
  ],
  "extraction_notes": "string"
}"""

USER_PROMPT_TEMPLATE = """Article URL: {url_or_none}

Article text:
<article_text>
{article_text}
</article_text>

Extract all verifiable factual claims."""


async def extract_claims(
        article_text: str,
        article_url: str | None = None,
) -> ClaimExtractionResult:
    """
    Run the Claim Extractor agent against the given article text.
    Returns a ClaimExtractionResult with claims list.
    """
    safe_text = sanitize_for_llm(article_text)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        url_or_none=article_url or "N/A",
        article_text=safe_text,
    )

    async def call_extractor(client: genai.Client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                response_mime_type="application/json",
            )
        )

    try:
        import uuid
        response = await execute_gemini_call(call_extractor)
        raw = response.text
        data = json.loads(raw)
        claims_data = data.get("claims", [])
        
        claims = []
        for c in claims_data:
            c["claim_id"] = str(uuid.uuid4())
            claims.append(ClaimSchema(**c))
            
        return ClaimExtractionResult(
            claims=claims,
            extraction_notes=data.get("extraction_notes", ""),
        )
    except Exception as e:
        logger.error("Claim extraction failed: %s", e)
        raise RuntimeError(f"Claim extraction failed: {e}")
