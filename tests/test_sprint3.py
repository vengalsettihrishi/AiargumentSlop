"""Sprint 3 offline smoke tests — no API calls required."""
import sys; sys.path.insert(0, ".")

from sprint3.credibility import classify_domain, detect_conflict
from sprint3.models import (
    SourceTier, EvidenceRelation, EvidenceSnippet,
    RetrievalResult, VerdictLabel, ModeratorVerdict,
)
from sprint3.cascade import run_cascade, _build_children_map, _topological_order
from sprint1.models import DependencyEdge

# ── Test 1: Credibility tier classification ───────────────────────────────────
assert classify_domain("https://www.nature.com/articles/xxx") == SourceTier.TIER_1, "nature.com must be Tier 1"
assert classify_domain("https://pubmed.ncbi.nlm.nih.gov/123456/") == SourceTier.TIER_1, "pubmed must be Tier 1"
assert classify_domain("https://cdc.gov/flu") == SourceTier.TIER_1, ".gov must be Tier 1"
assert classify_domain("https://www.mit.edu/research") == SourceTier.TIER_1, ".edu must be Tier 1"
assert classify_domain("https://www.bbc.com/news/science") == SourceTier.TIER_2, "bbc.com must be Tier 2"
assert classify_domain("https://www.wikipedia.org/wiki/Python") == SourceTier.TIER_2, "wikipedia must be Tier 2"
assert classify_domain("https://some-random-blog.io/post/123") == SourceTier.TIER_3, "unknown must be Tier 3"
assert classify_domain("", source_name="Nature, 2023") == SourceTier.TIER_1, "source_name heuristic: Nature"
assert classify_domain("", source_name="BBC News") == SourceTier.TIER_2, "source_name heuristic: BBC"
print("Test 1 – Credibility classifier: PASS")

# ── Test 2: EvidenceSnippet weight auto-sync ─────────────────────────────────
s = EvidenceSnippet(
    source_name="Nature", url="https://nature.com/x",
    tier=SourceTier.TIER_1, passage="test passage",
    relation=EvidenceRelation.SUPPORTS,
)
assert s.weight == 1.0, f"Tier 1 weight should be 1.0, got {s.weight}"
s2 = EvidenceSnippet(
    source_name="BBC", url="https://bbc.com/x",
    tier=SourceTier.TIER_2, passage="test passage",
    relation=EvidenceRelation.CONTRADICTS,
)
assert s2.weight == 0.7, f"Tier 2 weight should be 0.7, got {s2.weight}"
print("Test 2 – EvidenceSnippet weight sync: PASS")

# ── Test 3: Conflict detection ────────────────────────────────────────────────
conflict_snippets = [s, s2]   # Tier1 SUPPORTS vs Tier2 CONTRADICTS
has_conflict, note = detect_conflict(conflict_snippets)
assert has_conflict, "Should detect conflict between Tier1 SUPPORTS and Tier2 CONTRADICTS"
assert "precedence" in note.lower(), f"Note should mention precedence: {note}"
no_conflict, _ = detect_conflict([s])
assert not no_conflict, "Single snippet should not trigger conflict"
print("Test 3 – Conflict detection: PASS")

# ── Test 4: RetrievalResult dominant_relation ────────────────────────────────
r = RetrievalResult(
    claim_id="C1",
    claim_text="Test claim",
    snippets=[s, s2],   # Tier1 SUPPORTS (w=1.0) vs Tier2 CONTRADICTS (w=0.7)
    retrieved=True,
)
# SUPPORTS has weight 1.0, CONTRADICTS has 0.7 → dominant is SUPPORTS
assert r.dominant_relation == EvidenceRelation.SUPPORTS, f"Got {r.dominant_relation}"
print("Test 4 – Dominant relation (weighted vote): PASS")

# ── Test 5: ModeratorVerdict confidence computation ───────────────────────────
v = ModeratorVerdict(
    claim_id="C1",
    claim_text="test",
    verdict=VerdictLabel.CORRECT,
    source_weight=1.0,
)
assert v.confidence == 1.0, f"CORRECT × 1.0 = 1.0, got {v.confidence}"
v2 = ModeratorVerdict(
    claim_id="C2",
    claim_text="test",
    verdict=VerdictLabel.UNCERTAIN,
    source_weight=0.7,
)
assert abs(v2.confidence - 0.35) < 0.001, f"UNCERTAIN(0.5) × 0.7 = 0.35, got {v2.confidence}"
v3 = ModeratorVerdict(
    claim_id="C3",
    claim_text="test",
    verdict=VerdictLabel.INCORRECT,
    source_weight=1.0,
)
assert v3.confidence == 0.0, f"INCORRECT × 1.0 = 0.0, got {v3.confidence}"
print("Test 5 – Moderator confidence computation: PASS")

# ── Test 6: Cascade engine – topological sort ─────────────────────────────────
dep_graph = [
    DependencyEdge(parent="C1", children=["C2", "C3"]),
    DependencyEdge(parent="C2", children=["C4"]),
    DependencyEdge(parent="C3", children=[]),
    DependencyEdge(parent="C4", children=[]),
]
children_map = _build_children_map(dep_graph)
topo = _topological_order(["C1","C2","C3","C4"], children_map)
# C1 must come before C2, C3 before C4
assert topo.index("C1") < topo.index("C2"), "C1 must precede C2"
assert topo.index("C1") < topo.index("C3"), "C1 must precede C3"
assert topo.index("C2") < topo.index("C4"), "C2 must precede C4"
print("Test 6 – Topological sort: PASS")

# ── Test 7: Cascade engine – CORRECT child downgraded to UNCERTAIN ────────────
verdicts = [
    ModeratorVerdict(claim_id="C1", claim_text="c1", verdict=VerdictLabel.INCORRECT, source_weight=1.0),
    ModeratorVerdict(claim_id="C2", claim_text="c2", verdict=VerdictLabel.CORRECT,   source_weight=0.7),
    ModeratorVerdict(claim_id="C3", claim_text="c3", verdict=VerdictLabel.CORRECT,   source_weight=0.4),
    ModeratorVerdict(claim_id="C4", claim_text="c4", verdict=VerdictLabel.CORRECT,   source_weight=1.0),
]

updated, cascade_log = run_cascade(verdicts, dep_graph)
verdict_map = {v.claim_id: v for v in updated}

assert verdict_map["C1"].verdict == VerdictLabel.INCORRECT, "C1 should remain INCORRECT"
assert verdict_map["C2"].verdict == VerdictLabel.UNCERTAIN, "C2 should cascade to UNCERTAIN (child of INCORRECT C1)"
assert verdict_map["C3"].verdict == VerdictLabel.UNCERTAIN, "C3 should cascade to UNCERTAIN (child of INCORRECT C1)"
assert verdict_map["C4"].verdict == VerdictLabel.UNCERTAIN, "C4 should cascade to UNCERTAIN (grandchild of C1 via C2)"
assert verdict_map["C2"].cascade_flag is True, "C2 should have cascade_flag"
assert verdict_map["C2"].cascade_from == "C1", f"C2.cascade_from should be C1, got {verdict_map['C2'].cascade_from}"
assert len(cascade_log) >= 3, f"Expected >= 3 cascade events, got {len(cascade_log)}"
print("Test 7 – Cascade propagation (INCORRECT → descendants): PASS")

# ── Test 8: Cascade – UNCERTAIN parent also propagates ────────────────────────
verdicts2 = [
    ModeratorVerdict(claim_id="C1", claim_text="c1", verdict=VerdictLabel.UNCERTAIN, source_weight=0.5),
    ModeratorVerdict(claim_id="C2", claim_text="c2", verdict=VerdictLabel.CORRECT,   source_weight=0.7),
    ModeratorVerdict(claim_id="C3", claim_text="c3", verdict=VerdictLabel.CORRECT,   source_weight=0.4),
    ModeratorVerdict(claim_id="C4", claim_text="c4", verdict=VerdictLabel.CORRECT,   source_weight=1.0),
]
updated2, cascade_log2 = run_cascade(verdicts2, dep_graph)
vm2 = {v.claim_id: v for v in updated2}
assert vm2["C2"].verdict == VerdictLabel.UNCERTAIN, "UNCERTAIN parent should cascade to children"
print("Test 8 – Cascade propagation (UNCERTAIN → descendants): PASS")

print()
print("All Sprint 3 smoke tests passed.")
