"""Pin chunksize-by-column-count math against pg8000's 65535 bind-param limit.

Motivated by the 2026-05-04 `compute-earnings-reactions` failure
(`struct.error: 'H' format requires 0 <= number <= 65535`). The
`earnings_reactions` table grew to 35+ columns via PR #239 (ATR cols)
and pending PR #240 (swing-window hi/lo); at the existing
`chunksize=2000` default each batch packed 35 × 2000 = 70 000 params
into a single `pg_insert(...).values(batch)` call, blowing past
pg8000's 16-bit packed param-count.

The fix in `gcp/database.py:_max_safe_chunksize` shrinks chunksize so
`n_cols × chunksize + safety_margin ≤ PG_PARAM_LIMIT`. These tests
pin the math without touching Cloud SQL.
"""
from __future__ import annotations

from gcp.database import (
    PG_PARAM_LIMIT,
    _max_safe_chunksize,
)


# ── core math ─────────────────────────────────────────────────────────


def test_narrow_table_keeps_requested_chunksize():
    # 5-col table at chunksize=2000 → only 10 000 params, way under the
    # limit. Should not be capped.
    assert _max_safe_chunksize(n_cols=5, requested_chunksize=2000) == 2000


def test_wide_table_caps_chunksize():
    # 50-col table at chunksize=2000 → 100 000 params, over the limit.
    # Must shrink. Floor of (65535 - 5000) / 50 = 1210.
    chunk = _max_safe_chunksize(n_cols=50, requested_chunksize=2000)
    assert chunk < 2000
    assert chunk * 50 + 5000 <= PG_PARAM_LIMIT


def test_earnings_reactions_size_does_not_overflow():
    """The actual production failure case: 35 cols × 2000 rows = 70000."""
    chunk = _max_safe_chunksize(n_cols=35, requested_chunksize=2000)
    # Effective batch must not exceed the unsigned-short cap when
    # combined with the ON CONFLICT clause overhead.
    assert chunk * 35 + 5000 <= PG_PARAM_LIMIT


def test_post_pr240_size_does_not_overflow():
    """PR #240 lands 6 more max_high/min_low cols → 41-col table."""
    chunk = _max_safe_chunksize(n_cols=41, requested_chunksize=2000)
    assert chunk * 41 + 5000 <= PG_PARAM_LIMIT


def test_extreme_width_still_satisfies_safety_invariant():
    """A pathological 1000-col table must NOT overflow.

    Earlier draft used a `max(100, ...)` floor which Codex flagged on PR
    #256: 100 × 1000 + 5000 = 105 000 > 65 535, reproducing the exact
    failure the helper is meant to prevent. The floor is now max(1, ...)
    so the safety invariant always holds.
    """
    chunk = _max_safe_chunksize(n_cols=1000, requested_chunksize=2000)
    # The only invariant that matters: we never blow past pg8000's cap.
    assert chunk * 1000 + 5000 <= PG_PARAM_LIMIT
    # And we still produce a usable batch size (not 0).
    assert chunk >= 1


def test_max_legal_postgres_table_width_satisfies_invariant():
    """PostgreSQL caps tables at 1600 columns (`MaxHeapAttributeNumber`).
    Any legal table must produce a working chunksize >= 1 that doesn't
    overflow the bind-param cap.
    """
    chunk = _max_safe_chunksize(n_cols=1600, requested_chunksize=2000)
    assert chunk * 1600 + 5000 <= PG_PARAM_LIMIT
    assert chunk >= 1


def test_zero_or_negative_n_cols_returns_requested():
    """Edge case: empty DataFrame. Don't crash, just pass through."""
    assert _max_safe_chunksize(n_cols=0, requested_chunksize=2000) == 2000
    assert _max_safe_chunksize(n_cols=-1, requested_chunksize=500) == 500


def test_smaller_requested_is_never_grown():
    """If caller asks for chunksize=100, we never bump it up even if the
    table is narrow enough to support more.
    """
    assert _max_safe_chunksize(n_cols=5, requested_chunksize=100) == 100


def test_threshold_is_below_pg_param_limit_not_at_it():
    """Safety margin guarantees we don't write right up to 65535
    (the ON CONFLICT clause adds N extra params per row).
    """
    # At the boundary: 65 cols × 1000 rows = 65 000. Cap should drop us.
    chunk = _max_safe_chunksize(n_cols=65, requested_chunksize=1000)
    assert chunk * 65 + 5000 <= PG_PARAM_LIMIT
    assert chunk * 65 < PG_PARAM_LIMIT - 1000  # comfortable margin
