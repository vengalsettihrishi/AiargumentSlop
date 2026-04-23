"""
sprint4/models.py
─────────────────
Pydantic v2 data models for Sprint 4.

Model hierarchy:
  DependencyIntegrity  — STABLE / DEGRADED / COLLAPSED
  HallucinationRisk    — LOW / MEDIUM / HIGH
  ClaimSummaryRow      — one row in the claims evaluation table
  SystemMetrics        — full computed metrics report
  Sprint4Output        — top-level final deliverable object
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ── Categorical assessments ───────────────────────────────────────────────────

class DependencyIntegrity(str, Enum):
    STABLE    = "STABLE"     # 0 cascade failures
    DEGRADED  = "DEGRADED"   # 1–2 cascade failures
    COLLAPSED = "COLLAPSED"  # 3+ cascade failures


class HallucinationRisk(str, Enum):
    LOW    = "LOW"     # < 10%
    MEDIUM = "MEDIUM"  # 10–30%
    HIGH   = "HIGH"    # > 30%


# ── Per-claim evaluation table row ───────────────────────────────────────────

class ClaimSummaryRow(BaseModel):
    claim_id:           str
    claim_text:         str
    sprint1_marker:     str          = ""    # SUPERLATIVE / TIME-SENSITIVE / ""
    debate_status:      str          = ""    # Sprint 2 combined status
    verdict:            str          = ""    # CORRECT / INCORRECT / UNCERTAIN
    confidence:         float        = 0.0
    source_weight:      float        = 0.0
    evidence_summary:   str          = ""
    correction:         Optional[str] = None
    cascade_flag:       bool         = False
    cascade_from:       Optional[str] = None
    high_conflict:      bool         = False

    @property
    def verdict_tag(self) -> str:
        if self.cascade_flag and self.cascade_from:
            return f"{self.verdict} [CASCADE from {self.cascade_from}]"
        return self.verdict


# ── Full system metrics ───────────────────────────────────────────────────────

class SystemMetrics(BaseModel):
    # Claim counts
    total_claims:        int   = 0
    correct_count:       int   = 0
    incorrect_count:     int   = 0
    uncertain_count:     int   = 0
    cascade_flagged:     int   = 0

    # Accuracy
    accuracy:            float = 0.0   # correct / total
    hallucination_rate:  float = 0.0   # incorrect / total

    # Confidence (Bayesian aggregate)
    mean_confidence:     float = 0.0   # weighted mean of all Confidence(Claim) values
    avg_source_weight:   float = 0.0   # mean source weight across all claims

    # Debate metrics (from Sprint 2)
    debate_rounds_used:      int   = 0
    final_convergence:       float = 0.0
    high_conflict_ids:       list[str] = Field(default_factory=list)

    # Categorical assessments
    hallucination_risk:      HallucinationRisk   = HallucinationRisk.LOW
    dependency_integrity:    DependencyIntegrity = DependencyIntegrity.STABLE
    confidence_score:        float               = 0.0   # = mean_confidence

    @model_validator(mode="after")
    def compute_categorical(self) -> "SystemMetrics":
        n = self.total_claims or 1
        self.accuracy           = round(self.correct_count / n, 4)
        self.hallucination_rate = round(self.incorrect_count / n, 4)

        hr = self.hallucination_rate
        if hr < 0.10:
            self.hallucination_risk = HallucinationRisk.LOW
        elif hr < 0.30:
            self.hallucination_risk = HallucinationRisk.MEDIUM
        else:
            self.hallucination_risk = HallucinationRisk.HIGH

        cf = self.cascade_flagged
        if cf == 0:
            self.dependency_integrity = DependencyIntegrity.STABLE
        elif cf <= 2:
            self.dependency_integrity = DependencyIntegrity.DEGRADED
        else:
            self.dependency_integrity = DependencyIntegrity.COLLAPSED

        self.confidence_score = self.mean_confidence
        return self


# ── Sprint 4 final output ─────────────────────────────────────────────────────

class Sprint4Output(BaseModel):
    query:              str
    # Stage 1 — Refined prose answer
    refined_answer:     str                  = ""
    # Stage 2 — Per-claim evaluation table
    claim_rows:         list[ClaimSummaryRow] = Field(default_factory=list)
    # Stage 3 — System metrics
    metrics:            SystemMetrics        = Field(default_factory=SystemMetrics)
    # Sprint 2 lineage summary (for transparency report)
    dedup_aliases_retired:  int = 0
    debate_exit_reason:     str = ""
