"""
sprint4/runner.py
─────────────────
Orchestrates the complete Sprint 4 pipeline:

  Stage 0 — Accept Sprint 1, 2, 3 outputs (or load from disk)
  Stage 1 — Build Synthesis LLM context and call the agent
  Stage 2 — Parse claims evaluation table from LLM response
  Stage 3 — Compute system metrics from Sprint 3 ground truth
             (never from LLM output — metrics must be exact)
  Stage 4 — Render terminal transparency report
  Stage 5 — Persist Sprint4Output JSON + plain-text report

Public function: run_sprint4(s1, s2, s3) -> Sprint4Output
"""

from __future__ import annotations
import json
import logging
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from config import settings
from sprint1.models import Sprint1Output
from sprint2.models import Sprint2Output
from sprint3.models import Sprint3Output, VerdictLabel
from sprint4.models import (
    Sprint4Output, SystemMetrics,
    HallucinationRisk, DependencyIntegrity,
)
from sprint4.synthesizer import run_synthesis_llm, parse_synthesis_output
from sprint4.report import render_full_report, save_plain_report

log = logging.getLogger(__name__)
console = Console()


# ── Metrics computation (ground-truth only) ───────────────────────────────────

def _compute_metrics(
    sprint2: Sprint2Output,
    sprint3: Sprint3Output,
) -> SystemMetrics:
    """
    Compute all metrics from Sprint 2 and Sprint 3 ground-truth data.
    NEVER derived from LLM output — counts must be exact.
    """
    verdicts = sprint3.verdicts
    n        = len(verdicts)

    correct   = sum(1 for v in verdicts if v.verdict == VerdictLabel.CORRECT)
    incorrect = sum(1 for v in verdicts if v.verdict == VerdictLabel.INCORRECT)
    uncertain = sum(1 for v in verdicts if v.verdict == VerdictLabel.UNCERTAIN)
    cascaded  = sum(1 for v in verdicts if v.cascade_flag)

    # Confidence = Bayesian aggregate = mean of all Confidence(Claim)
    confidences    = [v.confidence for v in verdicts]
    source_weights = [v.source_weight for v in verdicts]
    mean_conf = sum(confidences) / n if n else 0.0
    avg_weight = sum(source_weights) / n if n else 0.0

    # Sprint 2 debate metrics
    rounds_used    = sprint2.exit_round
    final_conv     = sprint2.final_convergence_score
    high_conf_ids  = sprint2.high_conflict_ids

    # Build metric object (model_validator computes categorical fields)
    m = SystemMetrics(
        total_claims=n,
        correct_count=correct,
        incorrect_count=incorrect,
        uncertain_count=uncertain,
        cascade_flagged=cascaded,
        mean_confidence=round(mean_conf, 4),
        avg_source_weight=round(avg_weight, 4),
        debate_rounds_used=rounds_used,
        final_convergence=final_conv,
        high_conflict_ids=list(high_conf_ids),
    )
    return m


# ── Debate context for display ─────────────────────────────────────────────────

def _attach_debate_statuses(
    claim_rows,
    sprint2: Sprint2Output,
) -> None:
    """Fill in the debate_status field on each ClaimSummaryRow from lineage."""
    s2_lin = {rec.claim_id: rec.final_debate_status.value for rec in sprint2.lineage_records}
    for row in claim_rows:
        row.debate_status = s2_lin.get(row.claim_id, "")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_sprint4(
    sprint1_output: Sprint1Output,
    sprint2_output: Sprint2Output,
    sprint3_output: Sprint3Output,
) -> Sprint4Output:
    """
    Execute the full Sprint 4 pipeline.
    Returns a Sprint4Output object, also persisted to outputs/.
    """
    query = sprint1_output.query

    console.print(Panel(
        f"[bold]Query:[/bold] {query}\n"
        f"[bold]Total verdicts from Sprint 3:[/bold] {len(sprint3_output.verdicts)}  "
        f"[bold green]Correct:[/bold green] {len(sprint3_output.correct_ids)}  "
        f"[bold red]Incorrect:[/bold red] {len(sprint3_output.incorrect_ids)}  "
        f"[bold yellow]Uncertain:[/bold yellow] {len(sprint3_output.uncertain_ids)}",
        title="[bold green]✅ SPRINT 4 — SYNTHESIS & TRANSPARENCY REPORT[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))

    # ── Stage 1: Synthesis LLM call ──────────────────────────────────────────
    console.print("\n[bold white]▶ Stage 1: Synthesis Agent rewriting answer …[/bold white]")
    t0 = time.perf_counter()
    raw_synthesis = run_synthesis_llm(sprint1_output, sprint2_output, sprint3_output)
    console.print(f"  [dim]Synthesis complete in {time.perf_counter()-t0:.1f}s[/dim]")

    # ── Stage 2: Parse output ─────────────────────────────────────────────────
    console.print("\n[bold white]▶ Stage 2: Parsing claims evaluation table …[/bold white]")
    claim_rows, refined_answer = parse_synthesis_output(
        raw_synthesis, sprint1_output, sprint3_output
    )
    _attach_debate_statuses(claim_rows, sprint2_output)
    console.print(f"  [dim]{len(claim_rows)} claim rows parsed.[/dim]")

    # ── Stage 3: Compute metrics (ground truth only) ──────────────────────────
    console.print("\n[bold white]▶ Stage 3: Computing system metrics …[/bold white]")
    metrics = _compute_metrics(sprint2_output, sprint3_output)
    console.print(
        f"  [dim]Accuracy: {metrics.accuracy:.1%}  |  "
        f"Hallucination rate: {metrics.hallucination_rate:.1%}  |  "
        f"Risk: {metrics.hallucination_risk.value}  |  "
        f"Integrity: {metrics.dependency_integrity.value}[/dim]"
    )

    # ── Stage 4: Build output object ─────────────────────────────────────────
    output = Sprint4Output(
        query=query,
        refined_answer=refined_answer,
        claim_rows=claim_rows,
        metrics=metrics,
        dedup_aliases_retired=sprint2_output.dedup_report.total_aliases_retired,
        debate_exit_reason=(
            sprint2_output.exit_reason.value
            if sprint2_output.exit_reason else ""
        ),
    )

    # ── Stage 5a: Rich terminal report ───────────────────────────────────────
    console.print("\n[bold white]▶ Stage 4: Rendering transparency report …[/bold white]\n")
    render_full_report(output)

    # ── Stage 5b: Persist outputs ─────────────────────────────────────────────
    out_dir = settings.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = out_dir / "sprint4_output.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output.model_dump(), f, indent=2, default=str)

    # Plain-text transparency report
    txt_path = save_plain_report(output, out_dir)

    console.print(f"\n[dim green]✓ Sprint 4 JSON saved     → {json_path}[/dim green]")
    console.print(f"[dim green]✓ Transparency report     → {txt_path}[/dim green]")
    console.print(f"[dim green]✓ Full pipeline complete.[/dim green]")

    return output


# ── Standalone loaders ────────────────────────────────────────────────────────

def load_sprint3_output() -> Sprint3Output:
    path = settings.OUTPUT_DIR / "sprint3_output.json"
    if not path.exists():
        raise FileNotFoundError(f"Sprint 3 output not found at {path}. Run Sprint 3 first.")
    with open(path, encoding="utf-8") as f:
        return Sprint3Output.model_validate(json.load(f))

def load_sprint2_output() -> Sprint2Output:
    path = settings.OUTPUT_DIR / "sprint2_output.json"
    if not path.exists():
        raise FileNotFoundError(f"Sprint 2 output not found at {path}. Run Sprint 2 first.")
    with open(path, encoding="utf-8") as f:
        return Sprint2Output.model_validate(json.load(f))

def load_sprint1_output() -> Sprint1Output:
    path = settings.OUTPUT_DIR / "sprint1_output.json"
    if not path.exists():
        raise FileNotFoundError(f"Sprint 1 output not found at {path}. Run Sprint 1 first.")
    with open(path, encoding="utf-8") as f:
        return Sprint1Output.model_validate(json.load(f))
