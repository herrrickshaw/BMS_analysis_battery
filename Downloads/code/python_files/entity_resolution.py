#!/usr/bin/env python3
"""
Shared entity resolution: consolidate duplicate records that refer to the same
real-world entity but surface under different keys (e.g. the same company
cross-listed on NSE and BSE, or the same instrument reported by two data
sources with slightly different metadata).

Derived from patent MY269113 "System and method for generating consolidated
virtual profiles of individuals with identical attributes" (IIIT-Hyderabad,
DSAC) -- generalizes the ad hoc per-caller dedup logic that used to live
inline in news_picks.py's NSE/BSE preference block, so other callers with the
same "many rows, one real entity" problem don't have to reinvent it.

Usage:
    from entity_resolution import consolidate, preferred_exchange_rank

    winners = consolidate(
        candidates,
        key_fn=lambda c: c["phrase"],
        rank_fn=lambda c: preferred_exchange_rank(c["exchange"], "NSE", c["mentions"]),
    )
"""
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def consolidate(
    candidates: list[T],
    key_fn: Callable[[T], str],
    rank_fn: Callable[[T], tuple],
) -> list[T]:
    """
    Collapse *candidates* referring to the same entity (same key_fn(c)) down to
    one "virtual profile" per key -- the highest-ranked one by rank_fn(c).

    rank_fn returns a tuple compared with normal tuple ordering (higher wins),
    e.g. (is_primary_exchange, mention_count) picks the primary-exchange
    listing first, then the one with more mentions as a tie-breaker.

    Preserves the first-seen order of each key's winning record.
    """
    best: dict[str, T] = {}
    best_rank: dict[str, tuple] = {}
    order: list[str] = []
    for c in candidates:
        key = key_fn(c)
        rank = rank_fn(c)
        if key not in best:
            order.append(key)
        if key not in best or rank > best_rank[key]:
            best[key] = c
            best_rank[key] = rank
    return [best[k] for k in order]


def preferred_exchange_rank(exchange: str, primary: str, secondary_metric: float = 0.0) -> tuple:
    """
    Convenience rank_fn helper for the common "prefer one exchange, then break
    ties by some metric" case (e.g. prefer NSE over BSE, then more mentions).
    """
    return (exchange == primary, secondary_metric)
