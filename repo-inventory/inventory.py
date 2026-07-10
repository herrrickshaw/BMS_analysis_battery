#!/usr/bin/env python3
"""
inventory.py
------------
Repo-inventory pass (phase 1 of the repo-consolidation-assistant plan): sweeps
every repo under a GitHub account via `gh api`, stores file trees + metadata in
DuckDB, and answers the two "pure script, no LLM needed" questions:

  1. Exact duplicates — GitHub's git tree API returns each file's blob SHA,
     which IS a content hash (git blob SHA-1 = hash of "blob {size}\0{content}").
     Two files with the same blob SHA in different repos are byte-identical —
     no need to download file contents to detect this.
  2. Lineage clusters — repos that share a large fraction of their (path, sha)
     pairs are very likely forks/snapshots of the same underlying codebase,
     even with no explicit fork relationship on GitHub.

This script only gathers and structures evidence. Deciding "which repo in a
cluster is canonical and why" is the next phase's job, and that one genuinely
benefits from an LLM (recency + completeness + judgment, not just set overlap).

Usage:
  python inventory.py --build [--owner herrrickshaw]   # fetch everything fresh
  python inventory.py --show repos
  python inventory.py --show duplicates [--min-repos 2]
  python inventory.py --show lineage [--min-overlap 0.3]
  python inventory.py --show files --repo BazaarTalks
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "inventory.duckdb")


def _gh_json(args: list[str]):
    """Run a gh CLI command and parse its JSON output. Raises on failure."""
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def fetch_repos(owner: str) -> list[dict]:
    # --jq with --paginate concatenates one JSON object per line, not a single array —
    # read raw and parse line-by-line instead of via _gh_json's single json.loads.
    r = subprocess.run(
        ["gh", "api", f"users/{owner}/repos", "--paginate",
         "--jq", ".[] | {name, description, language, size, updated_at, pushed_at, default_branch, fork}"],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"fetch_repos failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def fetch_tree(owner: str, repo: str, branch: str) -> list[dict]:
    """Full recursive file tree for one repo: [{path, sha, size, type}]."""
    try:
        data = _gh_json(["api", f"repos/{owner}/{repo}/git/trees/{branch}?recursive=1"])
    except RuntimeError as e:
        print(f"  [skip] {repo}: {e}", file=sys.stderr)
        return []
    return [
        {"path": e["path"], "sha": e["sha"], "size": e.get("size", 0), "type": e["type"]}
        for e in data.get("tree", [])
        if e["type"] == "blob"
    ]


def build(owner: str) -> None:
    import duckdb

    print(f"fetching repo list for {owner}...")
    repos = fetch_repos(owner)
    print(f"  {len(repos)} repos")

    all_files = []
    for r in repos:
        name = r["name"]
        branch = r.get("default_branch") or "main"
        print(f"  fetching tree: {name} ({branch})...")
        files = fetch_tree(owner, name, branch)
        for f in files:
            f["repo"] = name
        all_files.extend(files)
        print(f"    {len(files)} files")

    con = duckdb.connect(DB)
    con.execute("""CREATE OR REPLACE TABLE repos(
        name VARCHAR, description VARCHAR, language VARCHAR, size_kb INTEGER,
        updated_at VARCHAR, pushed_at VARCHAR, default_branch VARCHAR, fork BOOLEAN)""")
    if repos:
        con.executemany(
            "INSERT INTO repos VALUES (?,?,?,?,?,?,?,?)",
            [(r["name"], r.get("description"), r.get("language"), r.get("size"),
              r.get("updated_at"), r.get("pushed_at"), r.get("default_branch"), r.get("fork", False))
             for r in repos],
        )
    con.execute("""CREATE OR REPLACE TABLE files(
        repo VARCHAR, path VARCHAR, sha VARCHAR, size BIGINT)""")
    if all_files:
        con.executemany(
            "INSERT INTO files VALUES (?,?,?,?)",
            [(f["repo"], f["path"], f["sha"], f["size"]) for f in all_files],
        )
    con.close()
    print(f"\nbuilt {DB}: {len(repos)} repos, {len(all_files)} files")


SHOWS = {
    "repos": "SELECT name, language, size_kb, updated_at, fork FROM repos ORDER BY updated_at DESC",
    "duplicates": """
        SELECT sha, COUNT(DISTINCT repo) AS n_repos, COUNT(*) AS n_files,
               STRING_AGG(DISTINCT repo, ', ') AS repos, ANY_VALUE(path) AS sample_path,
               ANY_VALUE(size) AS size_bytes
        FROM files
        GROUP BY sha
        HAVING COUNT(DISTINCT repo) >= {min_repos}
        ORDER BY n_repos DESC, size_bytes DESC
        LIMIT 100
    """,
}


def show_lineage(min_overlap: float) -> None:
    """Repo-pair Jaccard similarity over (path, sha) sets — high overlap = same lineage."""
    import duckdb
    con = duckdb.connect(DB, read_only=True)
    pairs = con.execute("""
        WITH distinct_files AS (
            SELECT DISTINCT repo, sha FROM files
        ),
        pair_shared AS (
            SELECT a.repo AS repo_a, b.repo AS repo_b, COUNT(*) AS shared
            FROM distinct_files a JOIN distinct_files b
              ON a.sha = b.sha AND a.repo < b.repo
            GROUP BY 1, 2
        ),
        sizes AS (SELECT repo, COUNT(*) AS n FROM distinct_files GROUP BY 1)
        SELECT ps.repo_a, ps.repo_b, ps.shared, sa.n AS n_a, sb.n AS n_b,
               ROUND(ps.shared * 1.0 / (sa.n + sb.n - ps.shared), 3) AS jaccard
        FROM pair_shared ps
        JOIN sizes sa ON sa.repo = ps.repo_a
        JOIN sizes sb ON sb.repo = ps.repo_b
        WHERE ps.shared * 1.0 / (sa.n + sb.n - ps.shared) >= ?
        ORDER BY jaccard DESC
    """, [min_overlap]).df()
    con.close()
    print(pairs.to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--owner", default="herrrickshaw")
    ap.add_argument("--show", choices=["repos", "duplicates", "lineage", "files"])
    ap.add_argument("--min-repos", type=int, default=2)
    ap.add_argument("--min-overlap", type=float, default=0.3)
    ap.add_argument("--repo", help="for --show files")
    args = ap.parse_args()

    if args.build:
        build(args.owner)
        return

    if not args.show:
        ap.print_help()
        return

    if not os.path.exists(DB):
        print(f"{DB} not found — run --build first", file=sys.stderr)
        sys.exit(1)

    import duckdb
    con = duckdb.connect(DB, read_only=True)

    if args.show == "lineage":
        con.close()
        show_lineage(args.min_overlap)
    elif args.show == "files":
        if not args.repo:
            print("--show files requires --repo NAME", file=sys.stderr)
            sys.exit(1)
        df = con.execute("SELECT path, size FROM files WHERE repo = ? ORDER BY path", [args.repo]).df()
        con.close()
        print(df.to_string(index=False))
    else:
        sql = SHOWS[args.show].format(min_repos=args.min_repos)
        df = con.execute(sql).df()
        con.close()
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
