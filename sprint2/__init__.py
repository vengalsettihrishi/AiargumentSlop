"""
Sprint 2 — Adversarial Debate, Deduplication & Lineage Tracking

Public API:
    run_sprint2(sprint1_output)  → Sprint2Output
    load_sprint1_output()        → Sprint1Output  (disk loader)
"""

from sprint2.runner import run_sprint2, load_sprint1_output
from sprint2.models import (
    Sprint2Output, LineageRecord, DedupReport,
    DebateRound, ConvergenceScore,
    SkepticStatus, CombinedStatus, DisagreementType,
    ProponentAction, DebateExitReason,
)

__all__ = [
    "run_sprint2",
    "load_sprint1_output",
    "Sprint2Output",
    "LineageRecord",
    "DedupReport",
    "DebateRound",
    "ConvergenceScore",
    "SkepticStatus",
    "CombinedStatus",
    "DisagreementType",
    "ProponentAction",
    "DebateExitReason",
]
