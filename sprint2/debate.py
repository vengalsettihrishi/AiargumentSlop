"""
sprint2/debate.py
─────────────────
Core debate logic for Sprint 2.

Responsibilities:
  - Run SKEPTIC-A (GPT-4o) and SKEPTIC-B (Claude 3.5) independently
  - Compute Inter-Skeptic Analysis per claim per round
  - Run Proponent Rebuttal on contested/suspicious claims
  - Track convergence per round, apply exit conditions
  - Propagate HIGH_CONFLICT on stagnation
  - Update LineageRecord after each round

Public function:
  run_debate(
      query, canonical_claims, dep_graph, lineage_records, settings
  ) → list[DebateRound]
"""

from __future__ import annotations
import logging
import time
from typing import Optional

from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich import box

from config import settings as cfg
from llm_client import call_llm
from sprint1.models import AtomicClaim, DependencyEdge
from sprint2.models import (
    SkepticStatus, CombinedStatus, DisagreementType, ProponentAction,
    SkepticVerdict, InterSkepticResult, ProponentRebuttal,
    DebateRound, ConvergenceScore, LineageRecord, RoundEntry,
)
from sprint2.prompts import SKEPTIC_SYSTEM, SKEPTIC_USER, PROPONENT_REBUTTAL_SYSTEM, PROPONENT_REBUTTAL_USER
from sprint2.parser import parse_skeptic_verdicts, parse_proponent_rebuttal

log = logging.getLogger(__name__)
console = Console()

MAX_ROUNDS           = 3
CONVERGENCE_THRESHOLD = 0.85
STAGNATION_DELTA      = 0.05


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _claims_block(claims: list[AtomicClaim]) -> str:
    lines = []
    for c in claims:
        marker = f" [{c.marker.value}]" if c.marker.value else ""
        lines.append(f"  {c.id}: {c.text}{marker}")
    return "\n".join(lines)


def _current_texts_block(claims: list[AtomicClaim], lineage: dict[str, LineageRecord]) -> str:
    lines = []
    for c in claims:
        rec = lineage.get(c.id)
        current = rec.current_text if rec else c.text
        lines.append(f"  {c.id} (current): {current}")
    return "\n".join(lines)


def _contested_block(
    claims: list[AtomicClaim],
    inter_results: list[InterSkepticResult],
    lineage: dict[str, LineageRecord],
) -> str:
    """Build the contested claims block for the proponent prompt."""
    lines = []
    contested_map = {r.claim_id: r for r in inter_results
                     if r.combined_status in (
                         CombinedStatus.CONTESTED,
                         CombinedStatus.CONTESTED_DUAL,
                         CombinedStatus.SUSPICIOUS,
                     )}
    for c in claims:
        res = contested_map.get(c.id)
        if not res:
            continue
        rec = lineage.get(c.id)
        current = rec.current_text if rec else c.text
        lines.append(f"  {c.id}: {current}")
        lines.append(f"    SKEPTIC-A [{res.skeptic_a.status.value}]: {res.skeptic_a.reason}")
        lines.append(f"    SKEPTIC-B [{res.skeptic_b.status.value}]: {res.skeptic_b.reason}")
        lines.append(f"    Combined Status: {res.combined_status.value}")
        if res.combined_status == CombinedStatus.CONTESTED_DUAL:
            lines.append("    ⚠ DUAL-OBJECTION: address BOTH skeptic objections separately.")
        lines.append("")
    return "\n".join(lines) if lines else "  (none)"


# ── Inter-Skeptic Analysis ────────────────────────────────────────────────────

_STRICTER_PAIR: dict[tuple[SkepticStatus, SkepticStatus], CombinedStatus] = {
    # (A, B) → combined  [commutative — handled by sorting below]
    (SkepticStatus.CONTESTED,  SkepticStatus.ACCEPTED):   CombinedStatus.CONTESTED,
    (SkepticStatus.CONTESTED,  SkepticStatus.PLAUSIBLE):  CombinedStatus.CONTESTED,
    (SkepticStatus.CONTESTED,  SkepticStatus.SUSPICIOUS): CombinedStatus.CONTESTED,
    (SkepticStatus.SUSPICIOUS, SkepticStatus.ACCEPTED):   CombinedStatus.SUSPICIOUS,
    (SkepticStatus.SUSPICIOUS, SkepticStatus.PLAUSIBLE):  CombinedStatus.SUSPICIOUS,
    (SkepticStatus.PLAUSIBLE,  SkepticStatus.ACCEPTED):   CombinedStatus.PLAUSIBLE,
}

_STATUS_RANK = {
    SkepticStatus.ACCEPTED:   0,
    SkepticStatus.PLAUSIBLE:  1,
    SkepticStatus.SUSPICIOUS: 2,
    SkepticStatus.CONTESTED:  3,
}


def _compute_combined_status(
    a: SkepticVerdict,
    b: SkepticVerdict,
) -> tuple[CombinedStatus, bool, DisagreementType]:
    """
    Returns (combined_status, disagreement_bool, disagreement_type).
    """
    if a.status == b.status:
        if a.status == SkepticStatus.CONTESTED:
            # Both contested but possibly different reasons → DUAL-OBJECTION
            if a.reason.strip().lower() != b.reason.strip().lower():
                return CombinedStatus.CONTESTED_DUAL, False, DisagreementType.NONE
        status_map = {
            SkepticStatus.ACCEPTED:   CombinedStatus.ACCEPTED,
            SkepticStatus.PLAUSIBLE:  CombinedStatus.PLAUSIBLE,
            SkepticStatus.SUSPICIOUS: CombinedStatus.SUSPICIOUS,
            SkepticStatus.CONTESTED:  CombinedStatus.CONTESTED,
        }
        return status_map[a.status], False, DisagreementType.NONE

    # They disagree — stricter verdict wins
    ranks = sorted([(a.status, a), (b.status, b)], key=lambda x: _STATUS_RANK[x[0]], reverse=True)
    stricter_status = ranks[0][0]
    combined_map = {
        SkepticStatus.CONTESTED:  CombinedStatus.CONTESTED,
        SkepticStatus.SUSPICIOUS: CombinedStatus.SUSPICIOUS,
        SkepticStatus.PLAUSIBLE:  CombinedStatus.PLAUSIBLE,
        SkepticStatus.ACCEPTED:   CombinedStatus.ACCEPTED,
    }
    combined = combined_map[stricter_status]

    # Classify disagreement type
    rank_a = _STATUS_RANK[a.status]
    rank_b = _STATUS_RANK[b.status]
    gap = abs(rank_a - rank_b)
    if gap == 3:  # CONTESTED vs ACCEPTED
        dtype = DisagreementType.MODEL_BIAS
    elif gap == 2:  # CONTESTED vs PLAUSIBLE or SUSPICIOUS vs ACCEPTED
        dtype = DisagreementType.EVIDENCE_GAP
    else:
        dtype = DisagreementType.AMBIGUITY

    return combined, True, dtype


def run_inter_skeptic_analysis(
    claims: list[AtomicClaim],
    verdicts_a: list[SkepticVerdict],
    verdicts_b: list[SkepticVerdict],
) -> list[InterSkepticResult]:
    """Compare both skeptic verdicts claim-by-claim."""
    a_map = {v.claim_id: v for v in verdicts_a}
    b_map = {v.claim_id: v for v in verdicts_b}
    results: list[InterSkepticResult] = []

    for claim in claims:
        cid = claim.id
        va  = a_map.get(cid, SkepticVerdict(claim_id=cid, status=SkepticStatus.PLAUSIBLE, reason="Missing"))
        vb  = b_map.get(cid, SkepticVerdict(claim_id=cid, status=SkepticStatus.PLAUSIBLE, reason="Missing"))

        combined, disagrees, dtype = _compute_combined_status(va, vb)

        # Priority retrieval: any disagreement or any non-ACCEPTED verdict
        priority = disagrees or combined not in (CombinedStatus.ACCEPTED, CombinedStatus.PLAUSIBLE)

        results.append(InterSkepticResult(
            claim_id=cid,
            skeptic_a=va,
            skeptic_b=vb,
            disagreement=disagrees,
            disagreement_type=dtype,
            combined_status=combined,
            priority_retrieval=priority,
        ))

    return results


# ── Convergence ───────────────────────────────────────────────────────────────

def _compute_convergence(
    inter_results: list[InterSkepticResult],
    rebuttals: list[ProponentRebuttal],
    round_num: int,
    prev_score: float,
) -> ConvergenceScore:
    """
    Agreement = claims with ACCEPTED combined status
              + claims where Proponent conceded (resolved, not re-contested)
    """
    conceded_ids = {r.claim_id for r in rebuttals if r.action == ProponentAction.CONCEDE}
    agreed = sum(
        1 for r in inter_results
        if r.combined_status == CombinedStatus.ACCEPTED or r.claim_id in conceded_ids
    )
    total = len(inter_results)
    score = agreed / total if total else 1.0
    delta = score - prev_score

    return ConvergenceScore(
        round_num=round_num,
        agreed_count=agreed,
        total_count=total,
        score=round(score, 4),
        delta=round(delta, 4),
    )


# ── Post-round claim status ───────────────────────────────────────────────────

def _post_round_status(
    inter: InterSkepticResult,
    rebuttal: Optional[ProponentRebuttal],
) -> CombinedStatus:
    """Determine the claim's status after round resolution."""
    if inter.combined_status == CombinedStatus.ACCEPTED:
        return CombinedStatus.ACCEPTED

    if rebuttal is None:
        return inter.combined_status

    if rebuttal.action == ProponentAction.CONCEDE:
        return CombinedStatus.SUSPICIOUS   # conceded = uncertain, needs retrieval

    if rebuttal.action == ProponentAction.REVISE:
        # Revised claim re-enters debate as PLAUSIBLE until next round confirms
        return CombinedStatus.PLAUSIBLE

    # DEFEND — remains contested until a skeptic accepts it in the next round
    return inter.combined_status


# ── Display helpers ───────────────────────────────────────────────────────────

def _display_verdicts(
    label: str,
    verdicts: list[SkepticVerdict],
    style: str,
) -> None:
    console.print(f"\n  [bold {style}]{label}[/bold {style}]")
    for v in verdicts:
        color = {
            SkepticStatus.ACCEPTED:   "green",
            SkepticStatus.PLAUSIBLE:  "cyan",
            SkepticStatus.SUSPICIOUS: "yellow",
            SkepticStatus.CONTESTED:  "red",
        }.get(v.status, "white")
        console.print(
            f"    [bold]{v.claim_id}[/bold] → [{color}][{v.status.value}][/{color}]: {v.reason[:120]}"
        )


def _display_inter_skeptic(results: list[InterSkepticResult]) -> None:
    console.print("\n  [bold magenta]── INTER-SKEPTIC ANALYSIS ──[/bold magenta]")
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    table.add_column("ID",       width=5)
    table.add_column("Agree?",   width=7)
    table.add_column("Type",     width=14)
    table.add_column("Combined", width=22)
    table.add_column("Priority", width=9)
    for r in results:
        agree_str  = "✓" if not r.disagreement else "✗"
        agree_col  = "green" if not r.disagreement else "red"
        prio_str   = "🔴 YES" if r.priority_retrieval else "—"
        combined_col = "red" if "CONTESTED" in r.combined_status.value else \
                       "yellow" if r.combined_status == CombinedStatus.SUSPICIOUS else "green"
        table.add_row(
            r.claim_id,
            f"[{agree_col}]{agree_str}[/{agree_col}]",
            r.disagreement_type.value if r.disagreement else "—",
            f"[{combined_col}]{r.combined_status.value}[/{combined_col}]",
            prio_str,
        )
    console.print(table)


def _display_convergence(conv: ConvergenceScore) -> None:
    delta_str = f"{conv.delta:+.1%}"
    delta_col = "green" if conv.delta >= 0 else "red"
    console.print(
        f"\n  [bold white]Convergence:[/bold white] "
        f"{conv.agreed_count}/{conv.total_count} "
        f"({conv.score:.1%}) "
        f"[{delta_col}]Δ {delta_str}[/{delta_col}]"
    )


# ── Main debate loop ──────────────────────────────────────────────────────────

def run_debate(
    query: str,
    canonical_claims: list[AtomicClaim],
    dep_graph: list[DependencyEdge],
    lineage_map: dict[str, LineageRecord],
) -> list[DebateRound]:
    """
    Execute up to MAX_ROUNDS of dual-skeptic adversarial debate.
    Updates lineage_map in-place after each round.
    Returns the list of completed DebateRound objects.
    """
    claim_ids  = {c.id for c in canonical_claims}
    rounds: list[DebateRound] = []
    prev_score = 0.0
    current_claims = list(canonical_claims)   # may have revised texts by round 2+

    for rnum in range(1, MAX_ROUNDS + 1):
        console.print(Rule(f"[bold white]── DEBATE ROUND {rnum} ──[/bold white]"))

        # ── Apply latest claim texts from lineage ────────────────────────────
        for c in current_claims:
            rec = lineage_map.get(c.id)
            if rec and rec.current_text != c.text:
                c = c.model_copy(update={"text": rec.current_text})

        claims_txt      = _claims_block(current_claims)
        current_txt     = _current_texts_block(current_claims, lineage_map)
        skeptic_user_A  = SKEPTIC_USER.format(
            query=query, round_num=rnum,
            claims_block=claims_txt, current_texts_block=current_txt,
        )
        # B gets identical user prompt — independence enforced by separate calls
        skeptic_user_B = skeptic_user_A

        # ── SKEPTIC-A (GPT-4o) ───────────────────────────────────────────────
        console.print(f"\n[bold cyan]  ▶ Skeptic-A (GPT-4o) …[/bold cyan]")
        t0 = time.perf_counter()
        raw_a, prov_a = call_llm(
            system_prompt=SKEPTIC_SYSTEM,
            user_prompt=skeptic_user_A,
            max_tokens=cfg.SKEPTIC_MAX_TOKENS,
            temperature=cfg.SKEPTIC_TEMPERATURE,
            provider="openai",
        )
        console.print(f"  [dim]Done in {time.perf_counter()-t0:.1f}s via [{prov_a}][/dim]")
        verdicts_a = parse_skeptic_verdicts(raw_a, expected_ids=claim_ids)
        _display_verdicts("Skeptic-A Verdicts", verdicts_a, "cyan")

        # ── SKEPTIC-B (Claude 3.5 Sonnet) ────────────────────────────────────
        console.print(f"\n[bold yellow]  ▶ Skeptic-B (Claude 3.5) …[/bold yellow]")
        t1 = time.perf_counter()
        raw_b, prov_b = call_llm(
            system_prompt=SKEPTIC_SYSTEM,
            user_prompt=skeptic_user_B,
            max_tokens=cfg.SKEPTIC_MAX_TOKENS,
            temperature=cfg.SKEPTIC_TEMPERATURE,
            provider="anthropic",
        )
        console.print(f"  [dim]Done in {time.perf_counter()-t1:.1f}s via [{prov_b}][/dim]")
        verdicts_b = parse_skeptic_verdicts(raw_b, expected_ids=claim_ids)
        _display_verdicts("Skeptic-B Verdicts", verdicts_b, "yellow")

        # ── Inter-Skeptic Analysis ────────────────────────────────────────────
        inter_results = run_inter_skeptic_analysis(current_claims, verdicts_a, verdicts_b)
        _display_inter_skeptic(inter_results)

        # ── Proponent Rebuttal ────────────────────────────────────────────────
        contested_claims = [
            c for c in current_claims
            if any(
                r.claim_id == c.id and r.combined_status in (
                    CombinedStatus.CONTESTED,
                    CombinedStatus.CONTESTED_DUAL,
                    CombinedStatus.SUSPICIOUS,
                )
                for r in inter_results
            )
        ]

        rebuttals: list[ProponentRebuttal] = []
        if contested_claims:
            console.print(f"\n[bold green]  ▶ Proponent Rebuttal ({len(contested_claims)} contested) …[/bold green]")
            contested_txt = _contested_block(current_claims, inter_results, lineage_map)
            t2 = time.perf_counter()
            raw_prop, prov_prop = call_llm(
                system_prompt=PROPONENT_REBUTTAL_SYSTEM,
                user_prompt=PROPONENT_REBUTTAL_USER.format(
                    query=query, round_num=rnum, contested_block=contested_txt,
                ),
                max_tokens=cfg.PROPONENT_MAX_TOKENS,
                temperature=cfg.PROPONENT_TEMPERATURE,
                provider=cfg.PRIMARY_LLM_PROVIDER,
            )
            console.print(f"  [dim]Done in {time.perf_counter()-t2:.1f}s via [{prov_prop}][/dim]")
            rebuttals = parse_proponent_rebuttal(raw_prop, contested_claims)

            for reb in rebuttals:
                action_col = {"DEFEND": "blue", "REVISE": "yellow", "CONCEDE": "red"}.get(reb.action.value, "white")
                console.print(
                    f"    [bold]{reb.claim_id}[/bold] → [{action_col}]{reb.action.value}[/{action_col}]"
                    + (f" | Revised: {reb.revised_text[:80]}…" if reb.revised_text else "")
                )
        else:
            console.print("\n  [dim green]  No contested claims — Proponent rebuttal skipped.[/dim green]")

        # ── Update Lineage Records ────────────────────────────────────────────
        rebuttal_map = {r.claim_id: r for r in rebuttals}
        inter_map    = {r.claim_id: r for r in inter_results}

        for claim in current_claims:
            cid  = claim.id
            rec  = lineage_map[cid]
            inte = inter_map[cid]
            reb  = rebuttal_map.get(cid)
            post = _post_round_status(inte, reb)

            entry = RoundEntry(
                round_num=rnum,
                skeptic_a_status=inte.skeptic_a.status,
                skeptic_a_reason=inte.skeptic_a.reason,
                skeptic_b_status=inte.skeptic_b.status,
                skeptic_b_reason=inte.skeptic_b.reason,
                combined_status=inte.combined_status,
                disagreement_type=inte.disagreement_type,
                priority_retrieval=inte.priority_retrieval,
                proponent_action=reb.action if reb else ProponentAction.NONE,
                proponent_reasoning=reb.reasoning if reb else "",
                original_text=reb.original_text if reb else None,
                revised_text=reb.revised_text if reb else None,
                post_round_status=post,
            )
            rec.add_round(entry)

        # ── Convergence Score ─────────────────────────────────────────────────
        conv = _compute_convergence(inter_results, rebuttals, rnum, prev_score)
        prev_score = conv.score
        _display_convergence(conv)

        # ── Assemble round ────────────────────────────────────────────────────
        debate_round = DebateRound(
            round_num=rnum,
            skeptic_a_verdicts=verdicts_a,
            skeptic_b_verdicts=verdicts_b,
            inter_skeptic=inter_results,
            proponent_rebuttals=rebuttals,
            convergence=conv,
        )
        rounds.append(debate_round)

        # ── Exit Conditions ───────────────────────────────────────────────────
        if conv.score >= CONVERGENCE_THRESHOLD:
            console.print(
                f"\n  [bold green]✓ Early exit: convergence {conv.score:.1%} ≥ {CONVERGENCE_THRESHOLD:.0%}[/bold green]"
            )
            break

        if rnum >= 2 and conv.delta < STAGNATION_DELTA:
            console.print(
                f"\n  [bold red]⚠ Stagnation detected (Δ={conv.delta:.1%} < {STAGNATION_DELTA:.0%}) "
                f"— escalating remaining contested claims to [HIGH CONFLICT][/bold red]"
            )
            for rec in lineage_map.values():
                if rec.final_debate_status in (
                    CombinedStatus.CONTESTED,
                    CombinedStatus.CONTESTED_DUAL,
                    CombinedStatus.SUSPICIOUS,
                ):
                    rec.high_conflict = True
                    rec.priority_retrieval = True
                    rec.final_debate_status = CombinedStatus.HIGH_CONFLICT
            # Run remaining rounds if any
            # (stagnation does NOT auto-exit per spec — just escalates)

    return rounds
