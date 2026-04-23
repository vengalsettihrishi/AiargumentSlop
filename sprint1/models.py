"""
sprint1/models.py
─────────────────
Pydantic v2 data models that represent the structured output of Sprint 1.
These models are serialised to JSON and passed downstream to Sprint 2+.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Claim markers ─────────────────────────────────────────────────────────────

class ClaimMarker(str, Enum):
    SUPERLATIVE    = "SUPERLATIVE"     # uses first / only / largest / best …
    TIME_SENSITIVE = "TIME-SENSITIVE"  # may change over time or is date-bound
    NONE           = ""                # no special marker


# ── Individual claim ─────────────────────────────────────────────────────────

class AtomicClaim(BaseModel):
    id: str                              # "C1", "C2", …
    text: str                            # The claim assertion
    marker: ClaimMarker = ClaimMarker.NONE
    # Set by downstream sprints — leave None at Sprint 1
    verdict: Optional[str] = None
    evidence: Optional[str] = None
    cascade_flag: bool = False           # True if parent was INCORRECT/UNCERTAIN

    @property
    def label(self) -> str:
        suffix = f" [{self.marker.value}]" if self.marker != ClaimMarker.NONE else ""
        return f"{self.id}: {self.text}{suffix}"


# ── Dependency edge ───────────────────────────────────────────────────────────

class DependencyEdge(BaseModel):
    parent: str          # claim id, e.g. "C1"
    children: list[str]  # list of claim ids that depend on parent

    def __str__(self) -> str:
        children_str = ", ".join(self.children) if self.children else "(none)"
        return f"{self.parent} → {children_str}"


# ── Sprint 1 complete output ──────────────────────────────────────────────────

class Sprint1Output(BaseModel):
    query: str                           = Field(description="Original user query")
    proponent_answer: str                = Field(description="Full prose answer from Proponent Agent")
    claims: list[AtomicClaim]            = Field(description="Ordered list of atomic claims")
    dependency_graph: list[DependencyEdge] = Field(description="Directed dependency edges")
    # Metadata
    model_used: str                      = ""
    provider: str                        = ""
    total_claims: int                    = 0
    superlative_count: int               = 0
    time_sensitive_count: int            = 0

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        self.total_claims = len(self.claims)
        self.superlative_count = sum(
            1 for c in self.claims if c.marker == ClaimMarker.SUPERLATIVE
        )
        self.time_sensitive_count = sum(
            1 for c in self.claims if c.marker == ClaimMarker.TIME_SENSITIVE
        )

    def get_claim(self, cid: str) -> Optional[AtomicClaim]:
        """Retrieve a claim by its ID."""
        return next((c for c in self.claims if c.id == cid), None)

    def get_dependents(self, cid: str) -> list[str]:
        """Return all child claim IDs that depend on cid."""
        for edge in self.dependency_graph:
            if edge.parent == cid:
                return edge.children
        return []
