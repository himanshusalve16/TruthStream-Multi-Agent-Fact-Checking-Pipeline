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


def classify_article_complexity(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) < 100 or (len(cleaned) < 300 and " " not in cleaned):
        return "broken/noisy"
    wc = len(cleaned.split())
    if wc < 600:
        return "short/simple"
    elif wc < 1800:
        return "medium"
    else:
        return "long/complex"
