"""
sprint1/runner.py
─────────────────
Orchestrates the full Sprint 1 pipeline:

  Step 1 — Proponent Agent:     generate a defensible answer
  Step 2 — Decomposition Agent: atomise + build dependency graph
  Step 3 — Cascade Prep:        resolve orphan claims, annotate graph
  Step 4 — Persist output:      save Sprint1Output JSON to ./outputs/

This module exposes a single public function: run_sprint1(query) → Sprint1Output
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
from llm_client import call_llm
from sprint1.models import Sprint1Output, AtomicClaim, DependencyEdge
from sprint1.prompts import (
    PROPONENT_SYSTEM, PROPONENT_USER,
    DECOMPOSITION_SYSTEM, DECOMPOSITION_USER,
)
from sprint1.parser import (
    parse_proponent_answer,
    parse_claims,
    parse_dependency_graph,
)

log = logging.getLogger(__name__)
console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_all_claims_in_graph(
    claims: list[AtomicClaim],
    edges: list[DependencyEdge],
) -> list[DependencyEdge]:
    """
    Guarantee every claim appears in the dependency graph at least as a parent.
    Orphan claims (not mentioned as parents) are added with no children.
    This enforces the 'no orphaned claims' constraint.
    """
    parent_ids = {e.parent for e in edges}
    for claim in claims:
        if claim.id not in parent_ids:
            log.debug("Claim %s was orphaned — adding as leaf node.", claim.id)
            edges.append(DependencyEdge(parent=claim.id, children=[]))
    # Sort edges by numeric claim id for readability
    edges.sort(key=lambda e: int(e.parent[1:]))
    return edges


def _compute_stats(output: Sprint1Output) -> dict:
    return {
        "total_claims":        output.total_claims,
        "superlative_count":   output.superlative_count,
        "time_sensitive_count":output.time_sensitive_count,
        "provider_used":       output.provider,
        "model_used":          output.model_used,
    }


# ── Rich display helpers ───────────────────────────────────────────────────────

def _display_proponent_answer(answer: str) -> None:
    console.print(Rule("[bold cyan]STAGE 1 — PROPONENT ANSWER[/bold cyan]"))
    console.print(Panel(answer, border_style="cyan", padding=(1, 2)))


def _display_claims(claims: list[AtomicClaim]) -> None:
    console.print(Rule("[bold yellow]STAGE 2 — ATOMIC CLAIMS[/bold yellow]"))
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold yellow")
    table.add_column("ID",     style="dim", width=4)
    table.add_column("Claim",  style="white", ratio=1)
    table.add_column("Marker", style="magenta", width=14)

    for c in claims:
        marker_str = c.marker.value if c.marker.value else "—"
        table.add_row(c.id, c.text, marker_str)

    console.print(table)


def _display_dependency_graph(edges: list[DependencyEdge]) -> None:
    console.print(Rule("[bold green]STAGE 3 — DEPENDENCY GRAPH[/bold green]"))
    for edge in edges:
        console.print(f"  [bold]{edge.parent}[/bold] → {', '.join(edge.children) if edge.children else '(none)'}")


def _display_summary(stats: dict) -> None:
    console.print(Rule("[bold white]SPRINT 1 SUMMARY[/bold white]"))
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Key",   style="dim")
    table.add_column("Value", style="green")
    for k, v in stats.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_sprint1(query: str) -> Sprint1Output:
    """
    Execute the full Sprint 1 pipeline for the given user query.

    Returns a fully populated Sprint1Output object.
    """
    console.print(Panel(
        f"[bold]User Query:[/bold]\n{query}",
        title="[bold magenta]🚀 SPRINT 1 — PROPONENT + DECOMPOSITION[/bold magenta]",
        border_style="magenta",
        padding=(1, 2),
    ))

    # ── Step 1: Proponent Agent ─────────────────────────────────────────────

    console.print("\n[bold cyan]▶ Step 1: Running Proponent Agent …[/bold cyan]")
    t0 = time.perf_counter()

    raw_proponent, provider_used = call_llm(
        system_prompt=PROPONENT_SYSTEM,
        user_prompt=PROPONENT_USER.format(query=query),
        max_tokens=settings.PROPONENT_MAX_TOKENS,
        temperature=settings.PROPONENT_TEMPERATURE,
    )

    proponent_answer = parse_proponent_answer(raw_proponent)
    elapsed = time.perf_counter() - t0
    console.print(f"  [dim]Completed in {elapsed:.1f}s via [{provider_used}][/dim]")
    _display_proponent_answer(proponent_answer)

    # ── Step 2: Decomposition Analyst ───────────────────────────────────────

    console.print("\n[bold yellow]▶ Step 2: Running Decomposition Analyst …[/bold yellow]")
    t1 = time.perf_counter()

    raw_decomposition, _ = call_llm(
        system_prompt=DECOMPOSITION_SYSTEM,
        user_prompt=DECOMPOSITION_USER.format(
            query=query,
            proponent_answer=proponent_answer,
        ),
        max_tokens=settings.DECOMPOSITION_MAX_TOKENS,
        temperature=settings.DECOMPOSER_TEMPERATURE,
    )

    elapsed = time.perf_counter() - t1
    console.print(f"  [dim]Completed in {elapsed:.1f}s[/dim]")

    # ── Step 3: Parse + build structures ────────────────────────────────────

    claims = parse_claims(raw_decomposition)
    claim_ids = {c.id for c in claims}
    dep_graph = parse_dependency_graph(raw_decomposition, known_claim_ids=claim_ids)
    dep_graph = _ensure_all_claims_in_graph(claims, dep_graph)

    _display_claims(claims)
    _display_dependency_graph(dep_graph)

    # ── Step 4: Build output model ───────────────────────────────────────────

    # Resolve model name used (from provider)
    model_name_map = {
        "openai":    settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "groq":      settings.GROQ_MODEL,
    }

    output = Sprint1Output(
        query=query,
        proponent_answer=proponent_answer,
        claims=claims,
        dependency_graph=dep_graph,
        model_used=model_name_map.get(provider_used, provider_used),
        provider=provider_used,
    )

    # ── Step 5: Persist JSON ─────────────────────────────────────────────────

    out_dir = settings.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sprint1_output.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output.model_dump(), f, indent=2, default=str)

    console.print(f"\n[dim green]✓ Sprint 1 output saved → {out_path}[/dim green]")

    _display_summary(_compute_stats(output))

    return output
