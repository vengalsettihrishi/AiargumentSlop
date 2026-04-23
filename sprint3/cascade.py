"""
sprint3/cascade.py
──────────────────
Cascade Failure Propagation Engine.

Algorithm:
  1. Build a complete parent→children adjacency map from the dependency graph.
  2. Topological sort (Kahn's algorithm) to establish evaluation order.
  3. For every claim whose Moderator verdict is INCORRECT or UNCERTAIN:
       a. Walk all transitive descendants in topological order.
       b. Apply [CASCADE REVIEW]: if a child's current verdict is CORRECT
          or UNCERTAIN, downgrade it to UNCERTAIN (cannot be CORRECT when
          a prerequisite claim failed).
       c. Log each cascade event in a CascadeEntry.
  4. Return updated verdict list + cascade log.

Cascade rule:
  Parent INCORRECT  → child verdict becomes UNCERTAIN (at best)
  Parent UNCERTAIN  → child verdict becomes UNCERTAIN (at best)
  CORRECT child with a failed parent cannot remain CORRECT.
"""

from __future__ import annotations
import logging
from collections import deque
from typing import Optional

from sprint1.models import DependencyEdge
from sprint3.models import (
    ModeratorVerdict, VerdictLabel, CascadeEntry,
)

log = logging.getLogger(__name__)


# ── Graph utilities ───────────────────────────────────────────────────────────

def _build_children_map(dep_graph: list[DependencyEdge]) -> dict[str, list[str]]:
    """parent_id → [child_ids]"""
    graph: dict[str, list[str]] = {}
    for edge in dep_graph:
        graph.setdefault(edge.parent, []).extend(edge.children)
    return graph


def _build_parent_map(dep_graph: list[DependencyEdge]) -> dict[str, list[str]]:
    """child_id → [parent_ids]  (reverse edges)"""
    rmap: dict[str, list[str]] = {}
    for edge in dep_graph:
        for child in edge.children:
            rmap.setdefault(child, []).append(edge.parent)
    return rmap


def _topological_order(
    all_ids: list[str],
    children_map: dict[str, list[str]],
) -> list[str]:
    """
    Kahn's algorithm — returns claim IDs in topological order.
    Claims with no parents come first (roots), leaves last.
    Falls back to numeric-ID order if graph has cycles (shouldn't happen per spec).
    """
    parent_count: dict[str, int] = {cid: 0 for cid in all_ids}
    for parent, children in children_map.items():
        for child in children:
            if child in parent_count:
                parent_count[child] += 1

    queue = deque(cid for cid, cnt in parent_count.items() if cnt == 0)
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for child in children_map.get(node, []):
            if child not in parent_count:
                continue
            parent_count[child] -= 1
            if parent_count[child] == 0:
                queue.append(child)

    # Handle any remaining (cycle fallback)
    remaining = [cid for cid in all_ids if cid not in order]
    if remaining:
        log.warning("Cycle or orphan detected in dependency graph — appending: %s", remaining)
        order.extend(sorted(remaining, key=lambda x: int(x[1:])))

    return order


def _all_transitive_descendants(
    start_id: str,
    children_map: dict[str, list[str]],
) -> list[str]:
    """BFS — all claim IDs reachable from start_id (not including start_id)."""
    visited: set[str] = set()
    queue   = deque(children_map.get(start_id, []))
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(children_map.get(node, []))
    return list(visited)


# ── Main cascade engine ───────────────────────────────────────────────────────

_FAILING_VERDICTS = {VerdictLabel.INCORRECT, VerdictLabel.UNCERTAIN}


def run_cascade(
    verdicts: list[ModeratorVerdict],
    dep_graph: list[DependencyEdge],
) -> tuple[list[ModeratorVerdict], list[CascadeEntry]]:
    """
    Apply cascade failure propagation.

    Args:
        verdicts:  List of ModeratorVerdict objects (pre-cascade).
        dep_graph: Sprint 1 / Sprint 2 dependency graph.

    Returns:
        (updated_verdicts, cascade_log)
    """
    verdict_map    = {v.claim_id: v for v in verdicts}
    children_map   = _build_children_map(dep_graph)
    all_ids        = list(verdict_map.keys())
    topo_order     = _topological_order(all_ids, children_map)
    cascade_log: list[CascadeEntry] = []

    # Process claims in topological order so parent cascades propagate before
    # their children are evaluated
    for cid in topo_order:
        v = verdict_map.get(cid)
        if v is None:
            continue

        if v.verdict not in _FAILING_VERDICTS:
            continue   # parent is CORRECT — no cascade needed

        # This claim failed → propagate to all transitive descendants
        descendants = _all_transitive_descendants(cid, children_map)
        for child_id in descendants:
            child = verdict_map.get(child_id)
            if child is None:
                continue

            original_verdict = child.verdict

            # A child cannot be CORRECT if a prerequisite failed
            if child.verdict == VerdictLabel.CORRECT:
                new_verdict = VerdictLabel.UNCERTAIN
                cascade_reason = (
                    f"Parent claim {cid} was marked {v.verdict.value}; "
                    f"child claim cannot remain CORRECT without a valid prerequisite."
                )
                # Rebuild verdict with cascade annotations
                verdict_map[child_id] = child.model_copy(update={
                    "verdict":        new_verdict,
                    "cascade_flag":   True,
                    "cascade_from":   cid,
                    "confidence":     round(0.5 * child.source_weight, 4),
                    "evidence_summary": (
                        f"[CASCADE from {cid}] {child.evidence_summary}"
                    ),
                })

                cascade_log.append(CascadeEntry(
                    failed_parent_id=cid,
                    failed_parent_verdict=v.verdict,
                    child_id=child_id,
                    original_verdict=original_verdict,
                    cascaded_verdict=new_verdict,
                    cascade_reason=cascade_reason,
                ))
                log.info(
                    "CASCADE: %s (%s) → %s: CORRECT → UNCERTAIN",
                    cid, v.verdict.value, child_id,
                )

            elif child.verdict == VerdictLabel.UNCERTAIN and not child.cascade_flag:
                # Already UNCERTAIN — just annotate the cascade source if not already set
                verdict_map[child_id] = child.model_copy(update={
                    "cascade_flag": True,
                    "cascade_from": cid,
                    "evidence_summary": (
                        f"[CASCADE from {cid}] {child.evidence_summary}"
                    ),
                })
                cascade_log.append(CascadeEntry(
                    failed_parent_id=cid,
                    failed_parent_verdict=v.verdict,
                    child_id=child_id,
                    original_verdict=original_verdict,
                    cascaded_verdict=VerdictLabel.UNCERTAIN,
                    cascade_reason=(
                        f"Parent {cid} failed; child was already UNCERTAIN — cascade annotated."
                    ),
                ))

    updated = [verdict_map.get(v.claim_id, v) for v in verdicts]
    log.info(
        "Cascade complete: %d event(s) triggered across %d failing claim(s).",
        len(cascade_log),
        sum(1 for v in verdicts if v.verdict in _FAILING_VERDICTS),
    )
    return updated, cascade_log
