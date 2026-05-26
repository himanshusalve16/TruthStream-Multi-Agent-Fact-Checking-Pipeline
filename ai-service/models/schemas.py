from __future__ import annotations
from typing import Optional, List, Any
from pydantic import BaseModel, Field


# ─────────────────────────────────────────
# Job dispatch (from Spring Boot)
# ─────────────────────────────────────────
class JobDispatch(BaseModel):
    job_id: str
    user_id: str
    input_type: str  # "url" | "text"
    url: Optional[str] = None
    text: Optional[str] = None


# ─────────────────────────────────────────
# Claim
# ─────────────────────────────────────────
class ClaimSchema(BaseModel):
    claim_id: Optional[str] = None  # set after DB insert
    text: str
    context_quote: Optional[str] = None
    claim_type: Optional[str] = None  # statistic|event|attribution|definition
    checkability: Optional[str] = None  # high|medium|low
    embedding: Optional[List[float]] = None


class ClaimExtractionResult(BaseModel):
    claims: List[ClaimSchema]
    extraction_notes: Optional[str] = None


# ─────────────────────────────────────────
# Source
# ─────────────────────────────────────────
class SourceSchema(BaseModel):
    source_id: Optional[str] = None
    url: str
    title: Optional[str] = None
    domain: Optional[str] = None
    snippet: Optional[str] = None
    full_text: Optional[str] = None
    stance: Optional[str] = None  # SUPPORTS|REFUTES|NEUTRAL|UNCLEAR
    quality_score: Optional[float] = 0.0
    fetch_status: Optional[str] = None  # success|timeout|blocked|empty


class ClaimSourcesResult(BaseModel):
    claim_id: str
    sources: List[SourceSchema]


# ─────────────────────────────────────────
# Bias
# ─────────────────────────────────────────
class FramingFlag(BaseModel):
    type: str
    description: Optional[str] = None
    examples: Optional[List[str]] = None
    severity: Optional[str] = None  # low|medium|high


class BiasResult(BaseModel):
    bias_score: int = Field(ge=0, le=100)
    bias_direction: str  # left_leaning|right_leaning|pro_establishment|anti_establishment|neutral
    framing_flags: List[FramingFlag] = []
    loaded_terms: List[str] = []
    summary: str


# ─────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────
class ClaimVerdictSchema(BaseModel):
    claim_id: str
    verdict: str  # SUPPORTED|REFUTED|CONTESTED|UNVERIFIABLE
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_source_indices: List[int] = []


class JudgeResult(BaseModel):
    overall_verdict: str  # MOSTLY_TRUE|MIXTURE|MOSTLY_FALSE|UNVERIFIABLE
    overall_confidence: float = Field(ge=0.0, le=1.0)
    overall_summary: str
    claim_verdicts: List[ClaimVerdictSchema]


# ─────────────────────────────────────────
# SSE event envelope
# ─────────────────────────────────────────
class SseEvent(BaseModel):
    type: str
    data: Any
