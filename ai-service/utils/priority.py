import re
from typing import List, Tuple, Optional
import asyncpg

def compute_claim_significance(claim_text: str, checkability: str, claim_type: str) -> float:
    """Computes the local significance of a claim based on factual density, keywords, and type."""
    score = 0.0
    
    # 1. Factual / Numeric density (numbers, percentages, currencies)
    numbers = re.findall(r'\b\d+(?:\.\d+)?%?\b|[$€£¥]\d+', claim_text)
    score += len(numbers) * 1.5
    
    # 2. Proper Nouns / Entities (capitalized words after the first word)
    words = claim_text.split()
    proper_nouns = 0
    for w in words[1:]:
        if w and w[0].isupper() and w.lower() not in {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}:
            proper_nouns += 1
    score += proper_nouns * 0.8
    
    # 3. Checkability Weight
    chk_weight = {"high": 3.0, "medium": 1.5, "low": 0.5}
    score += chk_weight.get(checkability.lower(), 1.0)
    
    # 4. Claim Type Weight
    type_weight = {"statistic": 2.5, "event": 2.0, "attribution": 1.5, "definition": 0.5}
    score += type_weight.get(claim_type.lower(), 1.0)
    
    # 5. Geopolitical / Health / Science Keywords
    keywords = {
        # Geopolitical
        "biden", "trump", "election", "war", "military", "government", "senate", "house", "congress",
        "president", "minister", "china", "russia", "ukraine", "gaza", "israel", "iran", "court", "law",
        # Health & Science
        "covid", "vaccine", "health", "disease", "virus", "cancer", "medical", "treatment", "doctor", "study",
        "scientific", "research", "climate", "warming", "carbon", "co2", "environment",
        # Economics
        "gdp", "inflation", "unemployment", "recession", "economy", "percent", "rate", "billion", "million"
    }
    cleaned_words = set(re.findall(r'\w+', claim_text.lower()))
    keyword_matches = cleaned_words.intersection(keywords)
    score += len(keyword_matches) * 2.0
    
    return score

def calculate_source_overlap(claim_text: str, search_results: List[dict]) -> float:
    """Calculates semantic/lexical overlap between the claim and the top search snippets."""
    if not search_results:
        return 0.0
    
    overlaps = []
    claim_words = set(re.findall(r'\w+', claim_text.lower()))
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    claim_words = claim_words - stop_words
    if not claim_words:
        return 0.0
        
    for r in search_results[:3]:
        snippet = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        snippet_words = set(re.findall(r'\w+', snippet))
        intersection = claim_words.intersection(snippet_words)
        overlaps.append(len(intersection) / len(claim_words))
        
    return sum(overlaps) / len(overlaps) if overlaps else 0.0

async def fetch_cached_claim_results(pool: asyncpg.Pool, similar_claim_id: str) -> Tuple[List[asyncpg.Record], Optional[asyncpg.Record]]:
    """Retrieve cached sources and verdicts for a given claim ID."""
    async with pool.acquire() as conn:
        sources_rows = await conn.fetch(
            "SELECT * FROM sources WHERE claim_id = $1::uuid", similar_claim_id
        )
        verdict_row = await conn.fetchrow(
            "SELECT * FROM verdicts WHERE claim_id = $1::uuid AND is_overall = FALSE ORDER BY created_at DESC LIMIT 1",
            similar_claim_id
        )
        return sources_rows, verdict_row
