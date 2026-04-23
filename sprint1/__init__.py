"""
Sprint 1 — Answer Generation & Atomic Decomposition

Public API:
    run_sprint1(query)  → Sprint1Output
    Sprint1Output, AtomicClaim, DependencyEdge, ClaimMarker
"""

from sprint1.runner import run_sprint1
from sprint1.models import Sprint1Output, AtomicClaim, DependencyEdge, ClaimMarker

__all__ = [
    "run_sprint1",
    "Sprint1Output",
    "AtomicClaim",
    "DependencyEdge",
    "ClaimMarker",
]
