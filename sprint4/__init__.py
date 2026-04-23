"""
Sprint 4 — Synthesis, Final Answer & Transparency Report

Public API:
    run_sprint4(sprint1_output, sprint2_output, sprint3_output) -> Sprint4Output
    load_sprint1_output()  -> Sprint1Output
    load_sprint2_output()  -> Sprint2Output
    load_sprint3_output()  -> Sprint3Output
"""

from sprint4.runner import (
    run_sprint4,
    load_sprint1_output,
    load_sprint2_output,
    load_sprint3_output,
)
from sprint4.models import (
    Sprint4Output,
    SystemMetrics,
    ClaimSummaryRow,
    DependencyIntegrity,
    HallucinationRisk,
)
from sprint4.report import render_full_report, save_plain_report

__all__ = [
    "run_sprint4",
    "load_sprint1_output",
    "load_sprint2_output",
    "load_sprint3_output",
    "Sprint4Output",
    "SystemMetrics",
    "ClaimSummaryRow",
    "DependencyIntegrity",
    "HallucinationRisk",
    "render_full_report",
    "save_plain_report",
]
