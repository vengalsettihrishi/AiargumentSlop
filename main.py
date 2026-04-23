"""
main.py
-------
Entry point for the Hybrid Multi-Agent Debate System.

This is ONE application. The sprint/ folders are Python packages that
organise each pipeline stage. They chain together:

    Sprint 1 -> Sprint 2 -> Sprint 3 -> Sprint 4
    (Answer)   (Debate)   (Evidence)  (Synthesis & Report)

Usage
-----
  # Run the FULL pipeline in one shot (recommended)
  python main.py "Your query here"
  python main.py --all "Your query here"

  # Interactive mode
  python main.py

  # Run up to a specific sprint only
  python main.py --sprint 1 "query"   # Answer + Decomposition
  python main.py --sprint 2 "query"   # + Adversarial Debate
  python main.py --sprint 3 "query"   # + Evidence & Verdicts
  python main.py --sprint 4 "query"   # + Synthesis & Report (full)

  # Resume from saved disk outputs (skip re-running earlier sprints)
  python main.py --sprint 2           # load S1 from disk, run S2
  python main.py --sprint 3           # load S1+S2 from disk, run S3
  python main.py --sprint 4           # load S1+S2+S3 from disk, run S4
"""

from __future__ import annotations
import argparse
import logging
import sys
import time

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.rule import Rule

from config import settings

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
log = logging.getLogger(__name__)
console = Console()


# ── Config validation ──────────────────────────────────────────────────────────

def _validate_config() -> None:
    errors = settings.validate()
    if errors:
        for e in errors:
            log.error("Config error: %s", e)
        console.print(
            "\n[bold red]Missing required API keys. "
            "Please fill in your .env file and retry.[/bold red]\n"
        )
        sys.exit(1)


# ── Individual sprint wrappers ─────────────────────────────────────────────────

def _sprint1(query: str):
    from sprint1.runner import run_sprint1
    return run_sprint1(query)


def _sprint2(s1_output=None):
    from sprint2.runner import run_sprint2, load_sprint1_output
    if s1_output is None:
        console.print("[dim]Loading Sprint 1 output from disk ...[/dim]")
        s1_output = load_sprint1_output()
    return run_sprint2(s1_output)


def _sprint3(s1_output=None, s2_output=None):
    from sprint3.runner import run_sprint3, load_sprint1_output, load_sprint2_output
    if s1_output is None:
        console.print("[dim]Loading Sprint 1 output from disk ...[/dim]")
        s1_output = load_sprint1_output()
    if s2_output is None:
        console.print("[dim]Loading Sprint 2 output from disk ...[/dim]")
        s2_output = load_sprint2_output()
    return run_sprint3(s1_output, s2_output)


def _sprint4(s1_output=None, s2_output=None, s3_output=None):
    from sprint4.runner import (
        run_sprint4,
        load_sprint1_output,
        load_sprint2_output,
        load_sprint3_output,
    )
    if s1_output is None:
        console.print("[dim]Loading Sprint 1 output from disk ...[/dim]")
        s1_output = load_sprint1_output()
    if s2_output is None:
        console.print("[dim]Loading Sprint 2 output from disk ...[/dim]")
        s2_output = load_sprint2_output()
    if s3_output is None:
        console.print("[dim]Loading Sprint 3 output from disk ...[/dim]")
        s3_output = load_sprint3_output()
    return run_sprint4(s1_output, s2_output, s3_output)


# ── Full pipeline ──────────────────────────────────────────────────────────────

def run_full_pipeline(query: str) -> None:
    """
    Run Sprint 1 -> Sprint 2 -> Sprint 3 -> Sprint 4 as one continuous pipeline.
    Each sprint's output is passed directly to the next — no disk round-trips
    between stages.
    """
    total_start = time.perf_counter()

    console.print(Panel(
        f"[bold white]Query:[/bold white] {query}\n\n"
        "[dim]Full pipeline: Sprint 1 (Answer) -> Sprint 2 (Debate) "
        "-> Sprint 3 (Evidence) -> Sprint 4 (Synthesis & Report)[/dim]",
        title="[bold magenta]HYBRID MULTI-AGENT DEBATE SYSTEM[/bold magenta]",
        border_style="magenta",
        padding=(1, 2),
    ))

    # Sprint 1
    console.print(Rule("[bold cyan]SPRINT 1 -- ANSWER & DECOMPOSITION[/bold cyan]"))
    t1 = time.perf_counter()
    s1 = _sprint1(query)
    console.print(f"[dim]Sprint 1 complete in {time.perf_counter()-t1:.1f}s[/dim]")

    # Sprint 2
    console.print(Rule("[bold magenta]SPRINT 2 -- ADVERSARIAL DEBATE[/bold magenta]"))
    t2 = time.perf_counter()
    s2 = _sprint2(s1)
    console.print(f"[dim]Sprint 2 complete in {time.perf_counter()-t2:.1f}s[/dim]")

    # Sprint 3
    console.print(Rule("[bold cyan]SPRINT 3 -- EVIDENCE RETRIEVAL & VERDICTS[/bold cyan]"))
    t3 = time.perf_counter()
    s3 = _sprint3(s1, s2)
    console.print(f"[dim]Sprint 3 complete in {time.perf_counter()-t3:.1f}s[/dim]")

    # Sprint 4
    console.print(Rule("[bold green]SPRINT 4 -- SYNTHESIS & TRANSPARENCY REPORT[/bold green]"))
    t4 = time.perf_counter()
    s4 = _sprint4(s1, s2, s3)
    console.print(f"[dim]Sprint 4 complete in {time.perf_counter()-t4:.1f}s[/dim]")

    # Final banner (uses Sprint 4 metrics — the authoritative system assessment)
    total_elapsed = time.perf_counter() - total_start
    m  = s4.metrics
    rc = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "bold red"}.get(
        m.hallucination_risk.value, "white"
    )
    ic = {"STABLE": "green", "DEGRADED": "yellow", "COLLAPSED": "bold red"}.get(
        m.dependency_integrity.value, "white"
    )

    console.print(Panel(
        f"[bold]Total claims       :[/bold] {m.total_claims}\n"
        f"[green]Correct            :[/green] {m.correct_count}  ({m.accuracy:.0%})\n"
        f"[red]Incorrect          :[/red] {m.incorrect_count}  "
        f"(hallucination {m.hallucination_rate:.0%})\n"
        f"[yellow]Uncertain          :[/yellow] {m.uncertain_count}\n"
        f"Cascade events     : {m.cascade_flagged}\n\n"
        f"Confidence score   : {m.confidence_score:.1%}\n"
        f"Hallucination risk : [{rc}]{m.hallucination_risk.value}[/{rc}]\n"
        f"Dep. integrity     : [{ic}]{m.dependency_integrity.value}[/{ic}]\n\n"
        f"[dim]Total wall time    : {total_elapsed:.1f}s[/dim]",
        title="[bold white]PIPELINE COMPLETE[/bold white]",
        border_style=(
            "green"  if m.hallucination_risk.value == "LOW"    else
            "yellow" if m.hallucination_risk.value == "MEDIUM" else "red"
        ),
        padding=(1, 2),
    ))


# ── Partial sprint dispatcher ──────────────────────────────────────────────────

def _run_sprint(sprint_num: int, query: str) -> None:
    """Run the pipeline up to sprint N only."""
    if sprint_num == 1:
        if not query:
            console.print("[bold red]--sprint 1 requires a query.[/bold red]")
            sys.exit(1)
        _sprint1(query)

    elif sprint_num == 2:
        s1 = _sprint1(query) if query else None
        _sprint2(s1)

    elif sprint_num == 3:
        if query:
            s1 = _sprint1(query)
            s2 = _sprint2(s1)
        else:
            s1 = s2 = None
        _sprint3(s1, s2)

    elif sprint_num == 4:
        if query:
            s1 = _sprint1(query)
            s2 = _sprint2(s1)
            s3 = _sprint3(s1, s2)
        else:
            s1 = s2 = s3 = None
        _sprint4(s1, s2, s3)

    else:
        console.print(f"[bold red]Sprint {sprint_num} is not implemented.[/bold red]")
        sys.exit(1)


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Hybrid Multi-Agent Debate System "
            "-- Sprint 1 -> 2 -> 3 -> 4 full pipeline"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python main.py "Who invented the World Wide Web?"\n'
            '  python main.py --all "What caused the 2008 financial crisis?"\n'
            "  python main.py --sprint 4   # load S1-S3 from disk, run Sprint 4 only\n"
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="The question to fact-check (omit for interactive mode)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Run the full Sprint 1->2->3->4 pipeline (default when query is given)",
    )
    group.add_argument(
        "--sprint",
        type=int,
        metavar="N",
        help=(
            "Run the pipeline up to sprint N (1-4). "
            "Omit query to load earlier sprint outputs from disk."
        ),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    _validate_config()

    query = args.query

    # Interactive mode: no query, no flags
    if not query and args.sprint is None and not args.all:
        console.print(Panel(
            "[bold magenta]Hybrid Multi-Agent Debate System[/bold magenta]\n"
            "[dim]Sprints 1 -> 2 -> 3 -> 4 will run in sequence.[/dim]",
            border_style="magenta",
            padding=(0, 2),
        ))
        try:
            query = input("Query -> ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting.[/dim]")
            sys.exit(0)

    if not query and args.sprint is None and not args.all:
        console.print("[bold red]No query provided.[/bold red]")
        sys.exit(1)

    # Route
    if args.sprint is not None:
        _run_sprint(args.sprint, query or "")
    else:
        if not query:
            console.print("[bold red]A query is required to run the full pipeline.[/bold red]")
            sys.exit(1)
        run_full_pipeline(query)


if __name__ == "__main__":
    main()
