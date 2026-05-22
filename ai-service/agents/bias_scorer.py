"""Bias Scorer Agent — analyzes article text for media bias signals."""
import asyncio
import json
import logging

from models.schemas import BiasResult, FramingFlag
from services.embeddings import get_openai_client
from utils.text import sanitize_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a media bias analyst. Analyze the provided article for bias signals.

Evaluate:
1. Loaded language: emotionally charged words used to influence rather than inform.
2. Framing bias: selective emphasis, misleading headlines, omission of counterarguments.
3. Attribution patterns: are sources one-sided? Are opposing voices quoted fairly?
4. Overall tone: neutral/clinical vs. persuasive/emotional.

Score bias from 0 (completely neutral) to 100 (heavily biased).
Identify the likely direction: left_leaning, right_leaning, pro_establishment, anti_establishment, or neutral.

Output JSON only:
{
  "bias_score": integer (0-100),
  "bias_direction": "left_leaning|right_leaning|pro_establishment|anti_establishment|neutral",
  "framing_flags": [
    {"type": "string", "description": "string", "examples": ["string"], "severity": "low|medium|high"}
  ],
  "loaded_terms": ["string"],
  "summary": "string (2-3 sentences)"
}"""

MAX_RETRIES = 2
RETRY_DELAY = 5.0


async def score_bias(article_text: str, article_url: str | None = None) -> BiasResult:
    """
    Run the Bias Scorer agent against the full article text.
    Returns a BiasResult. Temperature = 0.2 per spec.
    """
    client = get_openai_client()
    safe_text = sanitize_for_llm(article_text)
    user_content = (
        f"Article URL: {article_url or 'N/A'}\n\n"
        f"<article_text>\n{safe_text}\n</article_text>\n\n"
        "Analyze this article for bias."
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                timeout=30.0,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            flags = [FramingFlag(**f) for f in data.get("framing_flags", [])]
            return BiasResult(
                bias_score=max(0, min(100, int(data.get("bias_score", 50)))),
                bias_direction=data.get("bias_direction", "neutral"),
                framing_flags=flags,
                loaded_terms=data.get("loaded_terms", []),
                summary=data.get("summary", ""),
            )
        except Exception as e:
            logger.warning("Bias scoring attempt %d failed: %s", attempt + 1, e)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error("All bias scoring attempts failed, returning neutral default")
                return BiasResult(
                    bias_score=50,
                    bias_direction="neutral",
                    framing_flags=[],
                    loaded_terms=[],
                    summary="Bias analysis could not be completed.",
                )
