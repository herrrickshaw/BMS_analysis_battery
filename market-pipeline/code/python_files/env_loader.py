# env_loader.py
# =============
# One place to resolve a secret, so credentials live in ONE gitignored file
# instead of being copied into every launchd plist.
#
# WHY THIS EXISTS
# ───────────────
# GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO were stored inline in three separate
# launchd plists. That is bad in three specific ways, not just aesthetically:
#
#   1. Rotating the app password meant editing three files, and missing one gave
#      a job that fails only at send time — hours after the run started.
#   2. Plists are plain XML that any process can read, and they get copied around
#      (this session transplanted them between plists twice).
#   3. Anything that echoes a plist — a debug dump, a `launchctl print`, an agent
#      transcript — leaks the live password in cleartext.
#
# The .env file is mode-600 and gitignored, so it is the right home. This module
# is the reader. It follows the idiom liquidity._fred_key() already used, just
# generalised and cached.
#
# PRECEDENCE (first hit wins):
#   1. os.environ                          — explicit override; CI / one-off runs
#   2. ~/.config/market-secrets/credentials.env  — the CANONICAL consolidated store
#   3. <this dir>/.env                     — legacy, kept as fallback during migration
#   4. ~/.env.local                        — legacy machine-wide fallback
#
# The canonical store (2026-07-23) collapses five scattered credential files
# (this .env, ~/.env.local, ~/.jquants.env, global-stock-screener/.env,
# ~/.aws/credentials) into ONE gitignored, mode-600 file so every data fetch
# resolves keys from a single place and rotation touches one file. The legacy
# files are still read AFTER it, so a key not yet migrated still resolves and
# nothing breaks; once verified they can be emptied. See market-secrets/README.
#
# stdlib only, and no dependency on python-dotenv: this is imported by
# send_alert.py, which must work even when the environment is broken enough that
# the alert is the only thing still running.

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

_HERE = Path(__file__).resolve().parent
_CANONICAL = Path.home() / ".config" / "market-secrets" / "credentials.env"
_FILES = (_CANONICAL, _HERE / ".env", Path.home() / ".env.local")

_cache: Optional[Dict[str, str]] = None


def _parse(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            # Strip one layer of matching quotes; an app password contains
            # spaces, so quoting it in .env is normal and must round-trip.
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[k.strip()] = v
    except OSError:
        pass
    return out


def _files() -> Dict[str, str]:
    global _cache
    if _cache is None:
        merged: Dict[str, str] = {}
        for p in reversed(_FILES):     # earlier file wins → apply in reverse
            merged.update(_parse(p))
        _cache = merged
    return _cache


def get(key: str, default: str = "") -> str:
    """Resolve one secret. os.environ wins, then .env, then ~/.env.local."""
    v = os.environ.get(key)
    if v:
        return v
    return _files().get(key, default)


def require(*keys: str) -> Dict[str, str]:
    """Resolve several, reporting which are MISSING by name.

    Names only — never values. A missing-credential message that echoes the
    other credentials is how secrets end up in logs and transcripts.
    """
    got = {k: get(k) for k in keys}
    missing = [k for k, v in got.items() if not v]
    if missing:
        raise KeyError("missing credential(s): " + ", ".join(missing)
                       + f" — set them in {_HERE / '.env'} or the environment")
    return got


def present(*keys: str) -> bool:
    return all(get(k) for k in keys)
