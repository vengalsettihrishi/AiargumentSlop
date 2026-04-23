"""Sprint 2 smoke tests — no API calls required."""
from sprint2.parser import parse_skeptic_verdicts, parse_proponent_rebuttal
from sprint2.models import SkepticStatus, CombinedStatus
from sprint2.debate import run_inter_skeptic_analysis
from sprint1.models import AtomicClaim, ClaimMarker

# ── Test 1: Skeptic parser ────────────────────────────────────────────────────
raw_a = """[SKEPTIC VERDICTS]
C1 -> [ACCEPTED]: Claim is straightforward and well-founded.
C2 -> [CONTESTED]: The date 1995 is likely wrong; the event occurred in 1993.
C3 -> [SUSPICIOUS]: The figure of 50 million is unverified without a source.
C4 -> [PLAUSIBLE]: Plausible but hard to confirm without data."""

verdicts_a = parse_skeptic_verdicts(raw_a, expected_ids={"C1","C2","C3","C4"})
assert len(verdicts_a) == 4, f"Expected 4 verdicts, got {len(verdicts_a)}"
assert verdicts_a[0].status == SkepticStatus.ACCEPTED
assert verdicts_a[1].status == SkepticStatus.CONTESTED
print("Test 1 – Skeptic parser: PASS")

# ── Test 2: Inter-skeptic analysis ────────────────────────────────────────────
claims = [AtomicClaim(id=f"C{i}", text=f"claim {i}") for i in range(1, 5)]
raw_b = """[SKEPTIC VERDICTS]
C1 -> [ACCEPTED]: Agreed.
C2 -> [PLAUSIBLE]: Seems reasonable to me.
C3 -> [CONTESTED]: This is factually incorrect based on available data.
C4 -> [SUSPICIOUS]: Needs verification."""
verdicts_b = parse_skeptic_verdicts(raw_b, expected_ids={"C1","C2","C3","C4"})

results = run_inter_skeptic_analysis(claims, verdicts_a, verdicts_b)
c2 = next(r for r in results if r.claim_id == "C2")
assert c2.disagreement is True, "C2 should be a disagreement"
assert c2.combined_status == CombinedStatus.CONTESTED, f"Got {c2.combined_status}"
c1 = next(r for r in results if r.claim_id == "C1")
assert c1.disagreement is False
print("Test 2 – Inter-skeptic analysis: PASS")

# ── Test 3: Proponent rebuttal parser ─────────────────────────────────────────
raw_prop = (
    "[PROPONENT REBUTTAL]\n"
    "C2 -> DEFEND\n"
    "  Objection (A): Date claimed as 1995\n"
    "  Response (A): Multiple primary sources confirm 1995 is correct.\n"
    "C3 -> REVISE\n"
    "  Original: The figure of 50 million is unverified\n"
    "  Revised:  Approximately 48 million users reported in the 2001 annual report\n"
    "  Reason:   Narrowing scope to a specific cited figure.\n"
)
contested = [AtomicClaim(id="C2", text="c2"), AtomicClaim(id="C3", text="c3")]
rebuttals = parse_proponent_rebuttal(raw_prop, contested)
assert len(rebuttals) == 2, f"Expected 2 rebuttals, got {len(rebuttals)}"
assert rebuttals[0].action.value == "DEFEND"
assert rebuttals[1].action.value == "REVISE"
assert rebuttals[1].revised_text is not None, "Revised text should be set"
print("Test 3 – Proponent parser: PASS")

# ── Test 4: Lineage init ──────────────────────────────────────────────────────
from sprint2.lineage import init_lineage
from sprint2.models import DedupReport, DedupCluster

dedup_report = DedupReport(
    clusters=[DedupCluster(
        canonical_id="C1",
        canonical_text="claim 1",
        alias_ids=["C5"],
        alias_texts=["claim 5 (alias)"],
        similarity_scores=[0.95],
        graph_updates=["C5 -> C1"],
    )],
    alias_map={"C5": "C1"},
    canonical_ids=["C1", "C2", "C3", "C4"],
    total_input_claims=5,
    total_canonical_claims=4,
    total_aliases_retired=1,
)
lineage = init_lineage(claims, dedup_report)
assert "C1" in lineage
assert lineage["C1"].alias_ids == ["C5"]
assert lineage["C2"].alias_ids == []
print("Test 4 – Lineage init: PASS")

print()
print("All Sprint 2 smoke tests passed.")
