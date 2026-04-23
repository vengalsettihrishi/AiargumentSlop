"""
sprint2/parser.py
─────────────────
Parses raw LLM text from Sprint 2 agents into structured Pydantic objects.

Parsers:
  parse_skeptic_verdicts(text)   → list[SkepticVerdict]
  parse_proponent_rebuttal(text, claims) → list[ProponentRebuttal]
"""

from __future__ import annotations
import re
import logging
from typing import Optional

from sprint1.models import AtomicClaim
from sprint2.models import (
    SkepticVerdict, SkepticStatus,
    ProponentRebuttal, ProponentAction,
)

log = logging.getLogger(__name__)

# ── Status keyword map ────────────────────────────────────────────────────────
_STATUS_MAP: dict[str, SkepticStatus] = {
    "CONTESTED":  SkepticStatus.CONTESTED,
    "PLAUSIBLE":  SkepticStatus.PLAUSIBLE,
    "SUSPICIOUS": SkepticStatus.SUSPICIOUS,
    "ACCEPTED":   SkepticStatus.ACCEPTED,
}

_ACTION_MAP: dict[str, ProponentAction] = {
    "DEFEND":   ProponentAction.DEFEND,
    "REVISE":   ProponentAction.REVISE,
    "CONCEDE":  ProponentAction.CONCEDE,
}

# Matches: C2 → [CONTESTED]: specific reason here
# Tolerates both → and -> and optional spaces
_VERDICT_RE = re.compile(
    r"^(C\d+)\s*[→\-]+>?\s*\[(CONTESTED|PLAUSIBLE|SUSPICIOUS|ACCEPTED)\]\s*:?\s*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)

# Matches start of a proponent block: C4 → REVISE
_REBUTTAL_HEADER_RE = re.compile(
    r"^(C\d+)\s*[→\-]+>?\s*(DEFEND|REVISE|CONCEDE)",
    re.MULTILINE | re.IGNORECASE,
)


# ── Skeptic verdict parser ────────────────────────────────────────────────────

def parse_skeptic_verdicts(
    raw: str,
    expected_ids: Optional[set[str]] = None,
) -> list[SkepticVerdict]:
    """
    Parse raw skeptic output into a list of SkepticVerdict.
    Falls back to [PLAUSIBLE] with a logged warning for any missing claims.
    """
    verdicts: dict[str, SkepticVerdict] = {}

    for m in _VERDICT_RE.finditer(raw):
        cid        = m.group(1).strip()
        status_raw = m.group(2).strip().upper()
        reason     = m.group(3).strip() or "No reason provided."
        status     = _STATUS_MAP.get(status_raw, SkepticStatus.PLAUSIBLE)

        if cid in verdicts:
            log.debug("Duplicate verdict for %s — keeping first occurrence.", cid)
            continue
        verdicts[cid] = SkepticVerdict(claim_id=cid, status=status, reason=reason)

    # Fill missing claims with PLAUSIBLE
    if expected_ids:
        for cid in expected_ids:
            if cid not in verdicts:
                log.warning("Skeptic produced no verdict for %s — defaulting to PLAUSIBLE.", cid)
                verdicts[cid] = SkepticVerdict(
                    claim_id=cid,
                    status=SkepticStatus.PLAUSIBLE,
                    reason="No verdict produced by skeptic agent.",
                )

    result = sorted(verdicts.values(), key=lambda v: int(v.claim_id[1:]))
    log.info("Parsed %d skeptic verdicts.", len(result))
    return result


# ── Proponent rebuttal parser ─────────────────────────────────────────────────

def _extract_field(block: str, *labels: str) -> str:
    """Pull the first line following any of the given labels."""
    for label in labels:
        pattern = re.compile(
            rf"{re.escape(label)}\s*:?\s*(.+?)(?:\n|$)",
            re.IGNORECASE,
        )
        m = pattern.search(block)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def parse_proponent_rebuttal(
    raw: str,
    contested_claims: list[AtomicClaim],
) -> list[ProponentRebuttal]:
    """
    Parse the raw proponent rebuttal into a list of ProponentRebuttal.
    For any contested claim missing an explicit response, default to DEFEND
    with a note that no structured response was found.
    """
    expected_ids = {c.id for c in contested_claims}
    rebuttals: dict[str, ProponentRebuttal] = {}

    # Split the rebuttal into per-claim blocks using header positions
    headers = list(_REBUTTAL_HEADER_RE.finditer(raw))

    for i, hdr in enumerate(headers):
        cid        = hdr.group(1).strip()
        action_raw = hdr.group(2).strip().upper()
        action     = _ACTION_MAP.get(action_raw, ProponentAction.DEFEND)

        # Slice block text between this header and the next
        start = hdr.end()
        end   = headers[i + 1].start() if i + 1 < len(headers) else len(raw)
        block = raw[start:end].strip()

        if action == ProponentAction.REVISE:
            original = _extract_field(block, "Original")
            revised  = _extract_field(block, "Revised")
            reason   = _extract_field(block, "Reason")
            rebuttals[cid] = ProponentRebuttal(
                claim_id=cid,
                action=action,
                reasoning=reason,
                original_text=original or None,
                revised_text=revised or None,
            )
        elif action == ProponentAction.CONCEDE:
            reason = _extract_field(block, "Reason")
            rebuttals[cid] = ProponentRebuttal(
                claim_id=cid,
                action=action,
                reasoning=reason or block[:200],
            )
        else:  # DEFEND
            rebuttals[cid] = ProponentRebuttal(
                claim_id=cid,
                action=action,
                reasoning=block[:500] if block else "Defense reasoning not parsed.",
            )

    # Fill missing contested claims with a default DEFEND
    for cid in expected_ids:
        if cid not in rebuttals:
            log.warning("No rebuttal found for contested claim %s — defaulting to DEFEND.", cid)
            rebuttals[cid] = ProponentRebuttal(
                claim_id=cid,
                action=ProponentAction.DEFEND,
                reasoning="No structured rebuttal produced by Proponent agent.",
            )

    result = sorted(rebuttals.values(), key=lambda r: int(r.claim_id[1:]))
    log.info("Parsed %d proponent rebuttal(s).", len(result))
    return result
