"""Claim Extractor Agent — extracts verifiable factual claims from article text."""
import asyncio
import json
import logging
from typing import List

from openai import AsyncOpenAI

from models.schemas import ClaimSchema, ClaimExtractionResult
from services.embeddings import get_openai_client
from utils.text import sanitize_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional fact-checker. Your task is to extract discrete, \
verifiable factual claims from the provided article.

Rules:
- Extract ONLY checkable factual claims: statistics, named events, attributed statements, specific dates/numbers.
- Do NOT extract: opinions, predictions, rhetorical questions, vague assertions.
- Each claim must be self-contained and understandable without the surrounding article.
- Maximum 10 claims per article. Prioritize the most specific and checkable ones.
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

MAX_RETRIES = 2
RETRY_DELAY = 5.0


async def extract_claims(
        article_text: str,
        article_url: str | None = None,
) -> ClaimExtractionResult:
    """
    Run the Claim Extractor agent against the given article text.
    Returns a ClaimExtractionResult with claims list.
    """
    client = get_openai_client()
    safe_text = sanitize_for_llm(article_text)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        url_or_none=article_url or "N/A",
        article_text=safe_text,
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=30.0,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            claims_data = data.get("claims", [])
            claims = [ClaimSchema(**c) for c in claims_data]
            return ClaimExtractionResult(
                claims=claims,
                extraction_notes=data.get("extraction_notes", ""),
            )
        except Exception as e:
            logger.warning("Claim extraction attempt %d failed: %s", attempt + 1, e)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error("All extraction attempts failed")
                raise RuntimeError(f"Claim extraction failed after {MAX_RETRIES + 1} attempts: {e}")
