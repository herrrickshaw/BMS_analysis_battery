#!/usr/bin/env python3
"""
canonicalize.py
----------------
Phase 2 of the repo-consolidation-assistant: takes the lineage clusters found
by inventory.py (repo-inventory/inventory.duckdb) and asks an LLM to judge,
per cluster, which repo is canonical and what to do with the rest.

This is deliberately the ONLY phase that calls an LLM. Clustering, file-set
diffing, and Jaccard math are all plain deterministic SQL/Python (inventory.py)
-- the LLM's job is judgment (recency + completeness + which sibling looks
like the "real" one), not computation.

Usage:
  python canonicalize.py [--min-overlap 0.3] [--out CANONICAL_REPORT.md]
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "inventory.duckdb")


def _load_env():
    env_path = os.path.expanduser("~/.env.local")
    if not os.path.exists(env_path):
        return
    for line in open(env_path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def cluster_repos(con, min_overlap: float) -> list[list[str]]:
    """Union-find over lineage pairs >= min_overlap. Returns list of repo-name clusters (size >= 2)."""
    pairs = con.execute("""
        WITH distinct_files AS (SELECT DISTINCT repo, sha FROM files),
        pair_shared AS (
            SELECT a.repo AS repo_a, b.repo AS repo_b, COUNT(*) AS shared
            FROM distinct_files a JOIN distinct_files b
              ON a.sha = b.sha AND a.repo < b.repo
            GROUP BY 1, 2
        ),
        sizes AS (SELECT repo, COUNT(*) AS n FROM distinct_files GROUP BY 1)
        SELECT ps.repo_a, ps.repo_b
        FROM pair_shared ps
        JOIN sizes sa ON sa.repo = ps.repo_a
        JOIN sizes sb ON sb.repo = ps.repo_b
        WHERE ps.shared * 1.0 / (sa.n + sb.n - ps.shared) >= ?
    """, [min_overlap]).fetchall()

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in pairs:
        union(a, b)

    groups: dict[str, list[str]] = {}
    for name in parent:
        groups.setdefault(find(name), []).append(name)

    return [sorted(g) for g in groups.values() if len(g) >= 2]


def cluster_evidence(con, cluster: list[str]) -> str:
    """Deterministic per-repo metadata + unique-file samples for one cluster. No LLM here."""
    lines = []
    meta = con.execute(
        f"SELECT name, description, language, size_kb, updated_at, pushed_at, fork "
        f"FROM repos WHERE name IN ({','.join('?' * len(cluster))})", cluster
    ).fetchall()
    meta_by_name = {m[0]: m for m in meta}

    for repo in cluster:
        m = meta_by_name.get(repo)
        total_files = con.execute("SELECT COUNT(*) FROM files WHERE repo = ?", [repo]).fetchone()[0]
        lines.append(f"\n### {repo}")
        if m:
            _, desc, lang, size_kb, updated_at, pushed_at, fork = m
            lines.append(f"- description: {desc or '(none)'}")
            lines.append(f"- language: {lang}, size: {size_kb}KB, fork: {fork}")
            lines.append(f"- updated_at: {updated_at}, pushed_at: {pushed_at}")
        lines.append(f"- total files: {total_files}")

        others = [r for r in cluster if r != repo]
        if others:
            placeholders = ",".join("?" * len(others))
            unique = con.execute(f"""
                SELECT path FROM files
                WHERE repo = ? AND sha NOT IN (
                    SELECT sha FROM files WHERE repo IN ({placeholders})
                )
                ORDER BY path LIMIT 20
            """, [repo] + others).fetchall()
            n_unique = con.execute(f"""
                SELECT COUNT(*) FROM files
                WHERE repo = ? AND sha NOT IN (
                    SELECT sha FROM files WHERE repo IN ({placeholders})
                )
            """, [repo] + others).fetchone()[0]
            lines.append(f"- files unique to this repo (not byte-identical to any sibling): {n_unique}")
            if unique:
                lines.append("  sample: " + ", ".join(u[0] for u in unique))
    return "\n".join(lines)


PROMPT_TMPL = """You are helping consolidate a solo developer's sprawling personal GitHub account.
These {n} repos share a large fraction of byte-identical files (confirmed via git blob SHA, not
guessed) -- they are almost certainly forks, copies, or divergent snapshots of the same underlying
codebase, built across many separate AI-assisted coding sessions.

Evidence (deterministic, computed from GitHub's git tree API -- not your job to re-derive):
{evidence}

Your job (judgment only, don't recompute the file diffs):
1. Which ONE repo is the canonical/most-current version? Base this on recency (updated_at/pushed_at),
   completeness (total files, unique-file count suggesting active development), and whether the
   description matches the actual file content.
2. For each non-canonical repo, one line: what it actually seems to be (e.g. "earlier snapshot",
   "mislabeled dumping ground", "genuinely unrelated content despite shared files") and a recommended
   action: keep-separate / archive / merge-into-canonical / delete-candidate.
3. Flag anything surprising (e.g. a repo's description doesn't match its content).

Be concise -- under 200 words. Output plain text, no markdown headers.
"""


def call_llm(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1")
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-overlap", type=float, default=0.3)
    ap.add_argument("--out", default=os.path.join(HERE, "CANONICAL_REPORT.md"))
    args = ap.parse_args()

    if not os.path.exists(DB):
        print(f"{DB} not found -- run inventory.py --build first", file=sys.stderr)
        sys.exit(1)

    _load_env()
    if "GROQ_API_KEY" not in os.environ:
        print("GROQ_API_KEY not found in ~/.env.local", file=sys.stderr)
        sys.exit(1)

    import duckdb
    con = duckdb.connect(DB, read_only=True)

    clusters = cluster_repos(con, args.min_overlap)
    print(f"found {len(clusters)} clusters at jaccard >= {args.min_overlap}")

    report = ["# Repo Consolidation Report",
              f"\nGenerated from `inventory.duckdb` ({len(clusters)} lineage clusters, "
              f"min-overlap={args.min_overlap}). File-level evidence (blob-sha matches, unique-file "
              f"counts) is deterministic; canonical-repo judgment below is LLM-assisted "
              f"(llama-3.3-70b-versatile) and should be spot-checked before archiving anything.\n"]

    for i, cluster in enumerate(clusters, 1):
        print(f"\n[{i}/{len(clusters)}] cluster: {', '.join(cluster)}")
        evidence = cluster_evidence(con, cluster)
        prompt = PROMPT_TMPL.format(n=len(cluster), evidence=evidence)
        try:
            verdict = call_llm(prompt)
        except Exception as e:
            verdict = f"(LLM call failed: {e})"
        print(verdict)
        report.append(f"\n## Cluster {i}: {', '.join(cluster)}\n")
        report.append(evidence)
        report.append(f"\n**Verdict:**\n\n{verdict}\n")

    con.close()

    with open(args.out, "w") as f:
        f.write("\n".join(report))
    print(f"\n\nwrote {args.out}")


if __name__ == "__main__":
    main()
