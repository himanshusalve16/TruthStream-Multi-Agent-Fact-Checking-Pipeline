"""Text cleaning and truncation utilities."""
import re
import hashlib
from typing import Optional

# Maximum tokens before truncation (~15000 tokens ≈ 60000 characters for GPT-4o)
MAX_CHARS = 60_000
MAX_WORDS = 15_000

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions?",
    r"you\s+are\s+now\s+(?:a\s+)?(?:different|new)",
    r"disregard\s+(?:all\s+)?(?:prior|previous|earlier)\s+(?:instructions?|context)",
    r"system\s*:\s*(?:you\s+are|forget)",
    r"\[INST\]",
    r"<\|(?:system|user|assistant)\|>",
]

INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def clean_text(raw: str) -> str:
    """Normalize whitespace, remove null bytes, collapse repeated newlines."""
    text = raw.replace("\x00", "")
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate_text(text: str) -> tuple[str, bool]:
    """Truncate to MAX_WORDS words. Returns (text, was_truncated)."""
    words = text.split()
    if len(words) <= MAX_WORDS:
        return text, False
    truncated = " ".join(words[:MAX_WORDS])
    return truncated, True


def sanitize_for_llm(text: str) -> str:
    """Strip potential prompt injection patterns."""
    # Find earliest injection pattern and truncate before it
    match = INJECTION_RE.search(text)
    if match:
        text = text[: match.start()].strip()
    return text


def word_count(text: str) -> int:
    return len(text.split())


def md5_hash(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def extract_domain(url: str) -> Optional[str]:
    """Extract the bare domain from a URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip www.
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or None
    except Exception:
        return None


def evaluate_article_complexity(text: str) -> dict:
    """
    Computes lightweight heuristics for article classification:
    - word_count (int)
    - html_noise (float)
    - claim_density (float)
    - entity_density (float)
    - classification (str)
    """
    import re
    cleaned = text.strip()
    words = cleaned.split()
    wc = len(words)
    
    # 1. HTML Noise Estimate (ratio of non-alphanumeric chars or long symbol strings)
    non_alphanum = len([c for c in cleaned if not c.isalnum() and not c.isspace()])
    noise_ratio = non_alphanum / max(1, len(cleaned))
    
    # 2. Claim Density Estimate (numbers, percentages, quotes, statistics)
    numbers_count = len(re.findall(r'\b\d+\b', cleaned))
    percent_count = len(re.findall(r'\d+%', cleaned))
    quotes_count = len(re.findall(r'["\'"“”]', cleaned))
    claim_density = (numbers_count + percent_count * 2 + quotes_count) / max(1, wc)
    
    # 3. Entity Density (capitalized words excluding start of string)
    capitalized = len([w for w in words if w and w[0].isupper()])
    entity_density = capitalized / max(1, wc)
    
    # Classification logic
    if wc < 80 or (wc < 250 and noise_ratio > 0.40):
        classification = "recovery"
    elif wc < 600 and claim_density < 0.08:
        classification = "fast"
    elif wc < 1800:
        classification = "standard"
    else:
        classification = "deep"
        
    return {
        "word_count": wc,
        "noise_ratio": noise_ratio,
        "claim_density": claim_density,
        "entity_density": entity_density,
        "classification": classification
    }


def classify_article_complexity(text: str) -> str:
    res = evaluate_article_complexity(text)
    return res["classification"]
