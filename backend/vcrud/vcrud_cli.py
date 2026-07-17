#!/usr/bin/env python3
"""
VCRUD CLI — manage Kaggle dataset file tracking.

Usage:
  python -m vcrud.vcrud_cli index-all   --db postgresql://... --repo /path/to/repo
  python -m vcrud.vcrud_cli status      --db postgresql://... --repo /path/to/repo
  python -m vcrud.vcrud_cli export      --db postgresql://...
  python -m vcrud.vcrud_cli duplicates  --db postgresql://...
  python -m vcrud.vcrud_cli hints       --db postgresql://...
  python -m vcrud.vcrud_cli optimize    --db postgresql://...  [--ratio 0.85]

Set DATABASE_URL instead of --db to avoid repeating it.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
log = logging.getLogger(__name__)

# Resolve repo root (two levels up from this file: backend/vcrud/vcrud_cli.py → repo root)
_DEFAULT_REPO = str(Path(__file__).parent.parent.parent)


def _make_tracker(args):
    from vcrud.kaggle_tracker import KaggleDatasetTracker
    db_url = getattr(args, 'db', None) or os.environ.get('DATABASE_URL', '')
    repo = getattr(args, 'repo', _DEFAULT_REPO) or _DEFAULT_REPO
    return KaggleDatasetTracker(db_url=db_url, repo_root=repo)


def cmd_index_all(args):
    t = _make_tracker(args)
    print(json.dumps(t.index_all(), indent=2, default=str))
    t.close()


def cmd_status(args):
    t = _make_tracker(args)
    print(json.dumps(t.status(), indent=2, default=str))
    t.close()


def cmd_export(args):
    t = _make_tracker(args)
    print(json.dumps(t.export(), indent=2, default=str))
    t.close()


def cmd_duplicates(args):
    t = _make_tracker(args)
    dups = t.duplicates()
    print(json.dumps({'count': len(dups), 'duplicates': dups}, indent=2, default=str))
    t.close()


def cmd_hints(args):
    t = _make_tracker(args)
    print(json.dumps(t.hints(), indent=2, default=str))
    t.close()


def cmd_optimize(args):
    t = _make_tracker(args)
    print(json.dumps(t.optimize(min_ratio=args.ratio), indent=2, default=str))
    t.close()


def main():
    parser = argparse.ArgumentParser(
        description='VCRUD CLI — Kaggle dataset file tracking',
    )
    parser.add_argument('--db',   help='PostgreSQL URL (overrides DATABASE_URL)')
    parser.add_argument('--repo', default=_DEFAULT_REPO, help='Path to repo root')

    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('index-all',  help='Walk data/kaggle/ and index all files')
    sub.add_parser('status',     help='Show indexing stats per category')
    sub.add_parser('export',     help='Full metadata export of all tracked files')
    sub.add_parser('duplicates', help='Detect duplicate files by checksum')
    sub.add_parser('hints',      help='Top-retrieval files to cache locally')

    p_opt = sub.add_parser('optimize', help='Report poorly-compressible files')
    p_opt.add_argument('--ratio', type=float, default=0.85,
                       help='Min compression ratio to flag (default 0.85)')

    args = parser.parse_args()
    dispatch = {
        'index-all':  cmd_index_all,
        'status':     cmd_status,
        'export':     cmd_export,
        'duplicates': cmd_duplicates,
        'hints':      cmd_hints,
        'optimize':   cmd_optimize,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
