"""
Sprint 3 — Multi-Source RAG Retrieval, Credibility Scoring & Moderator Verdicts

Public API:
    run_sprint3(sprint1_output, sprint2_output)  → Sprint3Output
    load_sprint1_output()                        → Sprint1Output
    load_sprint2_output()                        → Sprint2Output
"""

from sprint3.runner import run_sprint3, load_sprint1_output, load_sprint2_output
from sprint3.models import (
    Sprint3Output, Sprint3Metrics,
    RetrievalResult, EvidenceSnippet,
    ModeratorVerdict, CascadeEntry,
    VerdictLabel, SourceTier, EvidenceRelation,
    TIER_WEIGHTS, VERDICT_SCORES,
)
from sprint3.credibility import classify_domain
from sprint3.cascade import run_cascade

__all__ = [
    "run_sprint3",
    "load_sprint1_output",
    "load_sprint2_output",
    "Sprint3Output",
    "Sprint3Metrics",
    "RetrievalResult",
    "EvidenceSnippet",
    "ModeratorVerdict",
    "CascadeEntry",
    "VerdictLabel",
    "SourceTier",
    "EvidenceRelation",
    "TIER_WEIGHTS",
    "VERDICT_SCORES",
    "classify_domain",
    "run_cascade",
]
