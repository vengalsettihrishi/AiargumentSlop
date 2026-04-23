"""
sprint2/models.py
─────────────────
Pydantic v2 data models for Sprint 2.

Model hierarchy:
  DedupCluster          — one group of semantically equivalent claims
  DedupReport           — full dedup stage output

  LineageRecord         — audit trail for a single canonical claim
  RoundEntry            — one round's debate data per claim

  SkepticVerdict        — single-agent verdict on one claim
  InterSkepticAnalysis  — disagreement analysis for one claim in one round
  ProponentRebuttal     — proponent action on one contested claim

  DebateRound           — complete Round N data
  ConvergenceScore      — Score + Delta for one round

  Sprint2Output         — top-level object; feeds Sprint 3
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enumerations ──────────────────────────────────────────────────────────────

class SkepticStatus(str, Enum):
    CONTESTED  = "CONTESTED"
    PLAUSIBLE  = "PLAUSIBLE"
    SUSPICIOUS = "SUSPICIOUS"
    ACCEPTED   = "ACCEPTED"


class CombinedStatus(str, Enum):
    ACCEPTED              = "ACCEPTED"
    PLAUSIBLE             = "PLAUSIBLE"
    SUSPICIOUS            = "SUSPICIOUS"
    CONTESTED             = "CONTESTED"
    CONTESTED_DUAL        = "CONTESTED: DUAL-OBJECTION"
    HIGH_CONFLICT         = "HIGH CONFLICT"


class DisagreementType(str, Enum):
    MODEL_BIAS    = "MODEL-BIAS"
    AMBIGUITY     = "AMBIGUITY"
    EVIDENCE_GAP  = "EVIDENCE-GAP"
    NONE          = "NONE"       # no disagreement


class ProponentAction(str, Enum):
    DEFEND  = "DEFEND"
    REVISE  = "REVISE"
    CONCEDE = "CONCEDE"
    NONE    = "NONE"    # claim not contested in this round


class DebateExitReason(str, Enum):
    EARLY_EXIT   = "EARLY EXIT (convergence ≥ 0.85)"
    STAGNATION   = "STAGNATION (delta < 0.05 after Round 2)"
    FULL_ROUNDS  = "FULL 3 ROUNDS COMPLETED"


# ── Dedup stage ───────────────────────────────────────────────────────────────

class DedupCluster(BaseModel):
    """One group of semantically equivalent claims."""
    canonical_id: str
    canonical_text: str
    alias_ids: list[str]             = Field(default_factory=list)
    alias_texts: list[str]           = Field(default_factory=list)
    similarity_scores: list[float]   = Field(default_factory=list)  # alias vs canonical
    graph_updates: list[str]         = Field(default_factory=list)  # e.g. "C7 → C3"


class DedupReport(BaseModel):
    """Full output of the dedup stage."""
    clusters: list[DedupCluster]     = Field(default_factory=list)
    alias_map: dict[str, str]        = Field(default_factory=dict)  # alias_id → canonical_id
    canonical_ids: list[str]         = Field(default_factory=list)
    total_input_claims: int          = 0
    total_canonical_claims: int      = 0
    total_aliases_retired: int       = 0


# ── Lineage record ────────────────────────────────────────────────────────────

class RoundEntry(BaseModel):
    """One round's complete data for a single claim."""
    round_num: int
    skeptic_a_status: SkepticStatus
    skeptic_a_reason: str
    skeptic_b_status: SkepticStatus
    skeptic_b_reason: str
    combined_status: CombinedStatus
    disagreement_type: DisagreementType
    priority_retrieval: bool         = False
    proponent_action: ProponentAction = ProponentAction.NONE
    proponent_reasoning: str         = ""
    original_text: Optional[str]     = None   # set when action == REVISE
    revised_text: Optional[str]      = None   # set when action == REVISE
    post_round_status: CombinedStatus = CombinedStatus.ACCEPTED


class LineageRecord(BaseModel):
    """Full audit trail for one canonical claim, spanning all sprints."""
    claim_id: str
    canonical_text: str
    sprint1_marker: str              = ""      # SUPERLATIVE / TIME-SENSITIVE / ""
    alias_ids: list[str]             = Field(default_factory=list)
    round_log: list[RoundEntry]      = Field(default_factory=list)
    # Mutable state
    current_text: str                = ""      # may change on REVISE
    final_debate_status: CombinedStatus = CombinedStatus.ACCEPTED
    priority_retrieval: bool         = False   # permanently True once flagged
    high_conflict: bool              = False

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        if not self.current_text:
            self.current_text = self.canonical_text

    def add_round(self, entry: RoundEntry) -> None:
        self.round_log.append(entry)
        # Propagate permanent priority flag
        if entry.priority_retrieval:
            self.priority_retrieval = True
        if entry.proponent_action == ProponentAction.REVISE and entry.revised_text:
            self.current_text = entry.revised_text
        self.final_debate_status = entry.post_round_status


# ── Skeptic verdict ───────────────────────────────────────────────────────────

class SkepticVerdict(BaseModel):
    claim_id: str
    status: SkepticStatus
    reason: str


# ── Inter-skeptic analysis for one claim ─────────────────────────────────────

class InterSkepticResult(BaseModel):
    claim_id: str
    skeptic_a: SkepticVerdict
    skeptic_b: SkepticVerdict
    disagreement: bool
    disagreement_type: DisagreementType = DisagreementType.NONE
    combined_status: CombinedStatus
    priority_retrieval: bool = False


# ── Proponent rebuttal for one claim ─────────────────────────────────────────

class ProponentRebuttal(BaseModel):
    claim_id: str
    action: ProponentAction
    reasoning: str
    original_text: Optional[str] = None
    revised_text:  Optional[str] = None


# ── Full debate round ─────────────────────────────────────────────────────────

class ConvergenceScore(BaseModel):
    round_num: int
    agreed_count: int
    total_count: int
    score: float      # agreed / total
    delta: float      # score - previous score


class DebateRound(BaseModel):
    round_num: int
    skeptic_a_verdicts: list[SkepticVerdict]    = Field(default_factory=list)
    skeptic_b_verdicts: list[SkepticVerdict]    = Field(default_factory=list)
    inter_skeptic:      list[InterSkepticResult] = Field(default_factory=list)
    proponent_rebuttals: list[ProponentRebuttal] = Field(default_factory=list)
    convergence: Optional[ConvergenceScore]      = None


# ── Sprint 2 complete output ──────────────────────────────────────────────────

class Sprint2Output(BaseModel):
    query: str
    dedup_report: DedupReport
    lineage_records: list[LineageRecord]
    debate_rounds: list[DebateRound]
    # Final summary
    final_convergence_score: float   = 0.0
    exit_reason: Optional[DebateExitReason] = None
    exit_round: int                  = 0
    fully_accepted_ids: list[str]    = Field(default_factory=list)
    standard_retrieval_ids: list[str] = Field(default_factory=list)
    priority_retrieval_ids: list[str] = Field(default_factory=list)
    high_conflict_ids: list[str]     = Field(default_factory=list)

    def get_lineage(self, cid: str) -> Optional[LineageRecord]:
        return next((r for r in self.lineage_records if r.claim_id == cid), None)
