"""
sprint4/synthesizer.py
──────────────────────
Synthesis Agent + context assemblers.

Responsibilities:
  1. Build the structured claim block for the LLM prompt
     (all claims annotated with their Sprint 3 verdict + evidence)
  2. Build the debate context summary from Sprint 2
  3. Call the Synthesis LLM (primary provider, max accuracy)
  4. Parse the CLAIMS EVALUATION table from the response
  5. Extract the FINAL ANSWER prose

Parser strategy:
  Section-aware regex: finds CLAIMS EVALUATION: block, then FINAL ANSWER: block.
  Falls back gracefully if the LLM merges or slightly reformats sections.
"""

from __future__ import annotations
import logging
import re
from typing import Optional

from llm_client import call_llm
from config import settings
from sprint1.models import Sprint1Output
from sprint2.models import Sprint2Output
from sprint3.models import Sprint3Output, VerdictLabel
from sprint4.models import ClaimSummaryRow
from sprint4.prompts import SYNTHESIS_SYSTEM, SYNTHESIS_USER

log = logging.getLogger(__name__)


# ── Context block builders ────────────────────────────────────────────────────

def _build_claims_block(
    sprint1: Sprint1Output,
    sprint2: Sprint2Output,
    sprint3: Sprint3Output,
) -> str:
    """
    Produce a compact, structured claim listing for the Synthesis prompt.
    Each claim shows: text, Sprint1 marker, Sprint2 debate status,
    Sprint3 verdict, confidence, evidence summary, and correction if any.
    """
    # Build lookup maps
    s1_map  = {c.id: c for c in sprint1.claims}
    s2_lin  = {rec.claim_id: rec for rec in sprint2.lineage_records}
    s3_map  = {v.claim_id: v for v in sprint3.verdicts}

    # Use Sprint 2 canonical IDs as the authoritative claim set
    all_ids = sorted(
        set(s3_map.keys()) | set(s1_map.keys()),
        key=lambda x: int(x[1:]),
    )

    lines: list[str] = []
    for cid in all_ids:
        s3v     = s3_map.get(cid)
        s1c     = s1_map.get(cid)
        s2rec   = s2_lin.get(cid)

        # Prefer Sprint3 text (may be revised by Sprint 2 proponent)
        text    = (s3v.claim_text if s3v else "") or (s1c.text if s1c else "")
        marker  = s1c.marker.value if s1c else ""
        s2stat  = s2rec.final_debate_status.value if s2rec else "—"
        verdict = s3v.verdict.value if s3v else "UNCERTAIN"
        conf    = f"{s3v.confidence:.2f}" if s3v else "0.00"
        evid    = s3v.evidence_summary[:120] if s3v else "No evidence."
        corr    = f" | Correction: {s3v.correction}" if (s3v and s3v.correction) else ""
        cascade = ""
        if s3v and s3v.cascade_flag and s3v.cascade_from:
            cascade = f" [CASCADE from {s3v.cascade_from}]"
        hconf   = " [HIGH CONFLICT]" if (s3v and s3v.sprint2_high_conflict) else ""
        mark_str = f" [{marker}]" if marker else ""

        lines.append(
            f"{cid}{mark_str}: {text}\n"
            f"  Debate: {s2stat}  |  Verdict: {verdict}{cascade}{hconf}  |  Conf: {conf}\n"
            f"  Evidence: {evid}{corr}"
        )

    return "\n\n".join(lines)


def _build_debate_context(sprint2: Sprint2Output) -> str:
    lines = [
        f"Debate rounds completed : {sprint2.exit_round} / 3",
        f"Final convergence score : {sprint2.final_convergence_score:.1%}",
        f"Exit reason             : {sprint2.exit_reason.value if sprint2.exit_reason else 'N/A'}",
        f"High-conflict claims    : {', '.join(sprint2.high_conflict_ids) or 'none'}",
        f"Priority retrieval flags: {', '.join(sprint2.priority_retrieval_ids) or 'none'}",
        f"Aliases retired (dedup) : {sprint2.dedup_report.total_aliases_retired}",
    ]
    return "\n".join(lines)


# ── LLM call ─────────────────────────────────────────────────────────────────

def run_synthesis_llm(
    sprint1: Sprint1Output,
    sprint2: Sprint2Output,
    sprint3: Sprint3Output,
) -> str:
    """Call the Synthesis Agent LLM and return raw text output."""
    claims_block   = _build_claims_block(sprint1, sprint2, sprint3)
    debate_context = _build_debate_context(sprint2)

    user_prompt = SYNTHESIS_USER.format(
        query=sprint1.query,
        proponent_answer=sprint1.proponent_answer,
        claims_block=claims_block,
        debate_context=debate_context,
    )

    log.info("Calling Synthesis Agent …")
    raw, provider = call_llm(
        system_prompt=SYNTHESIS_SYSTEM,
        user_prompt=user_prompt,
        max_tokens=settings.SYNTHESIS_MAX_TOKENS,
        temperature=settings.SYNTHESIS_TEMPERATURE,
        provider=settings.PRIMARY_LLM_PROVIDER,
    )
    log.info("Synthesis response received via [%s].", provider)
    return raw


# ── Response parsers ──────────────────────────────────────────────────────────

# Matches: C2: <text> -> INCORRECT [CASCADE from C1]
_CLAIM_ROW_RE = re.compile(
    r"^\s*(C\d+)[^:]*:\s*(.+?)\s*->\s*(CORRECT|INCORRECT|UNCERTAIN)"
    r"(?:\s*\[CASCADE from (C\d+)\])?"
    r"(?:\s*\[.*?\])?",   # consume any extra badges like [HIGH CONFLICT]
    re.IGNORECASE | re.MULTILINE,
)
# Matches: Evidence: <text> | Correction: <text>
_EVIDENCE_RE = re.compile(
    r"Evidence\s*:\s*(.+?)(?:\s*\|\s*Correction\s*:\s*(.+))?$",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_section(raw: str, label: str) -> str:
    """
    Extract text between `label:` and the next all-caps section header or end-of-string.
    """
    pattern = re.compile(
        rf"{re.escape(label)}\s*:?\s*\n(.*?)(?=\n[A-Z][A-Z\s]+:|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(raw)
    return m.group(1).strip() if m else ""


def parse_synthesis_output(
    raw: str,
    sprint1: Sprint1Output,
    sprint3: Sprint3Output,
) -> tuple[list[ClaimSummaryRow], str]:
    """
    Parse LLM output into:
      - list[ClaimSummaryRow]   — claims evaluation table
      - str                     — refined final answer prose

    Falls back gracefully on partial LLM output.
    """
    s1_map = {c.id: c for c in sprint1.claims}
    s3_map = {v.claim_id: v for v in sprint3.verdicts}

    # ── Extract FINAL ANSWER section ────────────────────────────────────────
    final_answer = _extract_section(raw, "FINAL ANSWER")
    if not final_answer:
        # Second-pass: everything after the last CLAIMS EVALUATION block
        parts = re.split(r"FINAL ANSWER\s*:?\s*\n", raw, flags=re.IGNORECASE)
        final_answer = parts[-1].strip() if len(parts) > 1 else ""

    # ── Parse claim rows ─────────────────────────────────────────────────────
    rows: list[ClaimSummaryRow] = []
    seen_ids: set[str] = set()

    # Split into per-claim chunks for evidence extraction
    claim_chunks: dict[str, str] = {}
    current_id: Optional[str] = None
    current_lines: list[str] = []

    for line in raw.splitlines():
        m = _CLAIM_ROW_RE.match(line)
        if m:
            if current_id:
                claim_chunks[current_id] = "\n".join(current_lines)
            current_id = m.group(1)
            current_lines = [line]
        elif current_id:
            current_lines.append(line)

    if current_id:
        claim_chunks[current_id] = "\n".join(current_lines)

    # Build ClaimSummaryRow for each parsed chunk
    for cid, chunk in claim_chunks.items():
        m = _CLAIM_ROW_RE.search(chunk)
        if not m:
            continue

        text_raw    = m.group(2).strip()
        verdict_raw = m.group(3).strip().upper()
        cascade_from = m.group(4)

        # Evidence + correction
        ev_match   = _EVIDENCE_RE.search(chunk)
        evidence   = ev_match.group(1).strip() if ev_match else ""
        correction = ev_match.group(2).strip() if (ev_match and ev_match.group(2)) else None

        # Resolve against Sprint 3 for accurate confidence/weight
        s3v = s3_map.get(cid)
        s1c = s1_map.get(cid)

        rows.append(ClaimSummaryRow(
            claim_id=cid,
            claim_text=text_raw or (s3v.claim_text if s3v else ""),
            sprint1_marker=s1c.marker.value if s1c else "",
            debate_status="",
            verdict=verdict_raw,
            confidence=s3v.confidence if s3v else 0.0,
            source_weight=s3v.source_weight if s3v else 0.0,
            evidence_summary=evidence or (s3v.evidence_summary if s3v else ""),
            correction=correction or (s3v.correction if s3v else None),
            cascade_flag=bool(cascade_from) or (s3v.cascade_flag if s3v else False),
            cascade_from=cascade_from or (s3v.cascade_from if s3v else None),
            high_conflict=s3v.sprint2_high_conflict if s3v else False,
        ))
        seen_ids.add(cid)

    # Fill any claims not captured by the LLM (use Sprint 3 ground truth)
    for s3v in sprint3.verdicts:
        if s3v.claim_id not in seen_ids:
            s1c = s1_map.get(s3v.claim_id)
            rows.append(ClaimSummaryRow(
                claim_id=s3v.claim_id,
                claim_text=s3v.claim_text,
                sprint1_marker=s1c.marker.value if s1c else "",
                verdict=s3v.verdict.value,
                confidence=s3v.confidence,
                source_weight=s3v.source_weight,
                evidence_summary=s3v.evidence_summary,
                correction=s3v.correction,
                cascade_flag=s3v.cascade_flag,
                cascade_from=s3v.cascade_from,
                high_conflict=s3v.sprint2_high_conflict,
            ))

    rows.sort(key=lambda r: int(r.claim_id[1:]))
    return rows, final_answer
