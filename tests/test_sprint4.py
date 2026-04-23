"""
tests/test_sprint4.py
─────────────────────
Offline smoke tests for Sprint 4 — no API calls, no LLM.

Tests cover:
  1. DependencyIntegrity thresholds (0 → STABLE, 1-2 → DEGRADED, 3+ → COLLAPSED)
  2. HallucinationRisk thresholds (< 10% → LOW, 10-30% → MEDIUM, > 30% → HIGH)
  3. SystemMetrics auto-computed fields (accuracy, hallucination_rate, risk, integrity)
  4. ClaimSummaryRow.verdict_tag with and without cascade annotations
  5. Synthesis output parser — CLAIMS EVALUATION table extraction
  6. Synthesis output parser — FINAL ANSWER extraction
  7. Sprint4Output model round-trip serialisation via model_dump()
  8. Plain-text report generation (no file I/O — just string output)
"""

import sys
sys.path.insert(0, ".")

from sprint4.models import (
    SystemMetrics, ClaimSummaryRow,
    DependencyIntegrity, HallucinationRisk, Sprint4Output,
)
from sprint4.synthesizer import parse_synthesis_output
from sprint4.report import _build_plain_report


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_metrics(correct, incorrect, uncertain, cascade, debate_rounds=2, convergence=0.90):
    return SystemMetrics(
        total_claims=correct + incorrect + uncertain,
        correct_count=correct,
        incorrect_count=incorrect,
        uncertain_count=uncertain,
        cascade_flagged=cascade,
        mean_confidence=correct / max(correct + incorrect + uncertain, 1),
        avg_source_weight=0.8,
        debate_rounds_used=debate_rounds,
        final_convergence=convergence,
    )


# ── Test 1: DependencyIntegrity thresholds ───────────────────────────────────

m_stable    = make_metrics(8, 1, 1, cascade=0)
m_degraded  = make_metrics(7, 1, 2, cascade=2)
m_collapsed = make_metrics(5, 2, 3, cascade=3)

assert m_stable.dependency_integrity    == DependencyIntegrity.STABLE,    f"0 cascade → STABLE, got {m_stable.dependency_integrity}"
assert m_degraded.dependency_integrity  == DependencyIntegrity.DEGRADED,  f"2 cascade → DEGRADED, got {m_degraded.dependency_integrity}"
assert m_collapsed.dependency_integrity == DependencyIntegrity.COLLAPSED, f"3 cascade → COLLAPSED, got {m_collapsed.dependency_integrity}"
print("Test 1 - DependencyIntegrity thresholds: PASS")


# ── Test 2: HallucinationRisk thresholds ──────────────────────────────────────

# 0 incorrect out of 10  → 0% → LOW
m_low    = make_metrics(10, 0, 0, cascade=0)
# 2 incorrect out of 10  → 20% → MEDIUM
m_medium = make_metrics(8,  2, 0, cascade=0)
# 4 incorrect out of 10  → 40% → HIGH
m_high   = make_metrics(6,  4, 0, cascade=0)

assert m_low.hallucination_risk    == HallucinationRisk.LOW,    f"0% → LOW, got {m_low.hallucination_risk}"
assert m_medium.hallucination_risk == HallucinationRisk.MEDIUM, f"20% → MEDIUM, got {m_medium.hallucination_risk}"
assert m_high.hallucination_risk   == HallucinationRisk.HIGH,   f"40% → HIGH, got {m_high.hallucination_risk}"
print("Test 2 - HallucinationRisk thresholds: PASS")


# ── Test 3: SystemMetrics auto-computed accuracy & confidence_score ───────────

m = make_metrics(7, 2, 1, cascade=1, debate_rounds=3, convergence=0.72)
assert abs(m.accuracy - 0.7) < 0.001,            f"accuracy = 7/10 = 0.70, got {m.accuracy}"
assert abs(m.hallucination_rate - 0.2) < 0.001,  f"hallucination_rate = 2/10 = 0.20, got {m.hallucination_rate}"
assert m.confidence_score == m.mean_confidence,   "confidence_score must equal mean_confidence"
assert m.debate_rounds_used == 3
assert abs(m.final_convergence - 0.72) < 0.001
print("Test 3 - SystemMetrics computed fields: PASS")


# ── Test 4: ClaimSummaryRow.verdict_tag ──────────────────────────────────────

row_plain = ClaimSummaryRow(
    claim_id="C1", claim_text="The sky is blue.", verdict="CORRECT",
    confidence=1.0, source_weight=1.0,
)
assert row_plain.verdict_tag == "CORRECT", f"No cascade → bare verdict, got {row_plain.verdict_tag}"

row_cascade = ClaimSummaryRow(
    claim_id="C3", claim_text="X is true.", verdict="UNCERTAIN",
    confidence=0.35, source_weight=0.7,
    cascade_flag=True, cascade_from="C1",
)
assert row_cascade.verdict_tag == "UNCERTAIN [CASCADE from C1]", \
    f"Cascade tag wrong: {row_cascade.verdict_tag}"
print("Test 4 - ClaimSummaryRow.verdict_tag: PASS")


# ── Test 5 & 6: Synthesis LLM output parser ───────────────────────────────────

SAMPLE_LLM_OUTPUT = """
CLAIMS EVALUATION:
  C1: The Eiffel Tower was built in 1889. -> CORRECT
      Evidence: Britannica — construction completed 1889 for the World's Fair

  C2: It is the tallest structure in the world. -> INCORRECT
      Evidence: Wikipedia — Burj Khalifa (828m) surpassed it | Correction: It was the world's tallest structure until 1930

  C3: It attracts over 100 million visitors per year. -> UNCERTAIN
      Evidence: insufficient — no verified annual figure found

  C4: The tower was designed by Gustave Eiffel personally. -> UNCERTAIN [CASCADE from C2]
      Evidence: parent claim C2 was marked INCORRECT

FINAL ANSWER:
The Eiffel Tower was constructed in 1889 for the Paris World's Fair. While it was once
the world's tallest structure, that distinction now belongs to the Burj Khalifa. It is
unclear exactly how many visitors it attracts annually, as reliable figures vary
significantly. The claim that Gustave Eiffel personally designed the tower is uncertain
given the dependency on other contested facts.
"""

# Minimal stub objects for the parser (no LLM calls needed)
class _FakeClaim:
    def __init__(self, cid, text, marker=""):
        self.id   = cid
        self.text = text
        class _M:
            value = marker
        self.marker = _M()

class _FakeVerdict:
    def __init__(self, cid, text, verdict="UNCERTAIN", conf=0.5, sw=0.7,
                 ev="", corr=None, cascade=False, cf=None, hc=False):
        self.claim_id             = cid
        self.claim_text           = text
        self.verdict              = type("V", (), {"value": verdict})()
        self.confidence           = conf
        self.source_weight        = sw
        self.evidence_summary     = ev
        self.correction           = corr
        self.cascade_flag         = cascade
        self.cascade_from         = cf
        self.sprint2_high_conflict = hc

class _FakeS1:
    def __init__(self):
        self.claims = [
            _FakeClaim("C1", "The Eiffel Tower was built in 1889."),
            _FakeClaim("C2", "It is the tallest structure in the world."),
            _FakeClaim("C3", "It attracts over 100 million visitors per year."),
            _FakeClaim("C4", "The tower was designed by Gustave Eiffel personally."),
        ]
    def get_claim(self, cid): return next((c for c in self.claims if c.id == cid), None)

class _FakeS3:
    def __init__(self):
        self.verdicts = [
            _FakeVerdict("C1", "The Eiffel Tower was built in 1889.",         "CORRECT",   1.0, 1.0, "Britannica"),
            _FakeVerdict("C2", "It is the tallest structure in the world.",    "INCORRECT", 0.0, 1.0, "Wikipedia", "Burj Khalifa surpassed it"),
            _FakeVerdict("C3", "It attracts over 100 million visitors per year.", "UNCERTAIN", 0.35, 0.7),
            _FakeVerdict("C4", "The tower was designed by Gustave Eiffel personally.", "UNCERTAIN", 0.35, 0.7, cascade=True, cf="C2"),
        ]

rows, final_answer = parse_synthesis_output(SAMPLE_LLM_OUTPUT, _FakeS1(), _FakeS3())

# Test 5: Claims table
assert len(rows) == 4, f"Expected 4 rows, got {len(rows)}"

verdict_map = {r.claim_id: r for r in rows}
assert verdict_map["C1"].verdict == "CORRECT",   f"C1 should be CORRECT, got {verdict_map['C1'].verdict}"
assert verdict_map["C2"].verdict == "INCORRECT", f"C2 should be INCORRECT, got {verdict_map['C2'].verdict}"
assert verdict_map["C2"].correction is not None, "C2 should have a correction"
assert verdict_map["C3"].verdict == "UNCERTAIN", f"C3 should be UNCERTAIN"
assert verdict_map["C4"].cascade_flag is True,   "C4 should be cascade-flagged"
assert verdict_map["C4"].cascade_from == "C2",   f"C4 cascade_from should be C2, got {verdict_map['C4'].cascade_from}"
print("Test 5 - Synthesis parser (claims table): PASS")

# Test 6: Final answer extraction
assert "Eiffel Tower" in final_answer, "Final answer should mention Eiffel Tower"
assert "Burj Khalifa" in final_answer, "Final answer should include INCORRECT correction"
assert "unclear" in final_answer.lower(), "Final answer should qualify UNCERTAIN claims"
assert len(final_answer) > 100, f"Final answer too short: {len(final_answer)} chars"
print("Test 6 - Synthesis parser (final answer): PASS")


# ── Test 7: Sprint4Output model_dump round-trip ───────────────────────────────

output = Sprint4Output(
    query="Test query",
    refined_answer="Test answer.",
    claim_rows=rows,
    metrics=m,
    dedup_aliases_retired=2,
    debate_exit_reason="EARLY EXIT (convergence >= 0.85)",
)
dumped = output.model_dump()
assert dumped["query"] == "Test query"
assert dumped["metrics"]["total_claims"] == 10
assert len(dumped["claim_rows"]) == 4
# Re-validate from dict
output2 = Sprint4Output.model_validate(dumped)
assert output2.metrics.total_claims == 10
assert output2.metrics.hallucination_risk.value == "MEDIUM"
print("Test 7 - Sprint4Output model_dump round-trip: PASS")


# ── Test 8: Plain-text report generation ─────────────────────────────────────

report_text = _build_plain_report(output)
assert "CLAIMS EVALUATION:" in report_text
assert "FINAL ANSWER:"      in report_text
assert "METRICS:"           in report_text
assert "CONFIDENCE SCORE"   in report_text
assert "HALLUCINATION RISK" in report_text
assert "DEPENDENCY INTEGRITY" in report_text
assert "C1" in report_text
assert "CORRECT" in report_text
assert "INCORRECT" in report_text
print("Test 8 - Plain-text report generation: PASS")


print()
print("All Sprint 4 smoke tests passed.")
