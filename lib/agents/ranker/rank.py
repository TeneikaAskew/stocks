"""Public entry point: rank a candidate set, persist an audit row.

This is what the API endpoint and the auto-refresh cron call. It:

  1. Calls `candidates.gather_candidates(...)` to build the universe.
  2. For each candidate, runs every signal in `signals.ALL_SIGNALS`.
  3. Aggregates via `scoring.weighted_score(...)` with config-driven weights.
  4. Drops gate-failed (illiquid) candidates.
  5. Sorts by total score descending, applies `limit`.
  6. Optionally persists a row to `ranker_runs` for audit.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from .candidates import CandidateTicker, gather_candidates
from .scoring import DEFAULT_WEIGHTS, ScoreResult, weighted_score
from .signals import ALL_SIGNALS

logger = logging.getLogger(__name__)


@dataclass
class RankedTicker:
    ticker: str
    score: float                    # ScoreResult.total
    pct_of_max: float               # ScoreResult.pct_of_max
    catalyst_types: list[str]       # from CandidateTicker
    catalyst_metadata: dict         # from CandidateTicker
    score_breakdown: list[dict]     # ScoreResult.breakdown serialized

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "score": round(self.score, 3),
            "pct_of_max": round(self.pct_of_max, 3),
            "catalyst_types": self.catalyst_types,
            "catalyst_metadata": self.catalyst_metadata,
            "score_breakdown": self.score_breakdown,
        }


def _run_signals_for(ticker: str) -> dict[str, dict]:
    """Run every signal sequentially. Each is a small SQL query so a
    handful of them per ticker is cheap (~10-50 ms total)."""
    out: dict[str, dict] = {}
    for name, fn in ALL_SIGNALS.items():
        try:
            out[name] = fn(ticker)
        except Exception as exc:
            logger.warning("signal %s failed for %s: %s", name, ticker, exc)
            out[name] = {
                "available": False, "score_0_to_1": 0.0,
                "reason": f"error: {exc}", "raw": {},
            }
    return out


def rank_tickers(
    *,
    weights: Optional[dict[str, float]] = None,
    catalyst_filter: Optional[set[str]] = None,
    limit: int = 10,
    manual_tickers: Optional[list[str]] = None,
    persist_audit: bool = True,
) -> dict:
    """Rank candidates. Returns a dict with the ranked list and metadata.

    Returned shape:
        {
            "run_id": str (uuid),
            "as_of": ISO timestamp,
            "candidate_count": int,
            "excluded_count": int,
            "ranked": list[dict],     # at most `limit` entries, sorted desc
            "weights_used": dict,
            "duration_ms": int,
        }
    """
    start = time.monotonic()
    run_id = str(uuid4())
    weights = weights or DEFAULT_WEIGHTS

    candidates = gather_candidates(
        catalyst_filter=catalyst_filter,
        manual_tickers=manual_tickers,
    )
    logger.info("rank_tickers: %d candidates from gather", len(candidates))

    scored: list[tuple[CandidateTicker, ScoreResult]] = []
    excluded = 0
    for cand in candidates:
        signal_results = _run_signals_for(cand.ticker)
        score = weighted_score(signal_results, weights)
        if score.excluded_reason:
            excluded += 1
            logger.debug("ranker excluded %s: %s",
                         cand.ticker, score.excluded_reason)
            continue
        scored.append((cand, score))

    scored.sort(key=lambda pair: pair[1].total, reverse=True)
    top = scored[:limit]

    ranked = [
        RankedTicker(
            ticker=cand.ticker,
            score=score.total,
            pct_of_max=score.pct_of_max,
            catalyst_types=cand.catalyst_types,
            catalyst_metadata=cand.metadata,
            score_breakdown=[c.__dict__ for c in score.breakdown],
        ).to_dict()
        for cand, score in top
    ]

    duration_ms = int((time.monotonic() - start) * 1000)
    result = {
        "run_id": run_id,
        "as_of": datetime.now(tz=timezone.utc).isoformat(),
        "candidate_count": len(candidates),
        "excluded_count": excluded,
        "ranked": ranked,
        "weights_used": weights,
        "duration_ms": duration_ms,
    }

    if persist_audit:
        _persist_audit(run_id, result)

    return result


def _persist_audit(run_id: str, result: dict) -> None:
    """Write one row per ranker run for later reproducibility."""
    try:
        from gcp.database import connect

        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO ranker_runs
                    (id, run_at, candidate_count, excluded_count,
                     weights_used, results, duration_ms)
                VALUES (%s, NOW(), %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    run_id,
                    result["candidate_count"],
                    result["excluded_count"],
                    json.dumps(result["weights_used"]),
                    json.dumps(result["ranked"]),
                    result["duration_ms"],
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("ranker_runs audit write failed: %s", exc)
