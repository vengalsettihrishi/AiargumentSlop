"""
sprint2/runner.py
─────────────────
Orchestrates the complete Sprint 2 pipeline:

  Stage 0 — Load Sprint 1 output (or accept it as argument)
  Stage 1 — Semantic Deduplication   (DEDUP ANALYST)
  Stage 2 — Lineage Record Init
  Stage 3 — Adversarial Debate       (SKEPTIC-A × SKEPTIC-B × PROPONENT)
             Up to 3 rounds with convergence tracking
  Stage 4 — Post-Debate Finalisation
  Stage 5 — Persist Sprint2Output JSON

Public function: run_sprint2(sprint1_output) → Sprint2Output
"""

from __future__ import annotations
import json
import logging
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box

from config import settings
from sprint1.models import Sprint1Output
from sprint2.models import (
    Sprint2Output, DebateExitReason, CombinedStatus,
)
from sprint2.dedup import run_dedup
from sprint2.lineage import init_lineage, finalise_lineage, render_lineage_init_table, render_lineage_table
from sprint2.debate import run_debate, MAX_ROUNDS, CONVERGENCE_THRESHOLD, STAGNATION_DELTA

log = logging.getLogger(__name__)
console = Console()


# ── Dedup display ─────────────────────────────────────────────────────────────

def _display_dedup_report(report) -> None:
    console.print(Rule("[bold blue]PRE-DEBATE — DEDUP ANALYST[/bold blue]"))
    if not report.clusters:
        console.print("  [dim]No duplicate clusters found — all claims are canonical.[/dim]")
    else:
        for i, cluster in enumerate(report.clusters, 1):
            console.print(
                f"  Cluster {i}: CANONICAL → [bold]{cluster.canonical_id}[/bold]: "
                f"{cluster.canonical_text[:70]}"
            )
            for aid, atxt, sim in zip(
                cluster.alias_ids, cluster.alias_texts, cluster.similarity_scores
            ):
                console.print(
                    f"            ALIAS → [dim]{aid}[/dim] ({sim:.3f}): {atxt[:60]}"
                )
            for upd in cluster.graph_updates:
                console.print(f"            [dim]Graph: {upd}[/dim]")

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Key",   style="dim")
    table.add_column("Value", style="green")
    table.add_row("Input claims",    str(report.total_input_claims))
    table.add_row("Canonical claims",str(report.total_canonical_claims))
    table.add_row("Aliases retired", str(report.total_aliases_retired))
    table.add_row("Canonical set",   ", ".join(report.canonical_ids))
    console.print(table)


def _display_final_summary(output: Sprint2Output) -> None:
    console.print(Rule("[bold white]SPRINT 2 — FINAL DEBATE SUMMARY[/bold white]"))
    table = Table(box=box.ROUNDED, show_header=False, expand=False)
    table.add_column("Field", style="dim", width=32)
    table.add_column("Value", style="bold")
    table.add_row("Final Convergence Score",
                  f"{output.final_convergence_score:.1%}")
    table.add_row("Exit Reason",
                  output.exit_reason.value if output.exit_reason else "—")
    table.add_row("Exit Round",
                  str(output.exit_round))
    table.add_row("Fully Accepted",
                  ", ".join(output.fully_accepted_ids) or "none")
    table.add_row("Standard Retrieval",
                  ", ".join(output.standard_retrieval_ids) or "none")
    table.add_row("[bold red]Priority Retrieval[/bold red]",
                  ", ".join(output.priority_retrieval_ids) or "none")
    table.add_row("[bold magenta]High Conflict[/bold magenta]",
                  ", ".join(output.high_conflict_ids) or "none")
    console.print(table)


# ── Exit reason resolver ──────────────────────────────────────────────────────

def _resolve_exit_reason(
    rounds_run: int,
    final_score: float,
    any_stagnation: bool,
) -> DebateExitReason:
    if final_score >= CONVERGENCE_THRESHOLD and rounds_run < MAX_ROUNDS:
        return DebateExitReason.EARLY_EXIT
    if any_stagnation:
        return DebateExitReason.STAGNATION
    return DebateExitReason.FULL_ROUNDS


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_sprint2(sprint1_output: Sprint1Output) -> Sprint2Output:
    """
    Execute the full Sprint 2 pipeline.
    Accepts a Sprint1Output object directly (pipeline mode)
    or loads from ./outputs/sprint1_output.json if None.
    """
    query  = sprint1_output.query
    claims = sprint1_output.claims
    graph  = sprint1_output.dependency_graph

    console.print(Panel(
        f"[bold]Query:[/bold] {query}\n"
        f"[bold]Claims from Sprint 1:[/bold] {len(claims)}",
        title="[bold magenta]🔥 SPRINT 2 — ADVERSARIAL DEBATE SYSTEM[/bold magenta]",
        border_style="magenta",
        padding=(1, 2),
    ))

    # ── Stage 1: Semantic Deduplication ──────────────────────────────────────
    console.print(f"\n[bold blue]▶ Stage 1: Semantic Deduplication …[/bold blue]")
    t0 = time.perf_counter()
    dedup_report, canonical_claims, updated_graph = run_dedup(claims, graph)
    console.print(f"  [dim]Done in {time.perf_counter()-t0:.1f}s[/dim]")
    _display_dedup_report(dedup_report)

    # ── Stage 2: Lineage Initialisation ──────────────────────────────────────
    console.print(f"\n[bold white]▶ Stage 2: Initialising Lineage Records …[/bold white]")
    lineage_map = init_lineage(canonical_claims, dedup_report)
    render_lineage_init_table(lineage_map)

    # ── Stage 3: Adversarial Debate ───────────────────────────────────────────
    console.print(f"\n[bold red]▶ Stage 3: Adversarial Debate ({len(canonical_claims)} canonical claims) …[/bold red]")
    debate_rounds = run_debate(
        query=query,
        canonical_claims=canonical_claims,
        dep_graph=updated_graph,
        lineage_map=lineage_map,
    )

    # ── Stage 4: Finalise ─────────────────────────────────────────────────────
    console.print(f"\n[bold white]▶ Stage 4: Finalising results …[/bold white]")

    accepted, std_ret, prio_ret, high_conf = finalise_lineage(lineage_map, debate_rounds)

    rounds_run     = len(debate_rounds)
    final_conv     = debate_rounds[-1].convergence.score if debate_rounds else 0.0
    any_stagnation = any(rec.high_conflict for rec in lineage_map.values())
    exit_reason    = _resolve_exit_reason(rounds_run, final_conv, any_stagnation)

    output = Sprint2Output(
        query=query,
        dedup_report=dedup_report,
        lineage_records=list(lineage_map.values()),
        debate_rounds=debate_rounds,
        final_convergence_score=final_conv,
        exit_reason=exit_reason,
        exit_round=rounds_run,
        fully_accepted_ids=accepted,
        standard_retrieval_ids=std_ret,
        priority_retrieval_ids=prio_ret,
        high_conflict_ids=high_conf,
    )

    render_lineage_table(lineage_map)
    _display_final_summary(output)

    # ── Stage 5: Persist ──────────────────────────────────────────────────────
    out_dir = settings.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sprint2_output.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output.model_dump(), f, indent=2, default=str)

    console.print(f"\n[dim green]✓ Sprint 2 output saved → {out_path}[/dim green]")
    return output


# ── Standalone loader ─────────────────────────────────────────────────────────

def load_sprint1_output() -> Sprint1Output:
    """Load Sprint 1 output JSON from disk."""
    path = settings.OUTPUT_DIR / "sprint1_output.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Sprint 1 output not found at {path}. Run Sprint 1 first."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Sprint1Output.model_validate(data)
