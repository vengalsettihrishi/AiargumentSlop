"""
sprint1/parser.py
─────────────────
Parses the raw LLM text output from the Decomposition Analyst into
structured Pydantic objects (AtomicClaim, DependencyEdge).

Design decisions:
  - Regex-based extraction is preferred over JSON mode so the prompt stays
    human-readable and the LLM produces auditable text.
  - Strict extraction: any claim that cannot be parsed is logged and skipped.
  - Dependency parser handles both "Cx → Cy, Cz" and "Cx -> Cy" notations.
"""

from __future__ import annotations
import re
import logging
from typing import Optional

from sprint1.models import AtomicClaim, ClaimMarker, DependencyEdge

log = logging.getLogger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────

# Matches: C1: Some claim text [SUPERLATIVE]
_CLAIM_RE = re.compile(
    r"^(C\d+):\s+(.+?)(?:\s+\[(SUPERLATIVE|TIME-SENSITIVE)\])?$",
    re.MULTILINE,
)

# Matches: C1 → C3, C5   or   C1 -> C3, C5   or   C1 → (none)
_DEP_RE = re.compile(
    r"^(C\d+)\s*[→\-]+>?\s*(.*?)$",
    re.MULTILINE,
)

_MARKER_MAP = {
    "SUPERLATIVE":    ClaimMarker.SUPERLATIVE,
    "TIME-SENSITIVE": ClaimMarker.TIME_SENSITIVE,
}


# ── Section splitter ──────────────────────────────────────────────────────────

def _extract_section(text: str, label: str) -> str:
    """Extract text following a section label until the next label or end."""
    pattern = re.compile(
        rf"\[{re.escape(label)}\](.*?)(?=\[|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


# ── Public parsers ─────────────────────────────────────────────────────────────

def parse_claims(raw_decomposition: str) -> list[AtomicClaim]:
    """Parse [ATOMIC CLAIMS] section into AtomicClaim objects."""
    section = _extract_section(raw_decomposition, "ATOMIC CLAIMS")
    if not section:
        log.warning("Could not locate [ATOMIC CLAIMS] section in LLM output.")
        return []

    claims: list[AtomicClaim] = []
    for m in _CLAIM_RE.finditer(section):
        cid, text, marker_raw = m.group(1), m.group(2).strip(), m.group(3)
        marker = _MARKER_MAP.get(marker_raw or "", ClaimMarker.NONE)
        claims.append(AtomicClaim(id=cid, text=text, marker=marker))

    if not claims:
        log.error("Zero claims parsed — check LLM output format.")
    else:
        log.info("Parsed %d atomic claim(s).", len(claims))

    return claims


def parse_dependency_graph(
    raw_decomposition: str,
    known_claim_ids: Optional[set[str]] = None,
) -> list[DependencyEdge]:
    """Parse [DEPENDENCY GRAPH] section into DependencyEdge objects."""
    section = _extract_section(raw_decomposition, "DEPENDENCY GRAPH")
    if not section:
        log.warning("Could not locate [DEPENDENCY GRAPH] section in LLM output.")
        return []

    edges: list[DependencyEdge] = []
    for m in _DEP_RE.finditer(section):
        parent = m.group(1).strip()
        rhs = m.group(2).strip()

        # "(none)" or empty → no children
        if not rhs or rhs.lower() == "(none)":
            children: list[str] = []
        else:
            children = [c.strip() for c in re.split(r"[,\s]+", rhs) if c.strip()]

        # Validate against known IDs if provided
        if known_claim_ids:
            invalid = [c for c in children if c not in known_claim_ids]
            if invalid:
                log.warning(
                    "Dependency edge %s references unknown claim IDs: %s — skipping those.",
                    parent, invalid,
                )
                children = [c for c in children if c in known_claim_ids]

        edges.append(DependencyEdge(parent=parent, children=children))

    log.info("Parsed %d dependency edge(s).", len(edges))
    return edges


def parse_proponent_answer(raw_proponent: str) -> str:
    """Strip the [PROPONENT ANSWER] label and return clean prose."""
    section = _extract_section(raw_proponent, "PROPONENT ANSWER")
    return section if section else raw_proponent.strip()
