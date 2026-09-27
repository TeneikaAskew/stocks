"""Leak-safe, event-driven evaluation of out-of-fold trading decisions.

This module is intentionally separate from the research backtests.  It consumes
*already generated* predictions and executable option quotes; it never fits a
model or manufactures an option price from an underlying close.  Missing quote
data therefore changes the evidence classification rather than silently falling
back to an underlying return.

The public entry point is :func:`evaluate_oof_events`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EvaluationConfig:
    """Execution and production-gate assumptions.

    Monetary values are dollars.  Quote prices are per share and ``multiplier``
    converts them to contract dollars.
    """

    latency_ms: int = 500
    holding_minutes: int = 30
    contracts_per_trade: int = 1
    max_open_positions: int = 1
    max_contracts: int = 1
    fee_per_contract_side: float = 0.65
    slippage_per_contract_side: float = 0.01
    fill_probability: float = 1.0
    multiplier: int = 100
    bootstrap_samples: int = 2_000
    confidence: float = 0.95
    max_acceptable_drawdown: float = 500.0
    annual_sessions: int = 252
    random_seed: int = 7

    def __post_init__(self) -> None:
        if not 0 <= self.fill_probability <= 1:
            raise ValueError("fill_probability must be in [0, 1]")
        if self.contracts_per_trade < 1 or self.max_contracts < 1:
            raise ValueError("contract limits must be positive")
        if self.max_open_positions < 1 or self.holding_minutes <= 0:
            raise ValueError("position/time limits must be positive")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be nonnegative")
        if self.bootstrap_samples < 1 or not 0 < self.confidence < 1:
            raise ValueError("bootstrap settings must be positive and confidence in (0, 1)")


@dataclass(frozen=True)
class EvaluationReport:
    evidence_classification: str
    production_eligible: bool
    eligibility_reasons: tuple[str, ...]
    metrics: Mapping[str, Mapping[str, float]]
    baselines: Mapping[str, Mapping[str, float]]
    events: pd.DataFrame
    assumptions: Mapping[str, object]

    def to_dict(self) -> dict:
        out = asdict(self)
        out["events"] = self.events.to_dict(orient="records")
        return out


_CANDIDATE_REQUIRED = {
    "alert_id", "timestamp", "session", "instrument", "prediction",
    "prediction_fold", "trained_through", "spot",
}
_QUOTE_REQUIRED = {
    "timestamp", "instrument", "contract", "expiration", "strike",
    "option_type", "bid", "ask",
}


def _normalise(candidates: pd.DataFrame, quotes: Optional[pd.DataFrame]) -> tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    missing = _CANDIDATE_REQUIRED - set(candidates.columns)
    if missing:
        raise ValueError(f"candidates missing required columns: {sorted(missing)}")
    c = candidates.copy()
    c["timestamp"] = pd.to_datetime(c["timestamp"], utc=True)  # tz-ok: evaluator input timestamps are UTC by contract
    c["session"] = pd.to_datetime(c["session"]).dt.date
    c["trained_through"] = pd.to_datetime(c["trained_through"], utc=True)  # tz-ok: model training boundaries are UTC by contract
    if c["alert_id"].duplicated().any():
        raise ValueError("alert_id must be unique")
    # A prediction is OOF only when its training information set ends before
    # the event.  A non-empty fold id is also required for auditability.
    bad = (c["timestamp"].isna() | c["trained_through"].isna() |
           c["session"].isna() | c["prediction_fold"].isna() |
           c["prediction_fold"].astype(str).str.strip().eq("") |
           (c["trained_through"] >= c["timestamp"]))
    if bad.any():
        ids = c.loc[bad, "alert_id"].astype(str).tolist()
        raise ValueError(f"non-OOF predictions rejected: {ids}")
    c = c.sort_values(["timestamp", "alert_id"], kind="stable").reset_index(drop=True)
    if quotes is None or quotes.empty:
        return c, None
    qmissing = _QUOTE_REQUIRED - set(quotes.columns)
    if qmissing:
        raise ValueError(f"quotes missing required columns: {sorted(qmissing)}")
    q = quotes.copy()
    q["timestamp"] = pd.to_datetime(q["timestamp"], utc=True)  # tz-ok: quote timestamps are UTC by contract
    q["expiration"] = pd.to_datetime(q["expiration"], utc=True)  # tz-ok: option expirations are UTC by contract
    numeric = ["strike", "bid", "ask"]
    q[numeric] = q[numeric].apply(pd.to_numeric, errors="coerce")
    q = q[q["timestamp"].notna() & q["expiration"].notna() &
          (q["bid"] >= 0) & (q["ask"] >= q["bid"])].sort_values("timestamp")
    return c, q if not q.empty else None


def _direction(value: object) -> int:
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        if float(value) == 1.0:
            return 1
        if float(value) == -1.0:
            return -1
    text = str(value).strip().lower()
    if text in {"1", "long", "call", "up", "buy"}:
        return 1
    if text in {"-1", "short", "put", "down", "sell"}:
        return -1
    return 0


def _select_contract(row: pd.Series, q: pd.DataFrame,
                     config: EvaluationConfig) -> Optional[tuple[pd.Series, Optional[pd.Series]]]:
    """Select the nearest-expiry, nearest-to-spot contract, then executable quotes."""
    side = _direction(row["prediction"])
    if side == 0:
        return None
    option_type = "call" if side > 0 else "put"
    earliest = row["timestamp"] + pd.Timedelta(milliseconds=config.latency_ms)
    desired_dte = int(row.get("target_dte", 0))
    desired_exp = earliest.normalize() + pd.Timedelta(days=desired_dte)
    eligible = q[(q["instrument"] == row["instrument"]) &
                 (q["option_type"].astype(str).str.lower().str.rstrip("s") == option_type) &
                 (q["timestamp"] >= earliest)]
    if eligible.empty:
        return None
    # Freeze the chain at the first executable snapshot. Looking across later
    # snapshots would use future contract availability to improve selection.
    entry_timestamp = eligible["timestamp"].min()
    universe = eligible[(eligible["timestamp"] == entry_timestamp) &
                        (eligible["expiration"] >= desired_exp)]
    if universe.empty:
        return None
    expir = universe["expiration"].min()
    universe = universe[universe["expiration"] == expir].copy()
    universe["distance"] = (universe["strike"] - float(row["spot"])).abs()
    contract = universe.sort_values(["distance", "strike", "contract"], kind="stable").iloc[0]["contract"]
    entry = universe[universe["contract"] == contract].sort_values("timestamp").iloc[0]
    exit_after = entry["timestamp"] + pd.Timedelta(minutes=config.holding_minutes)
    exits = q[(q["contract"] == contract) & (q["timestamp"] >= exit_after)].sort_values("timestamp")
    if exits.empty:
        return entry, None
    return entry, exits.iloc[0]


def _metrics(events: pd.DataFrame, config: EvaluationConfig) -> Dict[str, Dict[str, float]]:
    alerts = len(events)
    filled = events[events["status"] == "filled"].copy()
    sessions = max(events["session"].nunique(), 1)
    result: Dict[str, Dict[str, float]] = {}
    for label, col in (("gross", "gross_pnl"), ("net", "net_pnl")):
        pnl = filled[col].astype(float) if not filled.empty else pd.Series(dtype=float)
        by_session = filled.groupby("session")[col].sum().reindex(events["session"].drop_duplicates(), fill_value=0.0)
        # Drawdown follows realized exits rather than session-net P&L so an
        # intraday loss cannot be hidden by a later winner in the same session.
        realized = filled.sort_values(["exit_timestamp", "alert_id"], kind="stable")[col]
        equity = realized.cumsum()
        drawdown = equity - equity.cummax().clip(lower=0)
        downside = by_session[by_session < 0].std(ddof=1)
        std = by_session.std(ddof=1)
        wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        result[label] = {
            "total_pnl": float(pnl.sum()),
            "expected_value_per_alert": float(pnl.sum() / alerts) if alerts else 0.0,
            "max_drawdown": float(-drawdown.min()) if not drawdown.empty else 0.0,
            "turnover": float(filled["notional_in"].sum() + filled["notional_out"].sum()),
            "exposure": float(filled["duration_seconds"].sum() / (sessions * 6.5 * 3600)),
            "sharpe": float(by_session.mean() / std * np.sqrt(config.annual_sessions)) if pd.notna(std) and std > 0 else 0.0,
            "sortino": float(by_session.mean() / downside * np.sqrt(config.annual_sessions)) if pd.notna(downside) and downside > 0 else 0.0,
            "profit_factor": float(wins / losses) if losses > 0 else (float("inf") if wins > 0 else 0.0),
            "hit_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
            "alerts": float(alerts),
            "fills": float(len(filled)),
            "fill_rate": float(len(filled) / alerts) if alerts else 0.0,
        }
    return result


def _bootstrap_ci(events: pd.DataFrame, config: EvaluationConfig) -> tuple[float, float]:
    """Session-block bootstrap of net utility per alert (including no-fills)."""
    if events.empty:
        return (0.0, 0.0)
    grouped = events.groupby("session").agg(pnl=("net_pnl", "sum"), alerts=("alert_id", "size"))
    rng = np.random.default_rng(config.random_seed)
    values = np.empty(config.bootstrap_samples)
    for i in range(config.bootstrap_samples):
        sample = grouped.iloc[rng.integers(0, len(grouped), len(grouped))]
        values[i] = sample["pnl"].sum() / sample["alerts"].sum()
    alpha = (1 - config.confidence) / 2
    return tuple(float(v) for v in np.quantile(values, [alpha, 1 - alpha]))


def _baseline_metrics(events: pd.DataFrame, candidates: pd.DataFrame,
                      quotes: Optional[pd.DataFrame], config: EvaluationConfig) -> Dict[str, Dict[str, float]]:
    zero = {k: 0.0 for k in _metrics(events.assign(status="missed", gross_pnl=0.0, net_pnl=0.0), config)["net"]}
    out = {"abstention": zero}
    # Baselines use explicitly supplied OOF decisions.  Never infer them from
    # realized outcomes. Missing decisions mean abstention, not a hidden proxy.
    for name, column in (("class_prior", "class_prior_prediction"),
                         ("buy_and_hold", "buy_hold_prediction"),
                         ("simple_volatility", "volatility_prediction")):
        if column not in candidates:
            out[name] = {**zero, "available": 0.0}
            continue
        baseline_candidates = candidates.copy()
        baseline_candidates["prediction"] = baseline_candidates[column]
        # Common random numbers make missed-fill comparisons paired rather
        # than rewarding a baseline merely for a luckier RNG stream.
        base = _simulate(baseline_candidates, quotes, config,
                         seed=config.random_seed)
        out[name] = {**_metrics(base, config)["net"], "available": 1.0}
    return out


def _simulate(c: pd.DataFrame, q: Optional[pd.DataFrame], config: EvaluationConfig,
              *, seed: int) -> pd.DataFrame:
    """Run one decision stream so every baseline receives identical mechanics."""
    rows = []
    open_until: list[pd.Timestamp] = []
    rng = np.random.default_rng(seed)
    fill_draws = dict(zip(c["alert_id"], rng.random(len(c))))
    for _, candidate in c.iterrows():
        base = {"alert_id": candidate["alert_id"], "timestamp": candidate["timestamp"],
                "session": candidate["session"], "instrument": candidate["instrument"],
                "direction": _direction(candidate["prediction"]), "contract": None,
                "status": "abstained", "gross_pnl": 0.0, "net_pnl": 0.0,
                "notional_in": 0.0, "notional_out": 0.0, "duration_seconds": 0.0}
        if base["direction"] == 0:
            rows.append(base); continue
        if q is None:
            base["status"] = "no_execution_data"; rows.append(base); continue
        selected = _select_contract(candidate, q, config)
        if selected is None:
            base["status"] = "no_executable_quote"; rows.append(base); continue
        entry, exit_quote = selected
        entry_timestamp = entry["timestamp"]
        open_until = [t for t in open_until if t > entry_timestamp]
        if len(open_until) >= config.max_open_positions:
            base["status"] = "position_limit"; rows.append(base); continue
        if fill_draws[candidate["alert_id"]] > config.fill_probability:
            base["status"] = "missed_fill"; rows.append(base); continue
        qty = min(config.contracts_per_trade, config.max_contracts)
        entry_quote_px = float(entry["ask"])
        base.update(contract=entry["contract"], notional_in=(
            entry_quote_px + config.slippage_per_contract_side / config.multiplier
        ) * config.multiplier * qty)
        if exit_quote is None:
            # The entry was executable, so it must consume capacity. Its P&L
            # remains unknown and the report is made ineligible below rather
            # than survivorship-biasing the trade away.
            base["status"] = "open_no_exit_quote"
            open_until.append(pd.Timestamp.max.tz_localize("UTC"))
            rows.append(base)
            continue
        exit_quote_px = float(exit_quote["bid"])
        slip = config.slippage_per_contract_side / config.multiplier
        entry_px = entry_quote_px + slip
        exit_px = max(0.0, exit_quote_px - slip)
        # Gross still honors the executable spread (ask in, bid out); net then
        # deducts explicit slippage and fees. This keeps the cost bridge clear.
        gross = (exit_quote_px - entry_quote_px) * config.multiplier * qty
        net = (exit_px - entry_px) * config.multiplier * qty - 2 * config.fee_per_contract_side * qty
        base.update(status="filled", contract=entry["contract"], gross_pnl=gross,
                    net_pnl=net, notional_in=entry_px * config.multiplier * qty,
                    notional_out=exit_px * config.multiplier * qty,
                    exit_timestamp=exit_quote["timestamp"],
                    duration_seconds=(exit_quote["timestamp"] - entry["timestamp"]).total_seconds())
        open_until.append(exit_quote["timestamp"])
        rows.append(base)
    columns = ["alert_id", "timestamp", "session", "instrument", "direction",
               "contract", "status", "gross_pnl", "net_pnl", "notional_in",
               "notional_out", "duration_seconds", "exit_timestamp"]
    return pd.DataFrame(rows, columns=columns)


def evaluate_oof_events(
    candidates: pd.DataFrame,
    option_quotes: Optional[pd.DataFrame],
    config: EvaluationConfig = EvaluationConfig(),
) -> EvaluationReport:
    """Evaluate OOF decisions sequentially against executable option quotes.

    Required candidate columns are documented in ``_CANDIDATE_REQUIRED``.
    Optional ``target_dte`` controls the deterministic contract rule. Optional
    ``*_prediction`` columns provide already-OOF baseline decisions.
    """
    c, q = _normalise(candidates, option_quotes)
    evidence = "trading-performance evidence" if q is not None else "model-quality evidence only"
    events = _simulate(c, q, config, seed=config.random_seed)
    metrics = _metrics(events, config)
    ci = _bootstrap_ci(events, config)
    metrics["net"] = {**metrics["net"], "session_bootstrap_ci_low": ci[0], "session_bootstrap_ci_high": ci[1]}
    reasons = []
    if q is None:
        reasons.append("options execution data unavailable")
    if not np.isfinite(ci[0]) or ci[0] <= 0:
        reasons.append("net expected utility confidence interval is not above zero")
    if (events["status"] == "open_no_exit_quote").any():
        reasons.append("one or more entered positions lack an executable exit quote")
    if metrics["net"]["max_drawdown"] > config.max_acceptable_drawdown:
        reasons.append("net drawdown exceeds configured limit")
    assumptions = {**asdict(config), "instrument_rule": "candidate instrument",
                   "contract_selection_rule": "prediction side; nearest expiry >= target DTE; nearest strike to signal spot",
                   "entry_rule": "first valid ask after configured latency",
                   "exit_rule": "first valid bid after holding period"}
    return EvaluationReport(evidence, not reasons, tuple(reasons), metrics,
                            _baseline_metrics(events, c, q, config), events, assumptions)
