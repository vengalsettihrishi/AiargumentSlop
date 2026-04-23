"""
sprint3/retrieval.py
────────────────────
Multi-source RAG retrieval engine for Sprint 3.

Architecture:
  PRIMARY   — Tavily Search API (structured, snippet-level)
  SECONDARY — Serper (Google results)
  TERTIARY  — You.com Search API
  FALLBACK  — LLM internal knowledge (marked as synthetic, Tier 3)

For each claim:
  1. Fan out to all configured sources in parallel (concurrent.futures)
  2. Collect raw snippets
  3. Classify each snippet's source domain → SourceTier
  4. Detect cross-tier conflicts
  5. Return a RetrievalResult

Priority order (sprint2 flags):
  [HIGH CONFLICT] claims  → retrieved first
  [PRIORITY RETRIEVAL]    → retrieved second
  Standard / [ACCEPTED]+[TIME-SENSITIVE] → retrieved last
"""

from __future__ import annotations
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from config import settings
from sprint3.models import (
    EvidenceRelation, EvidenceSnippet, RetrievalResult, SourceTier,
)
from sprint3.credibility import classify_domain, detect_conflict

log = logging.getLogger(__name__)

# Max snippets to keep per claim (after dedup / ranking)
MAX_SNIPPETS_PER_CLAIM = 5
MAX_WORKERS            = 4


# ── Relation classifier (LLM-based) ──────────────────────────────────────────

def _classify_relation(claim_text: str, passage: str) -> EvidenceRelation:
    """
    Classify whether a retrieved passage SUPPORTS, CONTRADICTS, or is UNRELATED
    to the claim. Uses a fast LLM call with a tight prompt.
    Falls back to UNRELATED on error.
    """
    if not passage or not claim_text:
        return EvidenceRelation.UNRELATED

    from llm_client import call_llm

    system = (
        "You are a fact-checking assistant. Given a CLAIM and a PASSAGE, "
        "classify the passage's relation to the claim as exactly one of:\n"
        "  SUPPORTS    — the passage affirms the claim\n"
        "  CONTRADICTS — the passage directly refutes the claim\n"
        "  UNRELATED   — the passage is irrelevant to the claim\n"
        "Output ONLY the single word verdict. No explanation."
    )
    user = f"CLAIM: {claim_text[:300]}\n\nPASSAGE: {passage[:600]}"

    try:
        raw, _ = call_llm(
            system_prompt=system,
            user_prompt=user,
            max_tokens=8,
            temperature=0.0,
        )
        raw = raw.strip().upper().split()[0]
        return EvidenceRelation(raw) if raw in EvidenceRelation._value2member_map_ else EvidenceRelation.UNRELATED
    except Exception as exc:  # noqa: BLE001
        log.debug("Relation classification failed: %s", exc)
        return EvidenceRelation.UNRELATED


# ── Individual source adapters ────────────────────────────────────────────────

def _fetch_tavily(claim_text: str) -> list[dict]:
    """
    Call Tavily Search API.
    Returns list of {source_name, url, passage}.
    """
    if not settings.TAVILY_API_KEY:
        return []
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        resp = client.search(
            query=claim_text,
            search_depth="advanced",
            max_results=settings.RETRIEVAL_MAX_RESULTS,
            include_answer=False,
        )
        results = []
        for r in resp.get("results", []):
            results.append({
                "source_name": r.get("title", r.get("url", "Tavily Result")),
                "url":         r.get("url", ""),
                "passage":     r.get("content", "")[:800],
                "retrieval_source": "tavily",
            })
        log.debug("Tavily: %d results for '%s…'", len(results), claim_text[:40])
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("Tavily retrieval failed: %s", exc)
        return []


def _fetch_serper(claim_text: str) -> list[dict]:
    """
    Call Serper (Google Search) API.
    Returns list of {source_name, url, passage}.
    """
    if not settings.SERPER_API_KEY:
        return []
    try:
        import httpx
        resp = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": claim_text, "num": settings.RETRIEVAL_MAX_RESULTS},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", []):
            passage = item.get("snippet", "")
            if not passage:
                continue
            results.append({
                "source_name": item.get("title", item.get("link", "Serper Result")),
                "url":         item.get("link", ""),
                "passage":     passage[:800],
                "retrieval_source": "serper",
            })
        log.debug("Serper: %d results for '%s…'", len(results), claim_text[:40])
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("Serper retrieval failed: %s", exc)
        return []


def _fetch_you(claim_text: str) -> list[dict]:
    """
    Call You.com Search API.
    Returns list of {source_name, url, passage}.
    """
    if not settings.YOU_API_KEY:
        return []
    try:
        import httpx
        resp = httpx.get(
            "https://api.ydc-index.io/search",
            params={"query": claim_text, "num_web_results": settings.RETRIEVAL_MAX_RESULTS},
            headers={"X-API-Key": settings.YOU_API_KEY},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for hit in data.get("hits", []):
            for snippet_text in hit.get("snippets", [])[:2]:
                results.append({
                    "source_name": hit.get("title", hit.get("url", "You.com Result")),
                    "url":         hit.get("url", ""),
                    "passage":     snippet_text[:800],
                    "retrieval_source": "you",
                })
        log.debug("You.com: %d results for '%s…'", len(results), claim_text[:40])
        return results
    except Exception as exc:  # noqa: BLE001
        log.warning("You.com retrieval failed: %s", exc)
        return []


# ── LLM fallback retrieval ────────────────────────────────────────────────────

def _fetch_llm_fallback(claim_text: str) -> list[dict]:
    """
    Use LLM internal knowledge as a last-resort retrieval source.
    Marked as Tier 3 / synthetic. Used only when all web sources return nothing.
    """
    from llm_client import call_llm
    system = (
        "You are a fact-checking assistant. Provide a brief factual passage "
        "relevant to the following claim, citing any well-known source by name if possible. "
        "Do NOT fabricate citations. If uncertain, say so explicitly."
    )
    user = f"Claim to fact-check: {claim_text}"
    try:
        raw, _ = call_llm(
            system_prompt=system,
            user_prompt=user,
            max_tokens=300,
            temperature=0.1,
        )
        return [{
            "source_name": "LLM Internal Knowledge (fallback)",
            "url": "",
            "passage": raw[:800],
            "retrieval_source": "llm",
        }]
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM fallback retrieval failed: %s", exc)
        return []


# ── Snippet assembly ──────────────────────────────────────────────────────────

def _assemble_snippets(
    raw_results: list[dict],
    claim_text: str,
    classify_relations: bool = True,
) -> list[EvidenceSnippet]:
    """
    Convert raw result dicts → EvidenceSnippet objects.
    Classifies tier by domain and relation by LLM (if enabled).
    Deduplicates by URL; caps at MAX_SNIPPETS_PER_CLAIM.
    """
    snippets: list[EvidenceSnippet] = []
    seen_urls: set[str] = set()

    # Prioritise higher-tier sources first (sort by domain tier before truncating)
    def _tier_priority(r: dict) -> int:
        tier = classify_domain(r.get("url",""), r.get("source_name",""))
        return {SourceTier.TIER_1: 0, SourceTier.TIER_2: 1, SourceTier.TIER_3: 2}[tier]

    raw_results.sort(key=_tier_priority)

    for r in raw_results:
        url = r.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        passage = r.get("passage", "").strip()
        if not passage:
            continue

        tier = classify_domain(url, r.get("source_name", ""))
        relation = (
            _classify_relation(claim_text, passage)
            if classify_relations
            else EvidenceRelation.UNRELATED
        )

        snippets.append(EvidenceSnippet(
            source_name=r.get("source_name", "Unknown Source"),
            url=url,
            tier=tier,
            relation=relation,
            passage=passage,
            retrieval_source=r.get("retrieval_source", "unknown"),
        ))

        if len(snippets) >= MAX_SNIPPETS_PER_CLAIM:
            break

    return snippets


# ── Per-claim retrieval ───────────────────────────────────────────────────────

def _retrieve_one_claim(claim_id: str, claim_text: str) -> RetrievalResult:
    """
    Retrieve evidence for a single claim from all sources in parallel.
    """
    log.info("Retrieving evidence for %s …", claim_id)
    t0 = time.perf_counter()

    all_raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_fetch_tavily, claim_text): "tavily",
            ex.submit(_fetch_serper, claim_text): "serper",
            ex.submit(_fetch_you,    claim_text): "you",
        }
        for fut in as_completed(futures):
            all_raw.extend(fut.result())

    # LLM fallback if all web sources returned nothing
    if not all_raw:
        log.info("  No web results for %s — using LLM fallback.", claim_id)
        all_raw = _fetch_llm_fallback(claim_text)

    snippets = _assemble_snippets(all_raw, claim_text)

    conflict_flag, conflict_note = detect_conflict(snippets)

    elapsed = time.perf_counter() - t0
    log.debug("  %s: %d snippet(s) in %.1fs", claim_id, len(snippets), elapsed)

    return RetrievalResult(
        claim_id=claim_id,
        claim_text=claim_text,
        snippets=snippets,
        retrieved=len(snippets) > 0,
        conflict_detected=conflict_flag,
        conflict_note=conflict_note,
    )


# ── Batch retrieval with priority ordering ────────────────────────────────────

def run_retrieval(
    claims_to_retrieve: list[tuple[str, str]],  # [(claim_id, claim_text), ...]
    priority_ids: Optional[list[str]] = None,
    high_conflict_ids: Optional[list[str]] = None,
) -> list[RetrievalResult]:
    """
    Retrieve evidence for all supplied claims.

    Priority order:
      1. [HIGH CONFLICT] claims from Sprint 2
      2. [PRIORITY RETRIEVAL] claims from Sprint 2
      3. All remaining claims

    Returns a list of RetrievalResult in original claim order.
    """
    priority_ids      = set(priority_ids or [])
    high_conflict_ids = set(high_conflict_ids or [])

    def _priority_key(item: tuple[str, str]) -> int:
        cid = item[0]
        if cid in high_conflict_ids:   return 0
        if cid in priority_ids:        return 1
        return 2

    ordered = sorted(claims_to_retrieve, key=_priority_key)

    results: list[RetrievalResult] = []
    for cid, text in ordered:
        results.append(_retrieve_one_claim(cid, text))

    # Restore original claim order for downstream consistency
    result_map = {r.claim_id: r for r in results}
    return [result_map[cid] for cid, _ in claims_to_retrieve if cid in result_map]
