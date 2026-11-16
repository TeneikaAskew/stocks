"""Actual synthetic monitor decision compatibility; literal pre-change legacy goldens.

No production/captured/holdout inputs or external operations are admitted.
"""

from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch
import io
import pytest
import pandas as pd
# Names are read from the module at call time: another test reloads
# gcp.signal_monitor, and a class imported at collection would then miss
# every patch aimed at the module's current SignalMonitor.
import gcp.signal_monitor as _sm
from lib.strategies.insight_cache import InsightContext


class ExternalBoundaryRefused(BaseException):
    pass


ROWS = {
    "32_color": [(10, 12, 8, 11), (10, 11, 7, 8), (10, 13, 6, 12), (11, 14, 7, 13)],
    "outside212": [(10, 12, 8, 11), (10, 11, 7, 8), (9, 10, 8, 9), (9, 11, 7, 10)],
    "outside312": [(10, 12, 8, 11), (10, 13, 7, 12), (10, 12, 8, 11), (10, 13, 7, 12)],
    "clean": [(10, 12, 8, 11), (11, 13, 9, 12)],
}


def scenario(
    pattern="outside212",
    direction="CALL",
    ftfc=0.6,
    base=4,
    orb=0,
    agreement=False,
    bucket="quiet",
    plan=None,
    repeats=1,
    version=None,
    rvol=2.0,
    rvol_mode=None,
    persisted_brief=False,
):
    with ExitStack() as s, redirect_stdout(io.StringIO()):

        def guard(*a, **k):
            raise ExternalBoundaryRefused("external boundary refused")

        s.enter_context(patch("socket.socket.connect", side_effect=guard))
        s.enter_context(patch("pandas.read_sql", side_effect=guard))
        s.enter_context(patch("pandas.read_sql_query", side_effect=guard))
        s.enter_context(patch("gcp.signal_monitor.requests.get", side_effect=guard))
        s.enter_context(patch("gcp.database.execute_sql", side_effect=guard))
        s.enter_context(patch("gcp.database.upsert_dataframe", side_effect=guard))
        s.enter_context(
            patch(
                "gcp.signal_monitor.SignalMonitor._resolve_watchlist",
                return_value=["SYN"],
            )
        )
        m = _sm.SignalMonitor(
            **({"strat_rule_version": version} if version is not None else {})
        )
        m.webhook_url = "https://synthetic.invalid/refused"
        m.replay_clock_ts = pd.Timestamp("2026-01-06 15:00Z")
        m.volume_baselines["SYN"] = {
            "date": m._now(_sm._ET).date(),
            "baseline": {},
        }
        m.level_maps["SYN"] = object()
        # Prefix leaves terminal patterns unchanged while meeting the actual 30-bar gate.
        rows = [ROWS[pattern][0]] * 32 + ROWS[pattern]
        df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"])
        df["Time"] = pd.date_range(
            "2026-01-06 14:00", periods=len(df), freq="min", tz="UTC"
        )
        if rvol_mode is not None:
            m.signal_cfg.rvol_gate_mode = rvol_mode
        df["RVOL"] = rvol
        df["ATR14"] = 0.1
        df[m.indicator_cfg.rsi_col] = 50.0
        m.windows["SYN"] = df.copy()
        last = float(df.Close.iloc[-1])
        m.orb_levels["SYN"] = {
            "5m_high": last - 1 if orb == 1 else last + 2,
            "5m_low": last + 1 if orb == -1 else last - 2,
        }
        m._brief_bias_cache["SYN"] = {
            "bias": "NEUTRAL",
            "alignment": None,
            "setup_count": 0,
            "ftfc_direction": None,
            "ftfc_score": ftfc,
            "reason": "synthetic",
        }
        if persisted_brief:
            m._brief_bias_cache.clear()
            _sm.get_premarket_bias.cache_clear()
            s.callback(_sm.get_premarket_bias.cache_clear)
            s.enter_context(
                patch("gcp.database.is_cloud_sql_configured", return_value=True)
            )
            s.enter_context(
                patch(
                    "pandas.read_sql",
                    return_value=pd.DataFrame(
                        [
                            {
                                "signal_status": "No signal",
                                "ftfc_direction": "mixed",
                                "ftfc_score": ftfc,
                                "strat_combo": "none",
                                # Canonical sidecar cannot silently replace legacy weighted input.
                                "strat_state": {
                                    "weighted_candle_alignment": {"score": -1.0}
                                },
                            }
                        ]
                    ),
                )
            )
        combo = m.strat.detect_combos(df).strat_combo.iloc[-1]
        s.enter_context(patch.object(m, "calculate_indicators", return_value=df))
        s.enter_context(patch.object(m, "check_orb"))
        s.enter_context(patch.object(m, "check_level_breaks", return_value=[]))
        s.enter_context(
            patch.object(
                m,
                "_evaluate_strategies_for_bar",
                return_value=(
                    {
                        "direction": direction,
                        "base_score": base,
                        "conditions_met": ["synthetic"],
                    },
                    {"composite_score": 5.0} if agreement else None,
                ),
            )
        )
        s.enter_context(
            patch(
                "gcp.signal_monitor.get_catalyst_context",
                return_value={"proximity_bucket": bucket},
            )
        )
        s.enter_context(patch("gcp.database.get_engine", return_value=object()))
        s.enter_context(
            patch(
                "gcp.signal_monitor.fetch_insight_for_ticker",
                return_value=(
                    InsightContext("SYN", plan, "high", "normal") if plan else None
                ),
            )
        )
        for name, value in [
            ("get_call_target", 0.003),
            ("get_put_target", 0.0038),
            ("get_call_time_stop", 30),
            ("get_put_time_stop", 35),
        ]:
            s.enter_context(
                patch(
                    "lib.strategies.exit_config_overrides." + name, return_value=value
                )
            )
        posts = []
        persist = []
        s.enter_context(
            patch(
                "gcp.signal_monitor.requests.post",
                side_effect=lambda *a, **k: posts.append(k["json"]),
            )
        )
        s.enter_context(
            patch.object(
                m,
                "_persist_signal_alert",
                side_effect=lambda *a: persist.append(
                    {
                        "bonus": a[5],
                        "total": a[2],
                        "strength": a[3],
                        "size": a[4],
                        "direction": a[1]["direction"],
                    }
                ),
            )
        )
        for _ in range(repeats):
            m.evaluate_ticker("SYN")
        return {
            "combo": combo,
            "fires": persist,
            "daily_trades": m.daily_trades["SYN"],
            "posts": len(posts),
            "raw": getattr(m, "_latest_raw_score", None),
            "gate": getattr(m, "_latest_gate_action", None),
            "version": m.strat.rule_version,
        }


GOLDENS = [
    (
        "color",
        {"pattern": "32_color"},
        {
            "combo": "clean_2u_bull",
            "fires": [
                {
                    "bonus": 1.25,
                    "total": 5.25,
                    "strength": "strong",
                    "size": 0.75,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 5.25,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "outside212",
        {},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": 2.5,
                    "total": 6.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 6.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "outside312",
        {"pattern": "outside312"},
        {
            "combo": "312_bull_reversal",
            "fires": [
                {
                    "bonus": 2.5,
                    "total": 6.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 6.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "put",
        {"direction": "PUT", "ftfc": -0.6},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": -0.5,
                    "total": 3.5,
                    "strength": "weak",
                    "size": 0.25,
                    "direction": "PUT",
                }
            ],
            "daily_trades": 1,
            "posts": 0,
            "raw": 3.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "opposing",
        {"direction": "PUT", "ftfc": 0.6},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": -2.5,
                    "total": 1.5,
                    "strength": "weak",
                    "size": 0.25,
                    "direction": "PUT",
                }
            ],
            "daily_trades": 1,
            "posts": 0,
            "raw": 1.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "missing",
        {"ftfc": None},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": 1.5,
                    "total": 5.5,
                    "strength": "strong",
                    "size": 0.75,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 5.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "below",
        {"ftfc": 0.599999},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": 1.5,
                    "total": 5.5,
                    "strength": "strong",
                    "size": 0.75,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 5.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "negative_below",
        {"direction": "PUT", "ftfc": -0.599999},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": -1.5,
                    "total": 2.5,
                    "strength": "weak",
                    "size": 0.25,
                    "direction": "PUT",
                }
            ],
            "daily_trades": 1,
            "posts": 0,
            "raw": 2.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "orb",
        {"orb": 1},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": 3.5,
                    "total": 7.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 7.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "stacked_during",
        {"agreement": True, "bucket": "during"},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": 2.5,
                    "total": 5.625,
                    "strength": "strong",
                    "size": 0.75,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 7.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "opposed_weak",
        {"pattern": "32_color", "ftfc": None, "base": 3, "plan": "short"},
        {
            "combo": "clean_2u_bull",
            "fires": [],
            "daily_trades": 0,
            "posts": 0,
            "raw": 3.25,
            "gate": "suppress",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "opposed_medium",
        {"pattern": "32_color", "ftfc": None, "base": 4, "plan": "short"},
        {
            "combo": "clean_2u_bull",
            "fires": [
                {
                    "bonus": 0.25,
                    "total": 4.25,
                    "strength": "weak",
                    "size": 0.5,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 0,
            "raw": 4.25,
            "gate": "downgrade",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "opposed_strong",
        {"base": 4, "ftfc": None, "plan": "short"},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": 1.5,
                    "total": 5.5,
                    "strength": "strong",
                    "size": 0.75,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 5.5,
            "gate": "tag",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "quota",
        {"repeats": 6},
        {
            "combo": "212_bull_reversal",
            "fires": [
                {
                    "bonus": 2.5,
                    "total": 6.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                },
                {
                    "bonus": 2.5,
                    "total": 6.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                },
                {
                    "bonus": 2.5,
                    "total": 6.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                },
                {
                    "bonus": 2.5,
                    "total": 6.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                },
                {
                    "bonus": 2.5,
                    "total": 6.5,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                },
            ],
            "daily_trades": 5,
            "posts": 5,
            "raw": 6.5,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "threshold4",
        {"pattern": "32_color", "ftfc": None, "base": 3.75},
        {
            "combo": "clean_2u_bull",
            "fires": [
                {
                    "bonus": 0.25,
                    "total": 4.0,
                    "strength": "weak",
                    "size": 0.25,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 0,
            "raw": 4.0,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "threshold5",
        {"pattern": "32_color", "ftfc": None, "base": 4.75},
        {
            "combo": "clean_2u_bull",
            "fires": [
                {
                    "bonus": 0.25,
                    "total": 5.0,
                    "strength": "medium",
                    "size": 0.5,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 5.0,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "threshold6",
        {"pattern": "32_color", "ftfc": None, "base": 5.75},
        {
            "combo": "clean_2u_bull",
            "fires": [
                {
                    "bonus": 0.25,
                    "total": 6.0,
                    "strength": "strong",
                    "size": 0.75,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 6.0,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
    (
        "above6",
        {"pattern": "32_color", "ftfc": None, "base": 5.750001},
        {
            "combo": "clean_2u_bull",
            "fires": [
                {
                    "bonus": 0.25,
                    "total": 6.000001,
                    "strength": "perfect",
                    "size": 1.0,
                    "direction": "CALL",
                }
            ],
            "daily_trades": 1,
            "posts": 1,
            "raw": 6.000001,
            "gate": "annotate",
            "version": "legacy-pattern-v1",
        },
    ),
]


@pytest.mark.parametrize("selection", [None, "legacy-pattern-v1"])
@pytest.mark.parametrize("name,inputs,want", GOLDENS, ids=[row[0] for row in GOLDENS])
def test_actual_monitor_legacy_decisions(name, inputs, want, selection):
    # Mutation caught: silently using canonical combo masks changes real scores/fires.
    assert scenario(**inputs, version=selection) == want


@pytest.mark.parametrize(
    "version", ["strat-state-v2", "unknown", "", None, False, 0, [], {}]
)
def test_unadmitted_rule_refused_before_config_or_watchlist(version):
    def forbidden(*a, **k):
        raise ExternalBoundaryRefused("configuration/source work preceded admission")

    with patch("gcp.signal_monitor.load_config", side_effect=forbidden), patch.object(
        _sm.SignalMonitor, "_resolve_watchlist", side_effect=forbidden
    ):
        with pytest.raises(ValueError, match="not admitted"):
            _sm.SignalMonitor(strat_rule_version=version)


@pytest.mark.parametrize(
    "migration",
    [{"strat_basis": "av-adjusted-daily-v1"}, {"strat_input_version": "observed_v2"}],
)
def test_undeclared_input_or_basis_api_is_refused(migration):
    with patch("gcp.signal_monitor.load_config", side_effect=ExternalBoundaryRefused):
        with pytest.raises(TypeError):
            _sm.SignalMonitor(**migration)


@pytest.mark.parametrize("entry", ["monitor", "replay"])
@pytest.mark.parametrize(
    "flags",
    [
        ["--strat-rule-version", "strat-state-v2"],
        ["--strat-rule-version", ""],
        ["--strat-rule-version", "unknown"],
        ["--strat-basis", "av-adjusted-daily-v1"],
        ["--strat-input-version", "observed_v2"],
    ],
)
def test_cli_migration_refused_before_work(entry, flags):
    from gcp import signal_monitor
    from scripts import replay_signal_monitor

    with patch("gcp.database.get_engine", side_effect=ExternalBoundaryRefused), patch(
        "gcp.signal_monitor.load_config", side_effect=ExternalBoundaryRefused
    ), patch("sys.argv", ["signal_monitor", *flags]):
        with pytest.raises(SystemExit) as exc:
            (
                signal_monitor.main()
                if entry == "monitor"
                else replay_signal_monitor.main(flags)
            )
        assert exc.value.code == 2


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("mode", ["loop", "orb-snapshot", "replay"])
def test_monitor_main_explicit_version_reaches_actual_constructor_or_replay(
    mode, explicit
):
    from gcp import signal_monitor

    selected = []

    class StopAtBoundary(BaseException):
        pass

    def construct(*args, **kwargs):
        selected.append(kwargs)
        raise StopAtBoundary

    def replay(argv):
        selected.append(argv)
        raise StopAtBoundary

    argv = ["signal_monitor", "--mode", mode]
    if explicit:
        argv += ["--strat-rule-version", "legacy-pattern-v1"]
    with patch("sys.argv", argv), patch.dict(
        "os.environ",
        {
            "ALPHA_VANTAGE_API_KEY": "synthetic",
            "REPLAY_DATE": "",
            "REPLAY_TICKER": "",
            "REPLAY_TICKERS": "",
        },
    ), patch("gcp.database.is_cloud_sql_configured", return_value=True), patch.object(
        signal_monitor, "SignalMonitor", side_effect=construct
    ), patch(
        "scripts.replay_signal_monitor.main", side_effect=replay
    ):
        with pytest.raises(StopAtBoundary):
            signal_monitor.main()
    assert selected == (
        [["--strat-rule-version", "legacy-pattern-v1"]]
        if mode == "replay"
        else [{"strat_rule_version": "legacy-pattern-v1"}]
    )


@pytest.mark.parametrize("explicit", [False, True])
def test_replay_main_declares_legacy_to_actual_monitor_before_source_read(explicit):
    from scripts import replay_signal_monitor

    selected = []

    class StopAtBoundary(BaseException):
        pass

    def construct(*args, **kwargs):
        selected.append(kwargs)
        raise StopAtBoundary

    flags = ["--ticker", "SYN", "--date", "2026-01-06"]
    if explicit:
        flags += ["--strat-rule-version", "legacy-pattern-v1"]
    with patch("gcp.database.get_engine", return_value=object()), patch(
        "gcp.signal_monitor.SignalMonitor", side_effect=construct
    ), patch.object(
        replay_signal_monitor,
        "load_intraday_for_replay",
        side_effect=ExternalBoundaryRefused,
    ):
        with pytest.raises(StopAtBoundary):
            replay_signal_monitor.main(flags)
    assert selected == [{"strat_rule_version": "legacy-pattern-v1"}]


@pytest.mark.parametrize("value,count", [(None, 0), (0.0, 0), (2.0, 1)])
def test_legacy_scoring_still_respects_actual_rvol_fire_gate(value, count):
    # Existing enforce mode still suppresses before notification/persistence/quota.
    out = scenario(rvol=value, rvol_mode="enforce")
    assert (len(out["fires"]), out["posts"], out["daily_trades"]) == (
        count,
        count,
        count,
    )
    assert out["raw"] == 6.5


@pytest.mark.parametrize("direction,allowed", [("PUT", False), ("CALL", True)])
def test_legacy_monitor_keeps_actual_standalone_disabled_direction_gate(
    direction, allowed
):
    from lib.strategies.base import Signal

    with ExitStack() as s:
        s.enter_context(
            patch.object(_sm.SignalMonitor, "_resolve_watchlist", return_value=["SYN"])
        )
        s.enter_context(
            patch("socket.socket.connect", side_effect=ExternalBoundaryRefused)
        )
        s.enter_context(
            patch("gcp.database.get_engine", side_effect=ExternalBoundaryRefused)
        )
        m = _sm.SignalMonitor()
        m.signal_cfg.enable_standalone_momentum = True
        for name, value in [
            ("get_call_rsi_range", (45, 70)),
            ("get_put_rsi_range", (30, 55)),
            ("get_resolution_tier", "synthetic"),
        ]:
            s.enter_context(patch("gcp.signal_monitor." + name, return_value=value))
        s.enter_context(
            patch(
                "lib.strategies.exit_config_overrides.get_consecutive_periods",
                return_value=3,
            )
        )
        s.enter_context(
            patch("gcp.signal_monitor.get_consecutive_periods", return_value=3)
        )
        s.enter_context(
            patch(
                "lib.strategies.exit_config_overrides.get_disabled_directions",
                return_value={"PUT"},
            )
        )
        s.enter_context(patch("gcp.signal_monitor.evaluate_signal", return_value=None))
        sig = Signal(
            strategy="momentum",
            direction=direction,
            timestamp=pd.Timestamp("2026-01-06 15:00Z"),
            entry_price=10.0,
            base_score=4.0,
            weighted_score=4.0,
            conditions_met=["synthetic"],
        )
        s.enter_context(patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=sig))
        decision, agreement = m._evaluate_strategies_for_bar(
            pd.Series({"Time": sig.timestamp}), 10.0, "SYN"
        )
        assert (decision is not None) is allowed
        assert agreement is None
        assert m.momentum_evaluated_count["SYN"] == 1
        assert m.momentum_fired_count["SYN"] == 1
        assert m.strat.rule_version == "legacy-pattern-v1"


@pytest.mark.parametrize("name", ["outside212", "missing"])
def test_actual_persisted_brief_reader_preserves_legacy_ftfc_selection(name):
    _, inputs, want = next(row for row in GOLDENS if row[0] == name)
    assert scenario(**inputs, persisted_brief=True) == want
