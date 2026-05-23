"""Bias Scorer Agent — analyzes article text for media bias signals."""
import asyncio
import json
import logging

from google import genai
from google.genai import types
from models.schemas import BiasResult, FramingFlag
from services.gemini import execute_gemini_call
from config import settings
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


async def score_bias(article_text: str, article_url: str | None = None) -> BiasResult:
    """
    Run the Bias Scorer agent against the full article text.
    Returns a BiasResult. Temperature = 0.2 per spec.
    """
    safe_text = sanitize_for_llm(article_text)
    user_content = (
        f"Article URL: {article_url or 'N/A'}\n\n"
        f"<article_text>\n{safe_text}\n</article_text>\n\n"
        "Analyze this article for bias."
    )

    async def call_bias_scorer(client: genai.Client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                response_mime_type="application/json",
            )
        )

    try:
        response = await execute_gemini_call(call_bias_scorer)
        raw = response.text
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
        logger.error("Bias scoring failed: %s, returning neutral default", e)
        return BiasResult(
            bias_score=50,
            bias_direction="neutral",
            framing_flags=[],
            loaded_terms=[],
            summary="Bias analysis could not be completed.",
        )
