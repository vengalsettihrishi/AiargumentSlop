"""
sprint3/runner.py
─────────────────
Orchestrates the full Sprint 3 pipeline:

  Stage 0 — Load Sprint 1 + Sprint 2 outputs
  Stage 1 — Determine which claims need retrieval
            Priority: [HIGH CONFLICT] → [PRIORITY RETRIEVAL] → standard unresolved
            [ACCEPTED] with [TIME-SENSITIVE] marker also re-checked
  Stage 2 — Multi-source RAG retrieval (Tavily + Serper + You.com)
  Stage 3 — Moderator Agent: credibility-weighted verdicts
  Stage 4 — Cascade Failure Propagation
  Stage 5 — Metrics computation
  Stage 6 — Persist Sprint3Output JSON + rich console report

Public function: run_sprint3(sprint1_output, sprint2_output) → Sprint3Output
"""

from __future__ import annotations
import json
import logging
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box

from config import settings
from sprint1.models import Sprint1Output, ClaimMarker
from sprint2.models import Sprint2Output, CombinedStatus
from sprint3.models import (
    Sprint3Output, Sprint3Metrics, VerdictLabel, VERDICT_SCORES,
    ModeratorVerdict,
)
from sprint3.retrieval import run_retrieval
from sprint3.moderator import run_moderator
from sprint3.cascade import run_cascade

log = logging.getLogger(__name__)
console = Console()


# ── Claim selection ───────────────────────────────────────────────────────────

def _select_claims_for_retrieval(
    sprint1: Sprint1Output,
    sprint2: Sprint2Output,
) -> tuple[
    list[tuple[str, str]],  # all claims needing retrieval → (id, text)
    set[str],               # priority retrieval ids
    set[str],               # high conflict ids
    set[str],               # sprint2-accepted ids (skip retrieval unless TIME-SENSITIVE)
]:
    """
    Determine which claims require retrieval and their priority tier.

    Rules from spec:
      - All claims NOT marked [ACCEPTED] by both agents → retrieve
      - [ACCEPTED] claims with [TIME-SENSITIVE] marker → also retrieve
      - [ACCEPTED] without TIME-SENSITIVE → skip retrieval (already resolved)
    """
    # Build lookup: claim_id → current text (may have been revised in Sprint 2)
    s2_lineage = {rec.claim_id: rec.current_text for rec in sprint2.lineage_records}
    s1_claims  = {c.id: c for c in sprint1.claims}

    fully_accepted = set(sprint2.fully_accepted_ids)
    priority_ids   = set(sprint2.priority_retrieval_ids)
    high_conflict  = set(sprint2.high_conflict_ids)
    standard_ret   = set(sprint2.standard_retrieval_ids)

    # TIME-SENSITIVE accepted claims need re-checking
    time_sensitive_accepted = {
        cid for cid in fully_accepted
        if s1_claims.get(cid) and s1_claims[cid].marker == ClaimMarker.TIME_SENSITIVE
    }

    # Collect all claims needing retrieval
    to_retrieve: list[tuple[str, str]] = []
    skip_ids = fully_accepted - time_sensitive_accepted  # pure accepted, no TS

    # Canonical claim IDs from Sprint 2 (dedup may have retired some)
    canonical_ids = set(sprint2.dedup_report.canonical_ids)
    alias_map     = sprint2.dedup_report.alias_map   # alias → canonical

    for cid in sorted(canonical_ids, key=lambda x: int(x[1:])):
        if cid in skip_ids:
            continue
        text = s2_lineage.get(cid) or (s1_claims[cid].text if cid in s1_claims else "")
        if not text:
            continue
        to_retrieve.append((cid, text))

    return to_retrieve, priority_ids, high_conflict, skip_ids


# ── Sprint 2 status context builder ──────────────────────────────────────────

def _build_sprint2_statuses(sprint2: Sprint2Output) -> dict[str, str]:
    """Return {claim_id: debate_status_str} for context in Moderator prompt."""
    return {
        rec.claim_id: rec.final_debate_status.value
        for rec in sprint2.lineage_records
    }


# ── Cascade identification ─────────────────────────────────────────────────────

def _identify_cascade_claims(
    verdicts: list[ModeratorVerdict],
    dep_graph,
) -> set[str]:
    """Return the set of claim IDs that will be cascade-affected."""
    from sprint3.cascade import _build_children_map, _all_transitive_descendants
    failing = {v.claim_id for v in verdicts if v.verdict in (VerdictLabel.INCORRECT, VerdictLabel.UNCERTAIN)}
    children_map = _build_children_map(dep_graph)
    affected: set[str] = set()
    for fid in failing:
        affected.update(_all_transitive_descendants(fid, children_map))
    return affected - failing   # exclude the failing claims themselves


# ── Metrics computation ───────────────────────────────────────────────────────

def _compute_metrics(
    verdicts: list[ModeratorVerdict],
    retrieval_results,
    cascade_log,
) -> Sprint3Metrics:
    n         = len(verdicts)
    correct   = sum(1 for v in verdicts if v.verdict == VerdictLabel.CORRECT)
    incorrect = sum(1 for v in verdicts if v.verdict == VerdictLabel.INCORRECT)
    uncertain = sum(1 for v in verdicts if v.verdict == VerdictLabel.UNCERTAIN)
    mean_conf = sum(v.confidence for v in verdicts) / n if n else 0.0

    m = Sprint3Metrics(
        total_claims=n,
        correct_count=correct,
        incorrect_count=incorrect,
        uncertain_count=uncertain,
        cascade_count=len(cascade_log),
        retrieval_attempted=len(retrieval_results),
        retrieval_success=sum(1 for r in retrieval_results if r.retrieved),
    )
    m.mean_confidence = round(mean_conf, 4)
    # Recompute derived (model_validator already ran; update manually)
    m.accuracy           = round(correct / n, 4) if n else 0.0
    m.hallucination_rate = round(incorrect / n, 4) if n else 0.0
    hr = m.hallucination_rate
    m.risk_level = "LOW" if hr < 0.10 else ("MEDIUM" if hr < 0.30 else "HIGH")
    return m


# ── Rich display ──────────────────────────────────────────────────────────────

def _display_retrieval_log(retrieval_results) -> None:
    console.print(Rule("[bold cyan]STAGE 2 — RETRIEVAL LOG[/bold cyan]"))
    for r in retrieval_results:
        if not r.retrieved:
            console.print(f"  [dim]{r.claim_id}:[/dim] [red]No sources found → UNCERTAIN[/red]")
            continue
        best = r.best_snippet
        tier_col = {"Tier 1": "green", "Tier 2": "cyan", "Tier 3": "yellow"}.get(
            best.tier.value if best else "", "white"
        )
        console.print(
            f"  [bold]{r.claim_id}[/bold]: "
            + (
                f"[{tier_col}]{best.tier.value}[/{tier_col}] "
                f"[dim]{best.source_name[:40]}[/dim] "
                f"[{best.relation.value}] — {best.passage[:80]}…"
                if best else "no best snippet"
            )
        )
        if r.conflict_detected:
            console.print(f"    [bold yellow]⚡ {r.conflict_note[:100]}[/bold yellow]")


def _display_verdicts_table(verdicts: list[ModeratorVerdict], cascade_log) -> None:
    console.print(Rule("[bold white]STAGE 3+4 — MODERATOR VERDICTS + CASCADE[/bold white]"))
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold white", expand=True)
    table.add_column("ID",       width=5)
    table.add_column("Verdict",  width=12)
    table.add_column("Conf.",    width=6)
    table.add_column("w",        width=5)
    table.add_column("Priority", width=9)
    table.add_column("Cascade",  width=9)
    table.add_column("Evidence / Correction", ratio=1)

    cascade_ids = {e.child_id for e in cascade_log}
    vc = {
        VerdictLabel.CORRECT:   "green",
        VerdictLabel.INCORRECT: "bold red",
        VerdictLabel.UNCERTAIN: "yellow",
    }

    for v in verdicts:
        col      = vc.get(v.verdict, "white")
        casc_str = f"← {v.cascade_from}" if v.cascade_flag and v.cascade_from else ("⚠" if v.cascade_flag else "—")
        prio_str = "🔴" if v.sprint2_priority else ("⚠" if v.sprint2_high_conflict else "—")
        evid     = v.evidence_summary[:60] if v.evidence_summary else "—"
        if v.correction:
            evid += f" | Fix: {v.correction[:40]}"
        table.add_row(
            v.claim_id,
            f"[{col}]{v.verdict.value}[/{col}]",
            f"{v.confidence:.2f}",
            f"{v.source_weight:.1f}",
            prio_str,
            casc_str,
            evid,
        )
    console.print(table)

    if cascade_log:
        console.print(f"\n  [bold yellow]⚡ Cascade Events: {len(cascade_log)}[/bold yellow]")
        for ce in cascade_log:
            console.print(
                f"    {ce.failed_parent_id} ({ce.failed_parent_verdict.value}) → "
                f"{ce.child_id}: {ce.original_verdict.value} → {ce.cascaded_verdict.value}"
            )


def _display_metrics(metrics: Sprint3Metrics) -> None:
    console.print(Rule("[bold white]SPRINT 3 — METRICS[/bold white]"))
    risk_col = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "bold red"}.get(metrics.risk_level, "white")
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Metric", style="dim", width=28)
    table.add_column("Value",  style="bold")
    table.add_row("Total Claims",         str(metrics.total_claims))
    table.add_row("✓ Correct",            f"[green]{metrics.correct_count}[/green]")
    table.add_row("✗ Incorrect",          f"[red]{metrics.incorrect_count}[/red]")
    table.add_row("? Uncertain",          f"[yellow]{metrics.uncertain_count}[/yellow]")
    table.add_row("Cascade Events",       str(metrics.cascade_count))
    table.add_row("Retrieval Attempted",  str(metrics.retrieval_attempted))
    table.add_row("Retrieval Successful", str(metrics.retrieval_success))
    table.add_row("Accuracy",             f"{metrics.accuracy:.1%}")
    table.add_row("Hallucination Rate",   f"{metrics.hallucination_rate:.1%}")
    table.add_row("Mean Confidence",      f"{metrics.mean_confidence:.2f}")
    table.add_row("Risk Level",           f"[{risk_col}]{metrics.risk_level}[/{risk_col}]")
    console.print(table)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_sprint3(
    sprint1_output: Sprint1Output,
    sprint2_output: Sprint2Output,
) -> Sprint3Output:
    """
    Execute the full Sprint 3 pipeline.
    Returns a Sprint3Output object, also persisted to ./outputs/sprint3_output.json.
    """
    query = sprint1_output.query

    console.print(Panel(
        f"[bold]Query:[/bold] {query}\n"
        f"[bold]Canonical claims from Sprint 2:[/bold] {len(sprint2_output.dedup_report.canonical_ids)}\n"
        f"[bold]Priority retrieval:[/bold] {len(sprint2_output.priority_retrieval_ids)}  "
        f"[bold]High conflict:[/bold] {len(sprint2_output.high_conflict_ids)}",
        title="[bold cyan]🔍 SPRINT 3 — EVIDENCE RETRIEVAL & MODERATOR VERDICTS[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))

    # ── Stage 1: Claim selection ──────────────────────────────────────────────
    console.print("\n[bold white]▶ Stage 1: Selecting claims for retrieval …[/bold white]")
    to_retrieve, priority_ids, high_conflict_ids, accepted_skip = _select_claims_for_retrieval(
        sprint1_output, sprint2_output
    )
    console.print(
        f"  Claims to retrieve: [bold]{len(to_retrieve)}[/bold]  "
        f"Priority: [red]{len(priority_ids & {c for c,_ in to_retrieve})}[/red]  "
        f"High-conflict: [magenta]{len(high_conflict_ids & {c for c,_ in to_retrieve})}[/magenta]  "
        f"Skipped (accepted): [green]{len(accepted_skip)}[/green]"
    )

    # ── Stage 2: Retrieval ────────────────────────────────────────────────────
    console.print(f"\n[bold cyan]▶ Stage 2: Multi-source RAG retrieval ({len(to_retrieve)} claims) …[/bold cyan]")
    t0 = time.perf_counter()
    retrieval_results = run_retrieval(
        claims_to_retrieve=to_retrieve,
        priority_ids=list(priority_ids),
        high_conflict_ids=list(high_conflict_ids),
    )
    console.print(f"  [dim]Retrieval complete in {time.perf_counter()-t0:.1f}s[/dim]")
    _display_retrieval_log(retrieval_results)

    # ── Stage 3: Moderator verdicts ───────────────────────────────────────────
    console.print(f"\n[bold white]▶ Stage 3: Moderator Agent issuing verdicts …[/bold white]")

    # Build claims_data for moderator: (id, text, retrieval_result, is_cascade_candidate)
    retrieval_map   = {r.claim_id: r for r in retrieval_results}
    s2_statuses     = _build_sprint2_statuses(sprint2_output)

    claims_data = []
    for cid, text in to_retrieve:
        result     = retrieval_map.get(cid)
        if result is None:
            continue
        claims_data.append((cid, text, result, False))

    t1 = time.perf_counter()
    verdicts = run_moderator(
        query=query,
        claims_data=claims_data,
        sprint2_statuses=s2_statuses,
        priority_ids=priority_ids,
        high_conflict_ids=high_conflict_ids,
    )
    console.print(f"  [dim]Moderator complete in {time.perf_counter()-t1:.1f}s[/dim]")

    # Add CORRECT verdicts for fully-accepted (non-TIME-SENSITIVE) claims
    for cid in accepted_skip:
        s1_claim = sprint1_output.get_claim(cid)
        if s1_claim is None:
            continue
        verdicts.append(ModeratorVerdict(
            claim_id=cid,
            claim_text=s1_claim.text,
            verdict=VerdictLabel.CORRECT,
            source_weight=1.0,   # accepted by two models → treat as strong evidence
            confidence=1.0,
            evidence_summary="Sprint 2: both skeptics accepted; no retrieval required.",
            cascade_flag=False,
        ))

    # ── Stage 4: Cascade Failure Propagation ──────────────────────────────────
    console.print(f"\n[bold yellow]▶ Stage 4: Cascade Failure Propagation …[/bold yellow]")
    dep_graph = sprint2_output.dedup_report.alias_map   # may be empty; use S1 graph
    s1_dep_graph = sprint1_output.dependency_graph

    verdicts, cascade_log = run_cascade(verdicts, s1_dep_graph)
    console.print(f"  [dim]Cascade events: {len(cascade_log)}[/dim]")

    _display_verdicts_table(verdicts, cascade_log)

    # ── Stage 5: Metrics ──────────────────────────────────────────────────────
    metrics = _compute_metrics(verdicts, retrieval_results, cascade_log)
    _display_metrics(metrics)

    # ── Stage 6: Build and persist output ─────────────────────────────────────
    correct_ids   = [v.claim_id for v in verdicts if v.verdict == VerdictLabel.CORRECT]
    incorrect_ids = [v.claim_id for v in verdicts if v.verdict == VerdictLabel.INCORRECT]
    uncertain_ids = [v.claim_id for v in verdicts if v.verdict == VerdictLabel.UNCERTAIN]

    output = Sprint3Output(
        query=query,
        retrieval_results=retrieval_results,
        verdicts=verdicts,
        cascade_log=cascade_log,
        metrics=metrics,
        correct_ids=sorted(correct_ids,   key=lambda x: int(x[1:])),
        incorrect_ids=sorted(incorrect_ids, key=lambda x: int(x[1:])),
        uncertain_ids=sorted(uncertain_ids, key=lambda x: int(x[1:])),
    )

    out_dir  = settings.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sprint3_output.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output.model_dump(), f, indent=2, default=str)

    console.print(f"\n[dim green]✓ Sprint 3 output saved → {out_path}[/dim green]")
    return output


# ── Standalone loaders ────────────────────────────────────────────────────────

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
