"""DB-backed tests for the Strat playbook formatter.

Drives `lib.strat_levels.build_level_map` + `format_levels_for_brief`
from real OHLCV data — Cloud SQL in `--mode=live`, frozen IWM JSON
fixture in `--mode=mock`. No hardcoded prices, ATRs, or level values:
expected behavior is asserted as structural properties that hold for
any real market data.

Run live  : pytest tests/test_strat_levels_playbook.py
Run mock  : pytest tests/test_strat_levels_playbook.py --mode=mock

The mock path is the deterministic regression baseline.
The live path catches drift in real production data.
"""
from __future__ import annotations

import re

import pytest

from lib.strat_levels import (
    MAX_TRIGGER_DISTANCE_ATR,
    MAX_TRIGGER_DISTANCE_PCT,
    build_level_map,
    format_levels_for_brief,
)


# ───── Commit 1: "Room to T1" relabeling ──────────────────────────────


class TestRoomLabel:
    """The room-to-trigger line was previously labeled 'Room to T1' but
    `room_to_run_up/down` measures current_price → trigger, not
    trigger → T1. Commit 1 renamed it to 'Room to trigger' and
    suppresses the line when no targets exist (so the orphan line
    bug — 'Room to T1: 41.52%' with no T1 above it — can't recur).
    """

    def test_no_stale_label(self, market_data):
        df, price, _ = market_data
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')
        assert 'Room to T1' not in text, (
            "Old 'Room to T1' label resurfaced — should be 'Room to trigger'"
        )

    def test_room_label_present_when_targets_exist(self, market_data):
        df, price, _ = market_data
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')
        # If the playbook emits a CALLS block with targets, the room
        # line must accompany it.
        if lm.calls_trigger and lm.calls_trigger.get('targets'):
            assert 'Room to trigger' in text

    def test_room_line_suppressed_when_no_targets(self, market_data):
        """Construct a synthetic level_map where targets list is empty
        and assert the room line is absent. Uses real DB-driven
        level_map as base, then truncates targets to []."""
        df, price, _ = market_data
        lm = build_level_map('IWM', df, price)

        # Force the bug condition: keep trigger but drop all targets.
        if lm.calls_trigger:
            lm.calls_trigger['targets'] = []
        if lm.puts_trigger:
            lm.puts_trigger['targets'] = []

        text = format_levels_for_brief(lm, 'bullish')
        assert 'Room to trigger' not in text, (
            "Room line printed despite no targets — orphan-label bug"
        )

    def test_room_value_matches_trigger_distance(self, market_data):
        """The number printed in 'Room to trigger: X%' must equal
        (trigger - current_price) / current_price * 100, NOT
        (T1 - current_price)."""
        df, price, _ = market_data
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')

        m = re.search(r'Room to trigger:\s+([\d.]+)%', text)
        if m is None:
            pytest.skip("No 'Room to trigger' line in this fixture's output")
        printed_pct = float(m.group(1))

        # Determine which side rendered (CALLS comes first; PUTS may
        # also render). Prefer CALLS for this assertion when present.
        if lm.calls_trigger and lm.calls_trigger.get('targets'):
            trigger_price = lm.calls_trigger['trigger_level']
            expected_pct = abs(trigger_price - price) / price * 100
            assert abs(printed_pct - expected_pct) < 0.02, (
                f"printed={printed_pct} expected={expected_pct:.2f} "
                f"(trigger={trigger_price} price={price})"
            )

    def test_target_line_count_matches_targets_list(self, market_data):
        """Each emitted Tn line corresponds 1:1 with a target."""
        df, price, _ = market_data
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')

        ct_targets = (lm.calls_trigger or {}).get('targets', [])
        pt_targets = (lm.puts_trigger or {}).get('targets', [])
        emitted = re.findall(r'\n\s+T\d+:\s', '\n' + text)
        # Each side emits len(targets) lines.
        assert len(emitted) == len(ct_targets) + len(pt_targets)


# ───── Commit 2: ATR + % staleness filter ─────────────────────────────


class TestStalenessFilter:
    """When `atr` is passed to build_level_map, levels farther than
    BOTH 3×ATR AND 8% of spot are excluded from trigger AND stop
    selection. The filter prevents stale year-old crash lows (e.g.
    ASTX 2026-04-28: PYL=$15.03, spot=$25.70, distance=41%) from
    surfacing as PUT triggers or 41%-below stop levels on CALL trades.
    """

    def test_emitted_trigger_within_budgets(self, market_data):
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        for side in (lm.calls_trigger, lm.puts_trigger):
            if side is None:
                continue
            distance = abs(side['trigger_level'] - price)
            assert distance <= MAX_TRIGGER_DISTANCE_PCT * price, (
                f"trigger {side['trigger_name']} = {side['trigger_level']} "
                f"is {distance/price*100:.1f}% from spot {price} — "
                f"should be filtered (limit {MAX_TRIGGER_DISTANCE_PCT*100}%)"
            )
            if atr > 0:
                assert distance <= MAX_TRIGGER_DISTANCE_ATR * atr, (
                    f"trigger {side['trigger_name']} = "
                    f"{distance/atr:.2f} ATR away — limit "
                    f"{MAX_TRIGGER_DISTANCE_ATR}"
                )

    def test_emitted_stop_within_budgets(self, market_data):
        """Stops are picked from the OPPOSITE-side fresh level set, so
        the same staleness budgets apply. A stop at 41% from spot is
        useless even if the trigger is fine."""
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        for side in (lm.calls_trigger, lm.puts_trigger):
            if side is None or not side.get('stop'):
                continue
            distance = abs(side['stop'] - price)
            assert distance <= MAX_TRIGGER_DISTANCE_PCT * price, (
                f"stop {side['stop_name']} = {side['stop']} is "
                f"{distance/price*100:.1f}% from spot — should be filtered"
            )

    def test_no_stop_when_no_fresh_opposite(self, market_data):
        """When the staleness filter wipes out one side entirely (e.g.
        ASTX where PYL was the only below-level), the OPPOSITE side's
        stop must be omitted, NOT fall back to the stale level. This
        is the regression test for the 'Stop: 15.03 (PYL)' bug on
        ASTX CALLS where the year-low was being used as a 41% stop."""
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        # Find any side whose stop is None and assert no Stop line for
        # it appears in the rendered text (negative assertion).
        text = format_levels_for_brief(lm, 'bullish')
        if lm.calls_trigger and not lm.calls_trigger.get('stop'):
            # CALLS rendered without a stop: ensure no 'Stop:' line in
            # the CALLS block. We split by the PUTS marker and check
            # only the CALLS half.
            calls_block = text.split('PUTS', 1)[0]
            assert 'Stop:' not in calls_block

    def test_atr_none_falls_back_to_pct_only(self, market_data):
        """Back-compat: callers that don't pass `atr` still get the
        percent-distance filter applied. This protects callers that
        pre-date the ATR plumbing (signal_monitor, dashboard router)."""
        df, price, _ = market_data
        lm = build_level_map('IWM', df, price)  # no atr
        for side in (lm.calls_trigger, lm.puts_trigger):
            if side is None:
                continue
            distance = abs(side['trigger_level'] - price)
            assert distance <= MAX_TRIGGER_DISTANCE_PCT * price

    def test_filtered_levels_still_in_levels_list(self, market_data):
        """Stale levels are filtered out of TRIGGER selection but stay
        in `level_map.levels` so realtime signal_monitor can still
        track break alerts on them. (PYL crossing in either direction
        is a signal worth alerting on, even if it can't drive a
        playbook entry.)"""
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        # PYL must be present in levels regardless of whether it
        # appears in calls/puts trigger.
        names = {lv.name for lv in lm.levels}
        if len(df) >= 252:  # 1y of data
            assert 'PYL' in names
            assert 'PYH' in names

    def test_no_trigger_emits_banner_not_silence(self, market_data):
        """When neither side has a fresh trigger, the formatter emits
        the 'no near-term level' banner, not blank space. (Silently
        deleting both sides would lose the bias-denial setup the
        trader still needs to see for ORB-based execution.)"""
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        # If both triggers are None, the banner must appear for both.
        if lm.calls_trigger is None and lm.puts_trigger is None:
            text = format_levels_for_brief(lm, 'bullish')
            assert 'no near-term structural level' in text

    def test_no_trigger_banner_names_filtered_candidate(self, market_data):
        """Enriched banner: when a side gets filtered, the banner must
        name the actual would-be level + its distance. The trader
        needs to see WHY the side was rejected — '15.03 (41.5% away)'
        is more actionable than 'filtered as stale'.

        Drives the canonical bug case from ASTX 2026-04-28: PYL=15.03
        below spot $25.70 = 41.5% / 1.5× ATR. The banner must mention
        the level name (PYL), price (15.03), and distance.
        """
        from lib.strat_levels import StratLevel, LevelMap, identify_triggers
        # Synthesize a level set with a stale below-side level so the
        # filter fires regardless of what IWM happens to look like
        # today. (IWM tight-range data wouldn't exercise this path.)
        spot = 25.70
        atr_val = 7.02
        levels = [
            StratLevel('PYL', 15.03, 'year', 'low', '', False, '2025'),
            StratLevel('PWL', 26.55, 'week', 'low', '', False, '2026-W17'),
            StratLevel('PDL', 27.13, 'day', 'low', '', False, '2026-04-28'),
        ]
        triggers = identify_triggers(
            spot, {lv.name: lv for lv in levels}, atr=atr_val,
        )
        lm = LevelMap(
            ticker='ASTX', as_of='2026-04-28', current_price=spot,
            levels=levels, pmg_zones=[],
            calls_trigger=triggers['calls'], puts_trigger=triggers['puts'],
            room_to_run_up=(26.55 - spot) / spot * 100,
            room_to_run_down=(spot - 15.03) / spot * 100,
        )
        text = format_levels_for_brief(lm, 'bullish', atr=atr_val)
        # Multi-line banner mirroring active-block indentation.
        assert 'PYL 15.03' in text
        assert 'next bearish level' in text
        # Scope to the PUTS section — the active CALLS block also has
        # its own 'Room to trigger:' line for the fresh trigger, so we
        # need to look at the half of the output that follows the
        # 'next bearish level' line.
        puts_section = text.split('next bearish level', 1)[1]
        room_line = next(
            ln for ln in puts_section.split('\n') if 'Room to trigger' in ln
        )
        assert '41.5%' in room_line
        assert '× ATR' in room_line
        assert 'too far for intraday' in room_line
        # Trailer line is indented like a target line.
        assert '    -- wait for ORB confirmation' in text

    def test_no_trigger_banner_without_atr_omits_atr_str(self):
        """Same banner without `atr` kwarg: shows percent only, no
        '× ATR' suffix. Back-compat for callers that haven't been
        updated to pass ATR."""
        from lib.strat_levels import StratLevel, LevelMap, identify_triggers
        spot = 25.70
        levels = [
            StratLevel('PYL', 15.03, 'year', 'low', '', False, '2025'),
            StratLevel('PWL', 26.55, 'week', 'low', '', False, '2026-W17'),
        ]
        triggers = identify_triggers(spot, {lv.name: lv for lv in levels})
        lm = LevelMap(
            ticker='X', as_of='', current_price=spot,
            levels=levels, pmg_zones=[],
            calls_trigger=triggers['calls'], puts_trigger=triggers['puts'],
            room_to_run_up=0, room_to_run_down=0,
        )
        text = format_levels_for_brief(lm, 'bullish')
        if 'no near-term' in text:
            # No ATR axis qualifier when atr not passed; the banner
            # falls back to "(too far for intraday)" without the
            # "1.5× ATR away" prefix.
            assert '× ATR' not in text
            assert 'too far for intraday' in text


# ───── Commit 4: both-side regime ─────────────────────────────────────


class TestPerSideRegime:
    """Previously the brief computed a single regime in the bias
    direction only. A bullish ticker's PUT bias-denial setup never got
    'extended' / 'orb_only' tagging and could surface a stale trigger
    without warning. Commit 4 evaluates BOTH directions and renders a
    per-side banner, so the wrong-side trigger gets the same filtering
    the primary side does.
    """

    def test_per_side_extended_calls_only(self, market_data):
        """regime_long='extended', regime_short='normal' — only the
        CALLS block carries the warning; PUTS renders normally."""
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        text = format_levels_for_brief(
            lm, 'bullish', regime_long='extended', regime_short='normal',
        )
        if lm.calls_trigger:
            calls_block = text.split('PUTS', 1)[0]
            assert 'extended gap' in calls_block.lower()
        if lm.puts_trigger:
            puts_block = text.split('PUTS', 1)[1] if 'PUTS' in text else ''
            assert 'extended gap' not in puts_block.lower()

    def test_per_side_extended_puts_only(self, market_data):
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        text = format_levels_for_brief(
            lm, 'bullish', regime_long='normal', regime_short='extended',
        )
        if lm.calls_trigger:
            calls_block = text.split('PUTS', 1)[0]
            assert 'extended gap' not in calls_block.lower()
        if lm.puts_trigger:
            puts_block = text.split('PUTS', 1)[1] if 'PUTS' in text else ''
            assert 'extended gap' in puts_block.lower()

    def test_both_orb_only_short_circuits_to_global_block(self, market_data):
        """When BOTH sides clear every structural level, fall back to
        the legacy global 'ORB-only' block (it summarizes the whole
        situation cleaner than two per-side banners)."""
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        text = format_levels_for_brief(
            lm, 'bullish', regime_long='orb_only', regime_short='orb_only',
        )
        assert 'ORB-only' in text

    def test_legacy_regime_param_applies_to_both_sides(self, market_data):
        """Single `regime=` (no per-side) propagates to both sides via
        the default-fallback in the formatter. Back-compat for the
        existing premarket_brief caller pattern."""
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        text_legacy = format_levels_for_brief(lm, 'bullish', regime='extended')
        text_explicit = format_levels_for_brief(
            lm, 'bullish', regime_long='extended', regime_short='extended',
        )
        assert text_legacy == text_explicit


# ───── Commit 5: regime_compute_error surfaced ────────────────────────


class TestRegimeErrorSurface:
    """When the regime classifier raises, the brief used to silently
    fall back to 'normal' — masking real bugs. The error must now be
    visible in the playbook output so the on-call trader can see that
    'normal' is a fallback, not a verified classification.
    """

    def test_error_surfaced_in_output(self, market_data):
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        text = format_levels_for_brief(
            lm, 'bullish',
            regime_compute_error="TypeError: bad atr value",
        )
        assert 'regime classifier failed' in text
        assert 'TypeError' in text

    def test_no_error_no_warning(self, market_data):
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        text = format_levels_for_brief(lm, 'bullish')
        assert 'regime classifier failed' not in text


# ───── Commit 6: trigger picker and room calc agree ───────────────────


class TestTriggerRoomConsistency:
    """`room_to_run_up/down` and `identify_triggers` previously used
    different level sets — triggers used structural-only (prev/current
    period) levels, but room_to_run included gap levels. So a gap
    level closer than the actual trigger could dominate the
    'Room to trigger: X%' line even though no gap-level trigger was
    ever emitted. This invariant ensures both sides agree.
    """

    def test_room_to_run_distance_matches_trigger_distance(self, market_data):
        df, price, atr = market_data
        lm = build_level_map('IWM', df, price, atr=atr)
        if lm.calls_trigger:
            expected_up = abs(lm.calls_trigger['trigger_level'] - price) / price * 100
            assert abs(lm.room_to_run_up - expected_up) < 0.01, (
                f"room_to_run_up={lm.room_to_run_up} but "
                f"trigger distance={expected_up:.4f}% — sets disagree"
            )
        if lm.puts_trigger:
            expected_down = abs(lm.puts_trigger['trigger_level'] - price) / price * 100
            assert abs(lm.room_to_run_down - expected_down) < 0.01, (
                f"room_to_run_down={lm.room_to_run_down} but "
                f"trigger distance={expected_down:.4f}% — sets disagree"
            )
