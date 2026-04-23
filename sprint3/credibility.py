"""
sprint3/credibility.py
──────────────────────
Domain-based source credibility tier classifier.

Tier 1 [w=1.0] — Peer-reviewed / official / primary data repositories
Tier 2 [w=0.7] — Established news / encyclopedias / textbooks
Tier 3 [w=0.4] — Blogs, forums, unknown, undated content

Classification is purely rule-based on URL domain patterns.
Unknown domains default to Tier 3.
"""

from __future__ import annotations
import re
from sprint3.models import SourceTier

# ── Tier 1 domain patterns ─────────────────────────────────────────────────────
# Official, government, institutional, peer-reviewed

_TIER1_EXACT = frozenset({
    "who.int", "un.org", "cdc.gov", "nih.gov", "fda.gov", "nasa.gov",
    "ec.europa.eu", "europa.eu", "worldbank.org", "imf.org", "oecd.org",
    "nature.com", "science.org", "sciencemag.org", "cell.com",
    "nejm.org", "thelancet.com", "bmj.com", "jamanetwork.com",
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "arxiv.org", "ssrn.com", "jstor.org",
    "ieee.org", "ieeexplore.ieee.org", "acm.org", "dl.acm.org",
    "scholar.google.com", "researchgate.net",
    "data.worldbank.org", "stats.oecd.org", "ourworldindata.org",
    "ipcc.ch", "iea.org", "wto.org", "bis.org",
})

_TIER1_SUFFIXES = (
    ".gov", ".mil", ".edu",          # government, military, educational
    ".int",                           # international organisations
)

_TIER1_PATTERNS = (
    r"\.ac\.\w{2}$",                 # academic country domains (e.g. .ac.uk)
    r"ncbi\.nlm\.nih",
    r"pubmed",
)

# ── Tier 2 domain patterns ─────────────────────────────────────────────────────
# Established news, encyclopedias, textbooks

_TIER2_EXACT = frozenset({
    "wikipedia.org", "britannica.com", "encyclopedia.com",
    "bbc.com", "bbc.co.uk", "reuters.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com",
    "wsj.com", "ft.com", "bloomberg.com", "economist.com",
    "time.com", "newsweek.com", "forbes.com", "theatlantic.com",
    "scientificamerican.com", "newscientist.com", "nationalgeographic.com",
    "smithsonianmag.com", "pbs.org", "npr.org",
    "history.com", "britannica.com",
    "statista.com",                   # data aggregator — borderline T2
    "pew.org", "pewresearch.org",
})

# ── Classification function ────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    """Return lower-case bare domain from a URL string."""
    if not url:
        return ""
    # Strip scheme
    url = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
    # Strip path
    domain = url.split("/")[0].lower()
    # Strip www.
    domain = re.sub(r"^www\.", "", domain)
    return domain


def classify_domain(url: str, source_name: str = "") -> SourceTier:
    """
    Return the credibility tier for a given URL.
    Falls back to source_name heuristics if URL is empty.
    """
    domain = _extract_domain(url)

    # ── Tier 1 checks ──────────────────────────────────────────────────────
    if domain in _TIER1_EXACT:
        return SourceTier.TIER_1

    for suffix in _TIER1_SUFFIXES:
        if domain.endswith(suffix):
            return SourceTier.TIER_1

    for pattern in _TIER1_PATTERNS:
        if re.search(pattern, domain):
            return SourceTier.TIER_1

    # ── Tier 2 checks ──────────────────────────────────────────────────────
    if domain in _TIER2_EXACT:
        return SourceTier.TIER_2

    # Source name heuristics (when URL is unavailable)
    if not domain and source_name:
        name_lower = source_name.lower()
        tier1_keywords = {
            "nature", "science", "lancet", "nejm", "bmj", "jama", "cell",
            "pubmed", "arxiv", "ieee", "acm", "who", "cdc", "nih",
        }
        tier2_keywords = {
            "wikipedia", "britannica", "bbc", "reuters", "nytimes",
            "guardian", "bloomberg", "economist", "scientific american",
            "pew", "statista",
        }
        if any(k in name_lower for k in tier1_keywords):
            return SourceTier.TIER_1
        if any(k in name_lower for k in tier2_keywords):
            return SourceTier.TIER_2

    # ── Tier 3: default ────────────────────────────────────────────────────
    return SourceTier.TIER_3


def detect_conflict(snippets: list) -> tuple[bool, str]:
    """
    Detect cross-tier conflicts.
    Returns (conflict_bool, conflict_note).

    Conflict rule: if the highest-tier snippet SUPPORTS and any lower-tier
    CONTRADICTS (or vice versa), log the conflict. Higher tier wins.
    """
    if len(snippets) < 2:
        return False, ""

    from sprint3.models import EvidenceRelation
    sorted_snips = sorted(snippets, key=lambda s: s.weight, reverse=True)
    top = sorted_snips[0]

    for s in sorted_snips[1:]:
        if s.relation in (EvidenceRelation.SUPPORTS, EvidenceRelation.CONTRADICTS) \
        and top.relation in (EvidenceRelation.SUPPORTS, EvidenceRelation.CONTRADICTS) \
        and s.relation != top.relation:
            note = (
                f"Conflict: {top.tier.value} ({top.source_name}) says {top.relation.value} "
                f"vs {s.tier.value} ({s.source_name}) says {s.relation.value}. "
                f"Higher tier ({top.tier.value}) takes precedence."
            )
            return True, note

    return False, ""
