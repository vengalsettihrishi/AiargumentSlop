"""
sprint2/dedup.py
────────────────
Semantic deduplication stage (DEDUP ANALYST).

Strategy
────────
1.  Embed all claims using the configured OpenAI embedding model.
    Falls back to a simple Jaccard-similarity heuristic when no
    embedding key is available (so the system degrades gracefully).
2.  Compute pairwise cosine similarity.
3.  Union-Find clustering at threshold ≥ DEDUP_THRESHOLD (default 0.92).
4.  For each cluster, elect the "most precise" canonical claim
    (longest text wins as a proxy for specificity).
5.  Update the dependency graph: any edge pointing to an alias ID
    is re-routed to the cluster's canonical ID.
6.  Return a DedupReport + the pruned canonical claim list.
"""

from __future__ import annotations
import logging
import math
from typing import Optional

from sprint1.models import AtomicClaim, DependencyEdge
from sprint2.models import DedupCluster, DedupReport
from config import settings

log = logging.getLogger(__name__)

DEDUP_THRESHOLD: float = 0.92   # cosine similarity threshold


# ── Embedding helpers ─────────────────────────────────────────────────────────

def _get_embeddings(texts: list[str]) -> Optional[list[list[float]]]:
    """Return embeddings via OpenAI, or None on failure."""
    if not settings.OPENAI_API_KEY:
        log.warning("No OPENAI_API_KEY — falling back to Jaccard similarity for dedup.")
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]
    except Exception as exc:  # noqa: BLE001
        log.warning("Embedding API failed (%s) — falling back to Jaccard.", exc)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _jaccard(a: str, b: str) -> float:
    """Character-trigram Jaccard similarity as embedding fallback."""
    def trigrams(s: str) -> set[str]:
        s = s.lower()
        return {s[i:i+3] for i in range(len(s) - 2)}
    t_a, t_b = trigrams(a), trigrams(b)
    if not t_a or not t_b:
        return 0.0
    return len(t_a & t_b) / len(t_a | t_b)


# ── Union-Find ────────────────────────────────────────────────────────────────

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self.parent[ry] = rx


# ── Canonical selection ───────────────────────────────────────────────────────

def _elect_canonical(cluster_claims: list[AtomicClaim]) -> AtomicClaim:
    """
    Select the most precise claim as canonical.
    Heuristic: longer text → more specific.
    Tie-break: lower numeric ID (earlier = higher confidence from Sprint 1).
    """
    return max(cluster_claims, key=lambda c: (len(c.text), -int(c.id[1:])))


# ── Graph rewriting ───────────────────────────────────────────────────────────

def _rewrite_graph(
    dep_graph: list[DependencyEdge],
    alias_map: dict[str, str],   # alias_id → canonical_id
) -> list[DependencyEdge]:
    """
    Replace every alias ID (parent or child) with its canonical ID.
    De-duplicate resulting edges.
    """
    new_graph: list[DependencyEdge] = []
    seen: dict[str, set[str]] = {}

    for edge in dep_graph:
        parent = alias_map.get(edge.parent, edge.parent)
        children = [alias_map.get(c, c) for c in edge.children]
        # Remove self-loops and de-duplicate children
        children = list(dict.fromkeys(c for c in children if c != parent))

        if parent not in seen:
            seen[parent] = set()
        for child in children:
            seen[parent].add(child)

    for parent, children_set in seen.items():
        new_graph.append(DependencyEdge(parent=parent, children=sorted(children_set)))

    # Claims that became pure aliases (now only children, not parents) — still add as leaf
    for canonical_id in set(alias_map.values()):
        if canonical_id not in seen:
            new_graph.append(DependencyEdge(parent=canonical_id, children=[]))

    new_graph.sort(key=lambda e: int(e.parent[1:]))
    return new_graph


# ── Public API ────────────────────────────────────────────────────────────────

def run_dedup(
    claims: list[AtomicClaim],
    dep_graph: list[DependencyEdge],
) -> tuple[DedupReport, list[AtomicClaim], list[DependencyEdge]]:
    """
    Run semantic deduplication on the claim list.

    Returns:
        (DedupReport, canonical_claims_list, updated_dep_graph)
    """
    n = len(claims)
    texts = [c.text for c in claims]

    # ── 1. Compute similarity matrix ─────────────────────────────────────────
    embeddings = _get_embeddings(texts)

    sim_matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            if i == j:
                sim_matrix[i][j] = 1.0
            elif embeddings:
                s = _cosine(embeddings[i], embeddings[j])
            else:
                s = _jaccard(texts[i], texts[j])
                # Scale Jaccard to roughly match cosine range (calibration factor)
                s = min(s * 1.35, 1.0)
            sim_matrix[i][j] = sim_matrix[j][i] = s if i != j else 1.0

    # ── 2. Union-Find clustering at threshold ─────────────────────────────────
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i][j] >= DEDUP_THRESHOLD:
                log.debug(
                    "Merging %s ≈ %s (sim=%.3f)",
                    claims[i].id, claims[j].id, sim_matrix[i][j],
                )
                uf.union(i, j)

    # ── 3. Group clusters ──────────────────────────────────────────────────────
    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = uf.find(i)
        groups.setdefault(root, []).append(i)

    # ── 4. Build DedupReport ───────────────────────────────────────────────────
    clusters: list[DedupCluster] = []
    alias_map: dict[str, str] = {}
    canonical_claims: list[AtomicClaim] = []

    for root, members in groups.items():
        member_claims = [claims[i] for i in members]

        if len(member_claims) == 1:
            # No duplicate — just a singleton canonical
            canonical_claims.append(member_claims[0])
            continue

        canonical = _elect_canonical(member_claims)
        aliases   = [c for c in member_claims if c.id != canonical.id]
        canonical_claims.append(canonical)

        for alias in aliases:
            alias_map[alias.id] = canonical.id

        sims = [sim_matrix[claims.index(a)][claims.index(canonical)] for a in aliases]
        graph_updates = [f"{a.id} → {canonical.id}" for a in aliases]

        cluster = DedupCluster(
            canonical_id=canonical.id,
            canonical_text=canonical.text,
            alias_ids=[a.id for a in aliases],
            alias_texts=[a.text for a in aliases],
            similarity_scores=sims,
            graph_updates=graph_updates,
        )
        clusters.append(cluster)
        log.info(
            "Dedup cluster: CANONICAL=%s, ALIASES=%s",
            canonical.id, [a.id for a in aliases],
        )

    # Sort canonical claims by numeric ID
    canonical_claims.sort(key=lambda c: int(c.id[1:]))

    report = DedupReport(
        clusters=clusters,
        alias_map=alias_map,
        canonical_ids=[c.id for c in canonical_claims],
        total_input_claims=n,
        total_canonical_claims=len(canonical_claims),
        total_aliases_retired=len(alias_map),
    )

    # ── 5. Rewrite dependency graph ───────────────────────────────────────────
    updated_graph = _rewrite_graph(dep_graph, alias_map) if alias_map else list(dep_graph)

    return report, canonical_claims, updated_graph
