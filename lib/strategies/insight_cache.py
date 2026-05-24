"""InsightCache — signal_monitor's read-side adapter for insight_reports.

The Phase 1 direction gate (per docs/audits/2026-05-10-risk-reviewer-validation.md)
requires the live signal_monitor to know the morning insight's
`direction` for each ticker so it can suppress fires that go against
the plan. The cache shape:

  - Keyed on `ticker` (one cached InsightContext per ticker per session)
  - Refreshes on staleness (default 60s) so a mid-session insight rerun
    is picked up promptly
  - Falls back gracefully when DB is unreachable, when no insight exists
    for today, or when a query raises — gate degrades to "no-op" and
    the monitor fires as if Phase 1 wasn't deployed

The cache is intentionally small (one row per ticker) and stateless
across process restarts. All decisions are made fresh on each refresh.

Empirical baseline from the 36-day audit (5/4-5/8 SPY/IWM/QQQ
post-fix replay, n=951 directional fires): aligned-with-plan fires
win 55.7%, opposite-to-plan fires win 35.4% (-20.3pp delta). The
gate's expected impact is to filter out the loss-rich opposite
bucket.
"""
from __future__ import annotations

import logging
import time as time_module
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class InsightContext:
    """One ticker's morning insight, cached for use by the gate."""
    ticker: str
    direction: str  # 'long' / 'short' / 'flat'
    conviction: str  # 'low' / 'medium' / 'high'
    regime: str  # 'normal' / 'extended' / 'orb_only' (or future: 'gap_faded_*')
    invalidation_level: Optional[float] = None  # price level (None when prose-only)
    as_of_date: Optional[date] = None
    fetched_at: float = field(default_factory=time_module.time)

    @property
    def age_seconds(self) -> float:
        return time_module.time() - self.fetched_at


# Sentinel "no insight available" — distinct from None so callers know
# the cache has been queried (just had no row to return).
@dataclass
class NoInsight:
    """Indicates the cache has been checked but no insight exists for
    this ticker today. Distinguishes from None which means 'never queried'."""
    ticker: str
    fetched_at: float = field(default_factory=time_module.time)

    @property
    def age_seconds(self) -> float:
        return time_module.time() - self.fetched_at


class InsightCache:
    """Pull-based cache of today's insight_reports for live signal_monitor.

    Refreshes lazily: each `get(ticker)` call checks staleness and
    re-queries if older than `refresh_after_seconds`. This gives sub-60s
    latency from a fresh insight publish to the gate picking it up,
    without polling pressure on Cloud SQL between fires.

    The cache key is just `ticker` (single morning insight per ticker
    per session). Not keyed on (ticker, date) because the live monitor
    only cares about today.

    Staleness handling (per phased plan §3.6):
      - < refresh_after_seconds: serve cached value
      - >= refresh_after_seconds: re-query
      - > 12h with no row: gate disabled (caller falls back to no-gate)

    Constructor takes a `now_fn` injection so tests can drive time
    deterministically (and so replay can route to the bar's clock).
    """

    def __init__(
        self,
        refresh_after_seconds: float = 60.0,
        now_fn=None,
    ):
        self._cache: dict[str, InsightContext | NoInsight] = {}
        self._refresh_after = refresh_after_seconds
        self._now_fn = now_fn or time_module.time

    def get(self, ticker: str, fetcher) -> Optional[InsightContext]:
        """Return today's insight for the ticker, or None if not available.

        ``fetcher`` is a callable that takes (ticker) and returns either
        an InsightContext (when a row exists for today) or None. The
        cache invokes it on cold misses and on staleness expiry.

        Returns:
          - InsightContext if available
          - None if cache says "no insight today" (NoInsight sentinel)
        """
        ticker = ticker.upper()
        cached = self._cache.get(ticker)

        # Cold miss → fetch
        if cached is None:
            return self._fetch_and_cache(ticker, fetcher)

        # Staleness check — using monotonic time via now_fn
        age = self._now_fn() - cached.fetched_at
        if age >= self._refresh_after:
            return self._fetch_and_cache(ticker, fetcher)

        # Fresh enough — serve cached
        return cached if isinstance(cached, InsightContext) else None

    def _fetch_and_cache(self, ticker: str, fetcher) -> Optional[InsightContext]:
        try:
            ctx = fetcher(ticker)
        except Exception as exc:
            logger.warning(
                "InsightCache: fetcher raised for %s: %s — falling back to no-gate",
                ticker, exc,
            )
            ctx = None
        if ctx is None:
            self._cache[ticker] = NoInsight(ticker=ticker, fetched_at=self._now_fn())
            return None
        # Stamp fetched_at to enable staleness check
        ctx.fetched_at = self._now_fn()
        self._cache[ticker] = ctx
        return ctx

    def clear(self):
        """For tests + new-session boot."""
        self._cache.clear()


# ── Gate decision logic (pure, separable from the cache) ───────────


@dataclass
class GateDecision:
    """Output of the direction-gate evaluation for a fire.

    Three actions:
      - 'pass'        — fire as-is (aligned with plan, or no insight)
      - 'suppress'    — drop the fire entirely (opposing weak)
      - 'downgrade'   — fire as one tier weaker (opposing medium → weak)
      - 'tag'         — fire as-is but with directional-conflict tag
                        (opposing strong, kept because it might be the
                        actual reversal)
      - 'annotate'    — fire as-is with insight context shown (no-op
                        for low-conviction or stale insight)

    Phase 1 v1 matrix is conviction-UNAWARE per
    docs/replays/2026-05-10-corrected-baseline-v2.md §6 — the
    conviction signal is structurally pinned to 'low' until Phase 1α
    risk-reviewer fixes land. Once conviction varies meaningfully,
    Phase 1.5 reintroduces the conviction-weighted matrix per the
    original phased plan §3.3.
    """
    action: str  # 'pass' / 'suppress' / 'downgrade' / 'tag' / 'annotate'
    reason: str
    new_strength: Optional[str] = None  # set when action == 'downgrade'


def evaluate_direction_gate(
    fire_direction: str,
    fire_strength: str,
    insight: Optional[InsightContext],
    insight_invalidated: bool = False,
) -> GateDecision:
    """Pure decision function: should this fire pass, suppress, downgrade, or tag?

    Conviction-unaware v1 matrix (per audit doc §6):

      | fire vs insight | weak       | medium      | strong      |
      |-----------------|------------|-------------|-------------|
      | aligned         | pass       | pass        | pass        |
      | opposite        | SUPPRESS   | downgrade   | tag         |
      | flat-day        | annotate   | downgrade   | tag         |
      | no insight      | annotate   | annotate    | annotate    |

    Empirical justification (36-day SPY/IWM/QQQ audit):
      - aligned wins 55.7% / opposite wins 35.4% (-20.3pp delta)
      - filtering opposing weak removes ~63% of opposite-direction fires
        while keeping the 5-10% that are real reversal signals (medium+)

    Invalidation tripwire: when `insight_invalidated=True` (price has
    crossed the insight's invalidation_level), the gate stops opposing
    suppression — the morning bias is mechanically wrong, no point
    blocking fires that would oppose it. Aligned fires still pass; the
    monitor effectively reverts to no-gate behavior for the rest of
    the session (or until a fresh insight publishes via the 60s cache
    refresh).
    """
    # No insight at all → annotate-only (no suppression, no downgrade).
    # This is the "Phase 1 not yet rolled out for this ticker" path.
    if insight is None:
        return GateDecision(action='annotate', reason='no_insight_available')

    # Invalidation kill-switch — direction gate is functionally off.
    if insight_invalidated:
        return GateDecision(
            action='annotate',
            reason='thesis_invalidated_at_price_level',
        )

    # Direction match check
    fire_long = (fire_direction == 'CALL')
    plan_long = (insight.direction == 'long')
    plan_short = (insight.direction == 'short')
    plan_flat = (insight.direction == 'flat')

    # Flat-day branch: see §3.4 of phased plan. v1 just downgrades momentum
    # fires; structural-level proximity check is deferred to Phase 1.5.
    if plan_flat:
        if fire_strength == 'weak':
            return GateDecision(action='annotate',
                                reason='flat_day_weak_momentum_passthrough')
        elif fire_strength == 'medium':
            return GateDecision(action='downgrade',
                                reason='flat_day_medium_downgraded',
                                new_strength='weak')
        else:  # strong
            return GateDecision(action='tag',
                                reason='flat_day_strong_kept_with_tag')

    # Directional plan
    aligned = (fire_long and plan_long) or ((not fire_long) and plan_short)
    if aligned:
        return GateDecision(action='pass',
                            reason=f'aligned_with_plan_{insight.direction}')

    # Opposite direction
    if fire_strength == 'weak':
        return GateDecision(action='suppress',
                            reason=f'opposing_weak_vs_plan_{insight.direction}')
    elif fire_strength == 'medium':
        return GateDecision(action='downgrade',
                            reason=f'opposing_medium_vs_plan_{insight.direction}',
                            new_strength='weak')
    else:  # strong
        return GateDecision(action='tag',
                            reason=f'opposing_strong_vs_plan_{insight.direction}_kept')


# ── DB fetcher implementation (reusable + mockable) ───────────────


def fetch_insight_for_ticker(
    ticker: str,
    target_date: date,
    engine,
) -> Optional[InsightContext]:
    """Pull today's insight_reports row for the ticker. Returns None
    when no row exists or query fails.

    Caller (the InsightCache) wraps invocations in try/except so this
    function can raise on genuine DB errors and still degrade safely.
    """
    from sqlalchemy import text
    sql = text("""
        SELECT
            report->>'direction'      AS direction,
            report->>'conviction'     AS conviction,
            report->>'regime'         AS regime,
            (report->>'invalidation_level')::numeric AS invalidation_level
        FROM insight_reports
        WHERE ticker = :t AND as_of::date = :d
        ORDER BY created_at DESC
        LIMIT 1
    """)
    import pandas as pd
    df = pd.read_sql(sql, engine,
                     params={"t": ticker.upper(), "d": str(target_date)})
    if df.empty:
        return None
    row = df.iloc[0]
    return InsightContext(
        ticker=ticker.upper(),
        direction=str(row['direction']) if row['direction'] else 'flat',
        conviction=str(row['conviction']) if row['conviction'] else 'low',
        regime=str(row['regime']) if row['regime'] else 'normal',
        invalidation_level=(
            float(row['invalidation_level'])
            if row['invalidation_level'] is not None and pd.notna(row['invalidation_level'])
            else None
        ),
        as_of_date=target_date,
    )
