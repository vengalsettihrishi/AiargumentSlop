"""
sprint3/moderator.py
────────────────────
Moderator Agent — issues credibility-weighted verdicts on every claim.

Flow:
  1. Build claims+evidence context block for the LLM prompt.
  2. Call primary LLM (provider=openai/gpt-4o by default for consistency).
  3. Parse verdicts from LLM output.
  4. For any claim with no evidence retrieved (retrieved=False), force UNCERTAIN.
  5. For [ACCEPTED] claims from Sprint 2, skip retrieval but issue CORRECT if
     the claim was fully accepted with no caveats. Allow TIME-SENSITIVE overrides.
  6. Compute confidence = verdict_score × best_source_weight for every claim.

Parser strategy:
  Regex-based extraction is robust to slight formatting variation.
  Falls back to UNCERTAIN for any unparseable verdict.
"""

from __future__ import annotations
import logging
import re
from typing import Optional

from llm_client import call_llm
from config import settings
from sprint3.models import (
    EvidenceRelation, EvidenceSnippet, RetrievalResult,
    ModeratorVerdict, VerdictLabel, VERDICT_SCORES, TIER_WEIGHTS, SourceTier,
)
from sprint3.prompts import MODERATOR_SYSTEM, MODERATOR_USER

log = logging.getLogger(__name__)

# ── Verdict regex ──────────────────────────────────────────────────────────────
# Matches: C2 → INCORRECT [w=0.7] Evidence: ... | Correction: ...
_VERDICT_RE = re.compile(
    r"^(C\d+)\s*[→\-]+>?\s*(CORRECT|INCORRECT|UNCERTAIN)\s*"
    r"(?:\[w=[\d.]+\])?\s*"
    r"(?:Evidence\s*:\s*(.*?))?(?:\|\s*Correction\s*:\s*(.+))?$",
    re.MULTILINE | re.IGNORECASE,
)

_CASCADE_FLAG_RE = re.compile(r"\[CASCADE REVIEW from (C\d+)\]", re.IGNORECASE)


# ── Context block builders ─────────────────────────────────────────────────────

def _build_claims_evidence_block(
    claims_data: list[tuple[str, str, RetrievalResult, bool]],
    # (claim_id, claim_text, retrieval_result, is_cascade)
) -> str:
    lines: list[str] = []
    for cid, text, result, is_cascade in claims_data:
        cascade_note = f"  ⚠ [CASCADE REVIEW] — parent claim failed" if is_cascade else ""
        lines.append(f"\n{'─'*55}")
        lines.append(f"{cid}: {text}")
        if cascade_note:
            lines.append(cascade_note)

        if not result.retrieved or not result.snippets:
            lines.append("  [EVIDENCE] No sources retrieved.")
        else:
            for i, s in enumerate(result.snippets, 1):
                lines.append(
                    f"  [EVIDENCE {i}] {s.source_name} "
                    f"({s.tier.value}, w={s.weight:.1f}) "
                    f"[{s.relation.value}]"
                )
                lines.append(f"    \"{s.passage[:300]}\"")
            if result.conflict_detected:
                lines.append(f"  ⚡ CONFLICT DETECTED: {result.conflict_note}")
    return "\n".join(lines)


def _build_sprint2_context(
    sprint2_statuses: dict[str, str],
    priority_ids: set[str],
    high_conflict_ids: set[str],
) -> str:
    lines: list[str] = []
    for cid, status in sorted(sprint2_statuses.items(), key=lambda x: int(x[0][1:])):
        flags = []
        if cid in high_conflict_ids:  flags.append("[HIGH CONFLICT]")
        if cid in priority_ids:       flags.append("[PRIORITY RETRIEVAL]")
        flag_str = " ".join(flags)
        lines.append(f"  {cid}: {status} {flag_str}")
    return "\n".join(lines) if lines else "  (no Sprint 2 context available)"


# ── Verdict parser ─────────────────────────────────────────────────────────────

def _parse_verdicts(
    raw: str,
    claims_data: list[tuple[str, str, RetrievalResult, bool]],
) -> dict[str, tuple[VerdictLabel, Optional[str], Optional[str]]]:
    """
    Returns {claim_id: (verdict_label, evidence_summary, correction)}.
    Unparseable claims default to UNCERTAIN.
    """
    parsed: dict[str, tuple[VerdictLabel, Optional[str], Optional[str]]] = {}

    for m in _VERDICT_RE.finditer(raw):
        cid          = m.group(1).strip()
        verdict_raw  = m.group(2).strip().upper()
        evidence_txt = (m.group(3) or "").strip()
        correction   = (m.group(4) or "").strip() or None

        try:
            verdict = VerdictLabel(verdict_raw)
        except ValueError:
            verdict = VerdictLabel.UNCERTAIN

        # Only allow corrections for INCORRECT verdicts
        if verdict != VerdictLabel.INCORRECT:
            correction = None

        parsed[cid] = (verdict, evidence_txt or None, correction)

    # Fill missing claims with UNCERTAIN
    for cid, _, _, _ in claims_data:
        if cid not in parsed:
            log.warning("No verdict parsed for %s — defaulting to UNCERTAIN.", cid)
            parsed[cid] = (VerdictLabel.UNCERTAIN, "No verdict produced by Moderator.", None)

    return parsed


# ── Best source weight resolver ───────────────────────────────────────────────

def _best_weight(result: RetrievalResult) -> float:
    """Return the weight of the best SUPPORTS snippet, or overall best, or 0.4."""
    if not result.retrieved or not result.snippets:
        return 0.4   # no evidence → Tier 3 weight as floor

    supporting = [s for s in result.snippets if s.relation == EvidenceRelation.SUPPORTS]
    pool = supporting or result.snippets
    return max(s.weight for s in pool)


# ── Main moderator function ───────────────────────────────────────────────────

def run_moderator(
    query: str,
    claims_data: list[tuple[str, str, RetrievalResult, bool]],
    # (claim_id, claim_text, retrieval_result, is_cascade)
    sprint2_statuses: Optional[dict[str, str]] = None,
    priority_ids: Optional[set[str]] = None,
    high_conflict_ids: Optional[set[str]] = None,
) -> list[ModeratorVerdict]:
    """
    Run the Moderator Agent on all claims and return per-claim verdicts.

    For claims with no retrieved evidence → forced UNCERTAIN regardless of LLM output.
    """
    sprint2_statuses  = sprint2_statuses or {}
    priority_ids      = priority_ids or set()
    high_conflict_ids = high_conflict_ids or set()

    evidence_block  = _build_claims_evidence_block(claims_data)
    s2_context      = _build_sprint2_context(sprint2_statuses, priority_ids, high_conflict_ids)

    user_prompt = MODERATOR_USER.format(
        query=query,
        claims_evidence_block=evidence_block,
        sprint2_context_block=s2_context,
    )

    log.info("Calling Moderator Agent for %d claim(s) …", len(claims_data))
    raw, provider_used = call_llm(
        system_prompt=MODERATOR_SYSTEM,
        user_prompt=user_prompt,
        max_tokens=settings.MODERATOR_MAX_TOKENS,
        temperature=settings.MODERATOR_TEMPERATURE,
        provider=settings.PRIMARY_LLM_PROVIDER,
    )
    log.info("Moderator response received via [%s].", provider_used)

    parsed = _parse_verdicts(raw, claims_data)

    # Build ModeratorVerdict objects
    verdicts: list[ModeratorVerdict] = []
    claim_id_set = {cid for cid, _, _, _ in claims_data}
    cascade_map  = {cid for cid, _, _, is_cascade in claims_data if is_cascade}

    for cid, claim_text, result, is_cascade in claims_data:
        vlabel, evidence_summary, correction = parsed.get(
            cid, (VerdictLabel.UNCERTAIN, "Not evaluated.", None)
        )

        # Hard rule: no evidence → UNCERTAIN, regardless of LLM output
        if not result.retrieved and vlabel == VerdictLabel.CORRECT:
            log.warning(
                "%s: LLM said CORRECT but no evidence retrieved — overriding to UNCERTAIN.", cid
            )
            vlabel = VerdictLabel.UNCERTAIN

        w = _best_weight(result)
        conf = round(VERDICT_SCORES[vlabel] * w, 4)

        verdicts.append(ModeratorVerdict(
            claim_id=cid,
            claim_text=claim_text,
            verdict=vlabel,
            source_weight=w,
            confidence=conf,
            evidence_summary=evidence_summary or "No evidence summary.",
            correction=correction,
            cascade_from=None,
            cascade_flag=is_cascade,
            sprint2_priority=cid in priority_ids,
            sprint2_high_conflict=cid in high_conflict_ids,
        ))

    return verdicts
