"""
sprint3/models.py
─────────────────
Pydantic v2 data models for Sprint 3.

Model hierarchy:
  SourceTier          — Enum: Tier 1 / 2 / 3 with weights
  EvidenceRelation    — SUPPORTS / CONTRADICTS / UNRELATED
  EvidenceSnippet     — one retrieved passage with tier, weight, relation
  RetrievalResult     — all evidence gathered for one claim
  ModeratorVerdict    — CORRECT / INCORRECT / UNCERTAIN with confidence
  CascadeEntry        — one cascade event: failed parent → affected child
  Sprint3Output       — top-level object; feeds Sprint 4
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ── Source credibility tiers ──────────────────────────────────────────────────

class SourceTier(str, Enum):
    TIER_1 = "Tier 1"   # peer-reviewed / official / primary data
    TIER_2 = "Tier 2"   # established news / encyclopedias / textbooks
    TIER_3 = "Tier 3"   # blogs / forums / unknown / undated


TIER_WEIGHTS: dict[SourceTier, float] = {
    SourceTier.TIER_1: 1.0,
    SourceTier.TIER_2: 0.7,
    SourceTier.TIER_3: 0.4,
}


# ── Evidence relation ─────────────────────────────────────────────────────────

class EvidenceRelation(str, Enum):
    SUPPORTS     = "SUPPORTS"
    CONTRADICTS  = "CONTRADICTS"
    UNRELATED    = "UNRELATED"


# ── Individual evidence snippet ───────────────────────────────────────────────

class EvidenceSnippet(BaseModel):
    source_name: str
    url:         str                     = ""
    tier:        SourceTier              = SourceTier.TIER_3
    weight:      float                   = 0.4
    passage:     str                     = ""
    relation:    EvidenceRelation        = EvidenceRelation.UNRELATED
    retrieval_source: str                = ""   # "tavily" | "serper" | "you" | "llm"

    @model_validator(mode="after")
    def sync_weight(self) -> "EvidenceSnippet":
        self.weight = TIER_WEIGHTS[self.tier]
        return self


# ── Per-claim retrieval result ────────────────────────────────────────────────

class RetrievalResult(BaseModel):
    claim_id:         str
    claim_text:       str
    snippets:         list[EvidenceSnippet] = Field(default_factory=list)
    retrieved:        bool                  = False  # False → UNCERTAIN
    conflict_detected: bool                 = False  # True when tiers disagree
    conflict_note:    str                   = ""

    @property
    def best_snippet(self) -> Optional[EvidenceSnippet]:
        """Return the highest-tier supporting snippet, or highest-tier overall."""
        supporting = [s for s in self.snippets if s.relation == EvidenceRelation.SUPPORTS]
        pool = supporting or self.snippets
        if not pool:
            return None
        return max(pool, key=lambda s: s.weight)

    @property
    def dominant_relation(self) -> EvidenceRelation:
        """
        Weighted vote across snippets.
        Higher-tier sources have more influence.
        Conflict detection: if top-tier SUPPORTS but lower tiers CONTRADICT → conflict flag.
        """
        if not self.snippets:
            return EvidenceRelation.UNRELATED
        score: dict[EvidenceRelation, float] = {r: 0.0 for r in EvidenceRelation}
        for s in self.snippets:
            score[s.relation] += s.weight
        return max(score, key=lambda r: score[r])


# ── Moderator verdict ─────────────────────────────────────────────────────────

class VerdictLabel(str, Enum):
    CORRECT   = "CORRECT"
    INCORRECT = "INCORRECT"
    UNCERTAIN = "UNCERTAIN"


VERDICT_SCORES: dict[VerdictLabel, float] = {
    VerdictLabel.CORRECT:   1.0,
    VerdictLabel.UNCERTAIN: 0.5,
    VerdictLabel.INCORRECT: 0.0,
}


class ModeratorVerdict(BaseModel):
    claim_id:          str
    claim_text:        str
    verdict:           VerdictLabel
    source_weight:     float                  = 0.0
    confidence:        float                  = 0.0    # verdict_score × source_weight
    evidence_summary:  str                    = ""
    correction:        Optional[str]          = None   # only when INCORRECT
    cascade_from:      Optional[str]          = None   # parent claim ID if cascaded
    cascade_flag:      bool                   = False
    sprint2_priority:  bool                   = False  # was [PRIORITY RETRIEVAL] in S2
    sprint2_high_conflict: bool               = False  # was [HIGH CONFLICT] in S2

    @model_validator(mode="after")
    def compute_confidence(self) -> "ModeratorVerdict":
        score = VERDICT_SCORES[self.verdict]
        self.confidence = round(score * self.source_weight, 4)
        return self


# ── Cascade event ─────────────────────────────────────────────────────────────

class CascadeEntry(BaseModel):
    failed_parent_id:  str
    failed_parent_verdict: VerdictLabel
    child_id:          str
    original_verdict:  VerdictLabel      # child's verdict before cascade
    cascaded_verdict:  VerdictLabel      # verdict after cascade propagation
    cascade_reason:    str               = ""


# ── Aggregate metrics ─────────────────────────────────────────────────────────

class Sprint3Metrics(BaseModel):
    total_claims:          int   = 0
    correct_count:         int   = 0
    incorrect_count:       int   = 0
    uncertain_count:       int   = 0
    cascade_count:         int   = 0
    retrieval_attempted:   int   = 0
    retrieval_success:     int   = 0
    accuracy:              float = 0.0   # correct / total
    hallucination_rate:    float = 0.0   # incorrect / total
    mean_confidence:       float = 0.0
    risk_level:            str   = "LOW" # LOW / MEDIUM / HIGH

    @model_validator(mode="after")
    def compute_derived(self) -> "Sprint3Metrics":
        n = self.total_claims or 1
        self.accuracy           = round(self.correct_count / n, 4)
        self.hallucination_rate = round(self.incorrect_count / n, 4)
        self.mean_confidence    = 0.0   # filled by runner
        hr = self.hallucination_rate
        self.risk_level = "LOW" if hr < 0.10 else ("MEDIUM" if hr < 0.30 else "HIGH")
        return self


# ── Sprint 3 complete output ──────────────────────────────────────────────────

class Sprint3Output(BaseModel):
    query:             str
    retrieval_results: list[RetrievalResult]   = Field(default_factory=list)
    verdicts:          list[ModeratorVerdict]  = Field(default_factory=list)
    cascade_log:       list[CascadeEntry]      = Field(default_factory=list)
    metrics:           Sprint3Metrics          = Field(default_factory=Sprint3Metrics)
    # Convenience buckets (populated by runner)
    correct_ids:   list[str] = Field(default_factory=list)
    incorrect_ids: list[str] = Field(default_factory=list)
    uncertain_ids: list[str] = Field(default_factory=list)

    def get_verdict(self, cid: str) -> Optional[ModeratorVerdict]:
        return next((v for v in self.verdicts if v.claim_id == cid), None)

    def get_retrieval(self, cid: str) -> Optional[RetrievalResult]:
        return next((r for r in self.retrieval_results if r.claim_id == cid), None)
