"""
sprint4/report.py
─────────────────
Rich-formatted transparency report renderer for Sprint 4.

Renders three sections to the terminal:
  1. Claims Evaluation Table (full claim-by-claim breakdown)
  2. Refined Final Answer (framed prose panel)
  3. System Metrics Report (full stats + confidence/risk/integrity)

Also writes a plain-text transparency report to:
  ./outputs/sprint4_report.txt
"""

from __future__ import annotations
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import box
from rich.text import Text

from sprint4.models import (
    Sprint4Output, SystemMetrics,
    HallucinationRisk, DependencyIntegrity,
)

console = Console()


# ── Colour maps ───────────────────────────────────────────────────────────────

_VERDICT_COLORS = {
    "CORRECT":   "bold green",
    "INCORRECT": "bold red",
    "UNCERTAIN": "bold yellow",
}
_RISK_COLORS = {
    HallucinationRisk.LOW:    "green",
    HallucinationRisk.MEDIUM: "yellow",
    HallucinationRisk.HIGH:   "bold red",
}
_INTEGRITY_COLORS = {
    DependencyIntegrity.STABLE:    "green",
    DependencyIntegrity.DEGRADED:  "yellow",
    DependencyIntegrity.COLLAPSED: "bold red",
}


# ── Section 1: Claims evaluation table ───────────────────────────────────────

def render_claims_table(output: Sprint4Output) -> None:
    console.print(Rule("[bold white]STAGE 2 — CLAIMS EVALUATION TABLE[/bold white]"))

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("ID",      width=5)
    table.add_column("Marker",  width=14)
    table.add_column("Verdict", width=24)
    table.add_column("Conf.",   width=6)
    table.add_column("Evidence / Correction", ratio=1)

    for row in output.claim_rows:
        col = _VERDICT_COLORS.get(row.verdict, "white")
        tag = row.verdict_tag   # includes [CASCADE from Cx] suffix if applicable
        hc  = " [HC]" if row.high_conflict else ""

        marker_col = (
            "magenta" if row.sprint1_marker == "SUPERLATIVE"
            else "yellow" if row.sprint1_marker == "TIME-SENSITIVE"
            else "dim"
        )
        marker_str = f"[{marker_col}]{row.sprint1_marker or '—'}[/{marker_col}]"

        evid = row.evidence_summary[:70] if row.evidence_summary else "—"
        if row.correction:
            evid += f"\n  [italic]Fix: {row.correction[:60]}[/italic]"

        table.add_row(
            row.claim_id,
            marker_str,
            f"[{col}]{tag}{hc}[/{col}]",
            f"{row.confidence:.2f}",
            evid,
        )

    console.print(table)


# ── Section 2: Final answer ───────────────────────────────────────────────────

def render_final_answer(output: Sprint4Output) -> None:
    console.print(Rule("[bold cyan]STAGE 1 — REFINED FINAL ANSWER[/bold cyan]"))
    console.print(Panel(
        output.refined_answer or "[dim italic]No refined answer produced.[/dim italic]",
        title=f"[bold white]Answer to: {output.query[:80]}[/bold white]",
        border_style="cyan",
        padding=(1, 2),
    ))


# ── Section 3: Metrics report ─────────────────────────────────────────────────

def render_metrics_report(output: Sprint4Output) -> None:
    m = output.metrics
    console.print(Rule("[bold white]STAGE 3 — SYSTEM METRICS REPORT[/bold white]"))

    # ── Core counts table ─────────────────────────────────────────────────────
    counts = Table(box=box.SIMPLE, show_header=False, expand=False)
    counts.add_column("Metric", style="dim", width=30)
    counts.add_column("Value",  style="bold")
    counts.add_row("Total claims",      str(m.total_claims))
    counts.add_row("[green]Correct[/green]",    f"[green]{m.correct_count}[/green]")
    counts.add_row("[red]Incorrect[/red]",      f"[red]{m.incorrect_count}[/red]")
    counts.add_row("[yellow]Uncertain[/yellow]",f"[yellow]{m.uncertain_count}[/yellow]")
    counts.add_row("Cascade-flagged",   str(m.cascade_flagged))
    counts.add_row("─" * 20, "─" * 10)
    counts.add_row("Accuracy",          f"{m.accuracy:.1%}")
    counts.add_row("Hallucination rate",f"{m.hallucination_rate:.1%}")
    counts.add_row("Avg source weight", f"{m.avg_source_weight:.2f}")
    counts.add_row("─" * 20, "─" * 10)
    counts.add_row("Debate rounds used",f"{m.debate_rounds_used} / 3")
    counts.add_row("Final convergence", f"{m.final_convergence:.1%}")
    hc_str = ", ".join(m.high_conflict_ids) if m.high_conflict_ids else "none"
    counts.add_row("High-conflict IDs", hc_str)
    console.print(counts)

    # ── Summary badges ────────────────────────────────────────────────────────
    rc  = _RISK_COLORS[m.hallucination_risk]
    ic  = _INTEGRITY_COLORS[m.dependency_integrity]
    conf_pct = f"{m.confidence_score:.1%}"

    console.print()
    console.print(Panel(
        f"[bold]CONFIDENCE SCORE      :[/bold]  {conf_pct}\n"
        f"[bold]HALLUCINATION RISK    :[/bold]  [{rc}]{m.hallucination_risk.value}[/{rc}]\n"
        f"[bold]DEPENDENCY INTEGRITY  :[/bold]  [{ic}]{m.dependency_integrity.value}[/{ic}]",
        title="[bold white]SYSTEM ASSESSMENT[/bold white]",
        border_style=(
            "green"  if m.hallucination_risk == HallucinationRisk.LOW else
            "yellow" if m.hallucination_risk == HallucinationRisk.MEDIUM else "red"
        ),
        padding=(1, 2),
    ))


# ── Plain-text report for file output ─────────────────────────────────────────

def _build_plain_report(output: Sprint4Output) -> str:
    m = output.metrics
    sep = "─" * 60

    hc_str = ", ".join(m.high_conflict_ids) if m.high_conflict_ids else "none"

    lines = [
        sep,
        "HYBRID MULTI-AGENT DEBATE SYSTEM — TRANSPARENCY REPORT",
        sep,
        f"Query: {output.query}",
        "",
        sep,
        "CLAIMS EVALUATION:",
        sep,
    ]

    for row in output.claim_rows:
        lines.append(f"  {row.claim_id}: {row.claim_text}")
        lines.append(f"       -> {row.verdict_tag}")
        if row.evidence_summary:
            lines.append(f"       Evidence: {row.evidence_summary}")
        if row.correction:
            lines.append(f"       Correction: {row.correction}")
        lines.append("")

    lines += [
        sep,
        "FINAL ANSWER:",
        sep,
        output.refined_answer or "(No refined answer produced.)",
        "",
        sep,
        "METRICS:",
        sep,
        f"  Total claims          : {m.total_claims}",
        f"  Correct               : {m.correct_count}",
        f"  Incorrect             : {m.incorrect_count}",
        f"  Uncertain             : {m.uncertain_count}",
        f"  Cascade-flagged       : {m.cascade_flagged}",
        "",
        f"  Accuracy              : {m.accuracy:.1%}",
        f"  Hallucination rate    : {m.hallucination_rate:.1%}",
        f"  Avg source weight     : {m.avg_source_weight:.2f}",
        "",
        f"  Debate rounds used    : {m.debate_rounds_used} / 3",
        f"  Final convergence     : {m.final_convergence:.1%}",
        f"  High-conflict claims  : {hc_str}",
        "",
        sep,
        f"  CONFIDENCE SCORE      : {m.confidence_score:.1%}",
        f"  HALLUCINATION RISK    : {m.hallucination_risk.value}",
        f"  DEPENDENCY INTEGRITY  : {m.dependency_integrity.value}",
        sep,
    ]
    return "\n".join(lines)


def save_plain_report(output: Sprint4Output, out_dir: Path) -> Path:
    """Write the transparency report to a plain-text file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sprint4_report.txt"
    path.write_text(_build_plain_report(output), encoding="utf-8")
    return path


# ── Master render ─────────────────────────────────────────────────────────────

def render_full_report(output: Sprint4Output) -> None:
    """Render all three sections to the terminal in logical order."""
    render_claims_table(output)
    console.print()
    render_final_answer(output)
    console.print()
    render_metrics_report(output)
