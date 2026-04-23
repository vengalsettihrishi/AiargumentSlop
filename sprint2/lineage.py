"""
sprint2/lineage.py
──────────────────
Lineage Record initialisation and post-debate finalisation.

Functions:
  init_lineage(canonical_claims, dedup_report) → dict[str, LineageRecord]
  finalise_lineage(lineage_map, debate_rounds) → (accepted, std_retrieval, priority, high_conflict)
  render_lineage_table(lineage_map)             — rich console display
"""

from __future__ import annotations
import logging

from rich.console import Console
from rich.table import Table
from rich import box

from sprint1.models import AtomicClaim
from sprint2.models import (
    LineageRecord, DedupReport, DebateRound,
    CombinedStatus,
)

log    = logging.getLogger(__name__)
console = Console()


# ── Initialisation ────────────────────────────────────────────────────────────

def init_lineage(
    canonical_claims: list[AtomicClaim],
    dedup_report: DedupReport,
) -> dict[str, LineageRecord]:
    """
    Open a LineageRecord for every canonical claim.
    Alias IDs are attached where dedup found clusters.
    Returns a dict keyed by claim_id for O(1) access.
    """
    # Build alias lookup: canonical_id → [alias_ids]
    alias_lookup: dict[str, list[str]] = {}
    for cluster in dedup_report.clusters:
        alias_lookup.setdefault(cluster.canonical_id, []).extend(cluster.alias_ids)

    lineage_map: dict[str, LineageRecord] = {}
    for claim in canonical_claims:
        aliases = alias_lookup.get(claim.id, [])
        record = LineageRecord(
            claim_id=claim.id,
            canonical_text=claim.text,
            current_text=claim.text,
            sprint1_marker=claim.marker.value,
            alias_ids=aliases,
        )
        lineage_map[claim.id] = record
        log.debug("Lineage initialised: %s (aliases: %s)", claim.id, aliases or "none")

    log.info("Lineage records initialised for %d canonical claim(s).", len(lineage_map))
    return lineage_map


# ── Post-debate classification ────────────────────────────────────────────────

def finalise_lineage(
    lineage_map: dict[str, LineageRecord],
    debate_rounds: list[DebateRound],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Classify every canonical claim into one of four output buckets.

    Returns:
        (fully_accepted, standard_retrieval, priority_retrieval, high_conflict)
    """
    fully_accepted:     list[str] = []
    standard_retrieval: list[str] = []
    priority_retrieval: list[str] = []
    high_conflict:      list[str] = []

    for cid, rec in lineage_map.items():
        if rec.high_conflict:
            high_conflict.append(cid)
        elif rec.final_debate_status == CombinedStatus.ACCEPTED:
            fully_accepted.append(cid)
        elif rec.priority_retrieval:
            priority_retrieval.append(cid)
        else:
            standard_retrieval.append(cid)

    # Sort by numeric ID
    def _sort(lst: list[str]) -> list[str]:
        return sorted(lst, key=lambda x: int(x[1:]))

    return (
        _sort(fully_accepted),
        _sort(standard_retrieval),
        _sort(priority_retrieval),
        _sort(high_conflict),
    )


# ── Rich display ──────────────────────────────────────────────────────────────

def render_lineage_table(lineage_map: dict[str, LineageRecord]) -> None:
    """Render the post-debate lineage records as a rich table."""
    table = Table(
        title="[bold white]LINEAGE RECORDS — POST DEBATE[/bold white]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        expand=True,
    )
    table.add_column("ID",       width=5,  style="dim")
    table.add_column("Status",   width=22)
    table.add_column("Rounds",   width=7)
    table.add_column("Revised?", width=9)
    table.add_column("Priority", width=9)
    table.add_column("HiConf",   width=8)
    table.add_column("Current Text", ratio=1)

    status_colors = {
        CombinedStatus.ACCEPTED:        "green",
        CombinedStatus.PLAUSIBLE:       "cyan",
        CombinedStatus.SUSPICIOUS:      "yellow",
        CombinedStatus.CONTESTED:       "red",
        CombinedStatus.CONTESTED_DUAL:  "bold red",
        CombinedStatus.HIGH_CONFLICT:   "bold magenta",
    }

    for cid in sorted(lineage_map.keys(), key=lambda x: int(x[1:])):
        rec = lineage_map[cid]
        sc  = status_colors.get(rec.final_debate_status, "white")
        revised = any(e.revised_text for e in rec.round_log)
        table.add_row(
            cid,
            f"[{sc}]{rec.final_debate_status.value}[/{sc}]",
            str(len(rec.round_log)),
            "✓" if revised else "—",
            "🔴" if rec.priority_retrieval else "—",
            "⚠" if rec.high_conflict else "—",
            rec.current_text[:80] + ("…" if len(rec.current_text) > 80 else ""),
        )

    console.print(table)


def render_lineage_init_table(lineage_map: dict[str, LineageRecord]) -> None:
    """Display the freshly initialised lineage records before debate begins."""
    table = Table(
        title="[bold white]LINEAGE INIT — PRE-DEBATE[/bold white]",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold white",
    )
    table.add_column("ID",      width=5,  style="dim")
    table.add_column("Marker",  width=14)
    table.add_column("Aliases", width=12)
    table.add_column("Text")

    for cid in sorted(lineage_map.keys(), key=lambda x: int(x[1:])):
        rec = lineage_map[cid]
        marker_col = "magenta" if rec.sprint1_marker == "SUPERLATIVE" else \
                     "yellow"  if rec.sprint1_marker == "TIME-SENSITIVE" else "dim"
        table.add_row(
            cid,
            f"[{marker_col}]{rec.sprint1_marker or '—'}[/{marker_col}]",
            ", ".join(rec.alias_ids) if rec.alias_ids else "none",
            rec.canonical_text[:80],
        )
    console.print(table)
