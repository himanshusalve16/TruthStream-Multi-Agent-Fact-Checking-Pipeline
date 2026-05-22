"""Source quality scoring heuristics."""

TRUSTED_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "theguardian.com", "nytimes.com", "washingtonpost.com",
    "economist.com", "ft.com", "bloomberg.com", "npr.org",
    "nature.com", "science.org", "thelancet.com", "bmj.com",
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "who.int", "cdc.gov", "nih.gov", "fda.gov", "bls.gov",
    "census.gov", "data.gov", "congress.gov",
    "snopes.com", "factcheck.org", "politifact.com",
    "fullfact.org", "leadstories.com",
    "wikipedia.org",  # low weight — covered by domain scoring separately
}

# TLDs that imply institutional credibility
TRUSTED_TLDS = {".gov", ".edu", ".ac.uk", ".ac.nz", ".ac.in"}

LOW_QUALITY_DOMAINS = {
    "infowars.com", "naturalnews.com", "beforeitsnews.com",
    "worldnewsdailyreport.com", "empirenews.net", "thelastlineofdefense.org",
    "nowtheendbegins.com", "thegatewaypundit.com", "100percentfedup.com",
    "activistpost.com", "humansarefree.com", "zerohedge.com",
    "thedailybeast.com",  # known for sensationalism
}

PAYWALL_SIGNALS = [
    "subscribe to read", "sign in to read", "subscribe now",
    "this content is for subscribers", "premium content",
    "create your free account", "sign up to continue reading",
]


def score_source(
        domain: str,
        url: str,
        snippet: str,
        fetch_status: str,
        search_rank: int,
        full_text: str = "",
) -> float:
    """
    Score a source from 0.0 to 1.0 based on quality signals.
    Scores are clamped to [0.0, 1.0].
    """
    score = 0.0

    # Trusted domain
    if domain in TRUSTED_DOMAINS:
        score += 0.4

    # Trusted TLD (e.g. .gov, .edu)
    for tld in TRUSTED_TLDS:
        if domain.endswith(tld):
            score += 0.3
            break

    # Low quality domain (strong negative)
    if domain in LOW_QUALITY_DOMAINS:
        score -= 0.5

    # HTTPS
    if url.startswith("https://"):
        score += 0.1

    # Sufficient snippet
    if snippet and len(snippet) > 100:
        score += 0.1

    # Fetch succeeded
    if fetch_status == "success":
        score += 0.1

    # Paywall penalty
    combined_text = (snippet or "") + " " + (full_text or "")
    if any(pw.lower() in combined_text.lower() for pw in PAYWALL_SIGNALS):
        score -= 0.3

    # High search rank bonus
    if search_rank <= 3:
        score += 0.1

    return round(max(0.0, min(1.0, score)), 3)


def is_paywalled(snippet: str = "", full_text: str = "") -> bool:
    combined = (snippet or "") + " " + (full_text or "")
    return any(pw.lower() in combined.lower() for pw in PAYWALL_SIGNALS)
