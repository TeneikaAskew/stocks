# Exact baseline test-node disposition (draft)

Base `02f6df9b5b373c0f65cb3756436e3ad4977aaab6`. Collected with `pytest --collect-only -q tests/gcp/test_premarket_brief.py`: 211 nodes. `pytest -q tests/gcp/test_premarket_brief.py`: 211 passed in 1.71s. Historical d4478433 contains 189 AST test functions; all are still present. AST counts are not a rerun of that historical checkout. Proposed replacement nodes do not yet exist.

Every row below is an individual node; unchanged means test body/assertions unchanged. Shared fixture adjustments require reviewing each affected node; no blanket allowance. Q1 routing fixture already uses AV/UW (EW column names are inert keys), so its test stays unchanged. `test_no_whispers_section_when_no_strategy` already asserts absence and stays unchanged.

| Current collected node | In historical 189 | Proposed head node / disposition | Preserved proof / reason |
|---|---|---|---|
| `tests/gcp/test_premarket_brief.py::test_returns_empty_when_cloud_sql_not_configured` | yes | `tests/gcp/test_premarket_brief.py::test_returns_empty_when_cloud_sql_not_configured` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_returns_empty_envelope_when_query_returns_no_rows` | yes | `tests/gcp/test_premarket_brief.py::test_returns_empty_envelope_when_query_returns_no_rows` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_tier_1_when_all_three_sources_agree` | yes | `tests/gcp/test_premarket_brief.py::test_av_uw_mixed_ew_equals_ew_removed` | Actual SQL excludes EW; retained AV/UW tier 2, empty compatibility keys. |
| `tests/gcp/test_premarket_brief.py::test_tier_6_av_only_long_tail` | yes | `tests/gcp/test_premarket_brief.py::test_tier_6_av_only_long_tail` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_tier_2_av_plus_uw_no_strategy` | yes | `tests/gcp/test_premarket_brief.py::test_tier_2_av_plus_uw_no_strategy` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_tier_2_uw_plus_yahoo_promotes_av_disagreement` | yes | `tests/gcp/test_premarket_brief.py::test_tier_2_uw_plus_yahoo_promotes_av_disagreement` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_tier_1_three_dates_plus_ew` | yes | `tests/gcp/test_premarket_brief.py::test_three_date_sources_mixed_ew_stay_tier2` | Three retained date sources remain tier 2; no EW promotion. |
| `tests/gcp/test_premarket_brief.py::test_tier_4_yahoo_only` | yes | `tests/gcp/test_premarket_brief.py::test_tier_4_yahoo_only` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_tier_4_uw_alone_demoted_from_legacy_tier_5` | yes | `tests/gcp/test_premarket_brief.py::test_tier_4_uw_alone_demoted_from_legacy_tier_5` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_tier_3_yahoo_plus_ew` | yes | `tests/gcp/test_premarket_brief.py::test_yahoo_mixed_ew_stays_tier4` | Actual SQL removes EW, preserves Yahoo tier 4 in include-unconfirmed path. |
| `tests/gcp/test_premarket_brief.py::test_top_n_keeps_highest_tier_first` | yes | `tests/gcp/test_premarket_brief.py::test_top_n_keeps_highest_tier_first` | Retain node and top-N/post-sort assertion; use supported tiers 2/4/6 with ticker order opposing tier order. |
| `tests/gcp/test_premarket_brief.py::test_top_n_zero_returns_all_rows` | yes | `tests/gcp/test_premarket_brief.py::test_top_n_zero_returns_all_rows` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_default_top_n_is_25` | yes | `tests/gcp/test_premarket_brief.py::test_default_top_n_is_25` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_market_cap_coalesces_across_sources` | yes | `tests/gcp/test_premarket_brief.py::test_market_cap_coalesces_across_sources` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_weekly_mode_starts_next_monday` | yes | `tests/gcp/test_premarket_brief.py::test_weekly_mode_starts_next_monday` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_weekly_mode_on_thursday_jumps_to_next_week` | yes | `tests/gcp/test_premarket_brief.py::test_weekly_mode_on_thursday_jumps_to_next_week` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_daily_mode_query_uses_today` | yes | `tests/gcp/test_premarket_brief.py::test_daily_mode_query_uses_today` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_no_high_impact_returns_5m` | yes | `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_no_high_impact_returns_5m` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_830_high_impact_returns_15m` | yes | `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_830_high_impact_returns_15m` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_1000_high_impact_returns_30m` | yes | `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_1000_high_impact_returns_30m` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_empty_events_returns_5m` | yes | `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_empty_events_returns_5m` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_high_impact_at_other_time_returns_5m` | yes | `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_high_impact_at_other_time_returns_5m` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_skips_when_no_playbook` | yes | `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_skips_when_no_playbook` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_renders_when_playbook_present` | yes | `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_renders_when_playbook_present` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_orb_explanation_appears_in_description` | yes | `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_orb_explanation_appears_in_description` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_per_ticker_playbook_explanation_field` | yes | `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_per_ticker_playbook_explanation_field` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_playbook_explanation_omitted_when_blank` | yes | `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_playbook_explanation_omitted_when_blank` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_pegged_top_is_overbought` | yes | `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_pegged_top_is_overbought` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_pegged_bottom_is_oversold` | yes | `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_pegged_bottom_is_oversold` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_mid_range_is_neutral` | yes | `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_mid_range_is_neutral` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_either_line_pegged_top_triggers_overbought` | yes | `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_either_line_pegged_top_triggers_overbought` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_none_input_returns_blank` | yes | `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_none_input_returns_blank` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_bullish_ftfc_gates_to_call_even_when_put_score_higher` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_bullish_ftfc_gates_to_call_even_when_put_score_higher` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_bearish_ftfc_gates_to_put_even_when_call_score_higher` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_bearish_ftfc_gates_to_put_even_when_call_score_higher` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_mixed_ftfc_picks_higher_score_side` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_mixed_ftfc_picks_higher_score_side` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_mixed_ftfc_ties_resolve_to_call` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_mixed_ftfc_ties_resolve_to_call` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_below_building_threshold_returns_no_signal` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_below_building_threshold_returns_no_signal` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_setup_threshold_picks_setup_label_over_building` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_setup_threshold_picks_setup_label_over_building` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_none_ftfc_treated_as_mixed` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_none_ftfc_treated_as_mixed` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_capitalized_bullish_still_gates_correctly` | yes | `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_capitalized_bullish_still_gates_correctly` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_one_day_gap_is_fresh` | yes | `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_one_day_gap_is_fresh` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_zero_day_gap_is_fresh` | yes | `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_zero_day_gap_is_fresh` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_six_day_gap_flags_stale` | yes | `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_six_day_gap_flags_stale` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_friday_to_monday_weekend_exemption` | yes | `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_friday_to_monday_weekend_exemption` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_sunday_weekly_brief_friday_data_is_fresh` | yes | `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_sunday_weekly_brief_friday_data_is_fresh` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_thursday_to_monday_is_stale` | yes | `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_thursday_to_monday_is_stale` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_none_last_bar_returns_unknown` | yes | `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_none_last_bar_returns_unknown` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_renders_at_market_close_in_et` | yes | `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_renders_at_market_close_in_et` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_is_stable_across_dst_transitions` | yes | `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_is_stable_across_dst_transitions` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_display_no_longer_renders_prior_day_at_8pm` | yes | `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_display_no_longer_renders_prior_day_at_8pm` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_healthy_single_bar_window` | yes | `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_healthy_single_bar_window` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_stale_includes_warning_emoji_and_session_count` | yes | `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_stale_includes_warning_emoji_and_session_count` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_none_input_returns_none` | yes | `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_none_input_returns_none` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_322_bull_continuation_capitalized` | yes | `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_322_bull_continuation_capitalized` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_failed_2u_keeps_2u_uppercase` | yes | `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_failed_2u_keeps_2u_uppercase` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_clean_2d_bull` | yes | `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_clean_2d_bull` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_212_bull_reversal` | yes | `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_212_bull_reversal` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_none_or_empty_returns_blank` | yes | `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_none_or_empty_returns_blank` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_lowercase_day_to_uppercase` | yes | `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_lowercase_day_to_uppercase` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_lowercase_week_to_uppercase` | yes | `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_lowercase_week_to_uppercase` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_1mo_collapses_to_1M` | yes | `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_1mo_collapses_to_1M` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_4h_to_4H` | yes | `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_4h_to_4H` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_blank_passthrough` | yes | `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_blank_passthrough` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_prev_h_and_prev_l_on_separate_lines` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_prev_h_and_prev_l_on_separate_lines` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_ema9_and_ema20_on_separate_lines` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_ema9_and_ema20_on_separate_lines` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_rsi_and_stoch_on_separate_lines` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_rsi_and_stoch_on_separate_lines` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_renders_with_overbought_regime_tag` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_renders_with_overbought_regime_tag` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_renders_with_oversold_regime_tag` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_renders_with_oversold_regime_tag` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_neutral_renders_with_neutral_tag` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_neutral_renders_with_neutral_tag` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_three_inline_fields_per_ticker_when_no_llm_analysis` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_three_inline_fields_per_ticker_when_no_llm_analysis` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_strat_field_renders_combo_title_case` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_strat_field_renders_combo_title_case` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_daily_and_combo_render_on_separate_lines` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_daily_and_combo_render_on_separate_lines` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_strat_field_renders_timeframes_uppercase` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_strat_field_renders_timeframes_uppercase` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_llm_analysis_appends_full_width_field` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_llm_analysis_appends_full_width_field` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_two_tickers_each_get_their_own_explanation_block` | yes | `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_two_tickers_each_get_their_own_explanation_block` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestOverviewEmbedSetupExplanation::test_setup_explanation_renders_under_ftfc` | yes | `tests/gcp/test_premarket_brief.py::TestOverviewEmbedSetupExplanation::test_setup_explanation_renders_under_ftfc` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestOverviewEmbedSetupExplanation::test_overview_unchanged_when_no_explanation` | yes | `tests/gcp/test_premarket_brief.py::TestOverviewEmbedSetupExplanation::test_overview_unchanged_when_no_explanation` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_default_returns_today` | yes | `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_default_returns_today` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_explicit_past_date_honoured` | yes | `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_explicit_past_date_honoured` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_blank_falls_back_to_today` | yes | `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_blank_falls_back_to_today` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_future_date_rejected` | yes | `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_future_date_rejected` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_default_unchanged_when_unset` | yes | `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_default_unchanged_when_unset` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_comma_separated` | yes | `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_comma_separated` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_space_separated` | yes | `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_space_separated` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_semicolon_separated` | yes | `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_semicolon_separated` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_blank_falls_back_to_default` | yes | `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_blank_falls_back_to_default` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_cloud_sql_watchlist_supersedes_default` | yes | `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_cloud_sql_watchlist_supersedes_default` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_brief_tickers_env_supersedes_watchlist` | yes | `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_brief_tickers_env_supersedes_watchlist` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBriefAsOfDfCutoff::test_strict_less_than_excludes_analysis_date` | yes | `tests/gcp/test_premarket_brief.py::TestBriefAsOfDfCutoff::test_strict_less_than_excludes_analysis_date` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBriefAsOfDfCutoff::test_tz_aware_index_normalized` | yes | `tests/gcp/test_premarket_brief.py::TestBriefAsOfDfCutoff::test_tz_aware_index_normalized` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_cli_flag_wins` | yes | `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_cli_flag_wins` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_brief_update_env_implies_update` | yes | `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_brief_update_env_implies_update` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_brief_as_of_set_implies_update` | yes | `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_brief_as_of_set_implies_update` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_cloud_scheduler_triggered_by_default_no_update` | yes | `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_cloud_scheduler_triggered_by_default_no_update` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_no_env_no_flag_defaults_to_manual_replay` | yes | `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_no_env_no_flag_defaults_to_manual_replay` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_playbook_failed_writes_to_history_only` | yes | `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_playbook_failed_writes_to_history_only` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_no_data_skips_both_tables` | yes | `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_no_data_skips_both_tables` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_all_playbook_failed_returns_zero_canonical` | yes | `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_all_playbook_failed_returns_zero_canonical` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_playbook_failed_skipped_in_default_path` | yes | `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_playbook_failed_skipped_in_default_path` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_overview_embed_renders_stale_degraded_line` | yes | `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_overview_embed_renders_stale_degraded_line` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_overview_embed_does_not_crash_on_missing_per_ticker_fields` | yes | `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_overview_embed_does_not_crash_on_missing_per_ticker_fields` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_ticker_fields_renders_stale_degraded_field` | yes | `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_ticker_fields_renders_stale_degraded_field` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_singular_session_when_gap_one_treated_as_one_session` | yes | `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_singular_session_when_gap_one_treated_as_one_session` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_stale_writes_history_only_skips_canonical` | yes | `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_stale_writes_history_only_skips_canonical` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_data_as_of_columns_propagate_to_history_rows` | yes | `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_data_as_of_columns_propagate_to_history_rows` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_all_stale_canonical_write_short_circuits` | yes | `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_all_stale_canonical_write_short_circuits` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_brief_level_and_per_ticker_llm_fields_propagate_to_history` | yes | `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_brief_level_and_per_ticker_llm_fields_propagate_to_history` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_missing_llm_fields_persist_as_null` | yes | `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_missing_llm_fields_persist_as_null` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_canonical_upsert_carries_llm_fields` | yes | `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_canonical_upsert_carries_llm_fields` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_high_flow_tier2_beats_zero_flow_tier1` | yes | `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_high_flow_beats_zero_flow_supported_sources` | Remove EW sibling; retain zero-volume rejection and exact SBUX result. |
| `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_tier_breaks_ties_at_same_score` | yes | `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_tier_breaks_ties_at_same_score` | Retain node; equal numeric scores, supported tier2 versus tier4, reversed alphabetical order proves tier tie-break. |
| `tests/gcp/test_premarket_brief.py::TestConfirmedOnlyFilter::test_default_drops_tier_5_uw_only` | yes | `tests/gcp/test_premarket_brief.py::TestConfirmedOnlyFilter::test_default_drops_tier_5_uw_only` | Retain node/AV∩UW assertion; remove EW fixture and obsolete tier1 comment. |
| `tests/gcp/test_premarket_brief.py::TestConfirmedOnlyFilter::test_override_keeps_unconfirmed` | yes | `tests/gcp/test_premarket_brief.py::TestConfirmedOnlyFilter::test_override_keeps_unconfirmed` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_zero_options_volume_filtered_out` | yes | `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_zero_options_volume_filtered_out` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_null_options_volume_filtered_out` | yes | `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_null_options_volume_filtered_out` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_options_volume_propagates_max_across_sources` | yes | `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_options_volume_propagates_max_across_sources` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_specific_time_beats_unknown` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_specific_time_beats_unknown` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_uw_wins_over_av_on_time_when_both_specific` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_uw_wins_over_av_on_time_when_both_specific` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_all_unknown_stays_unknown` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_all_unknown_stays_unknown` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_gap_pct_propagates_to_output_row` | yes | `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_gap_pct_propagates_to_output_row` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_gap_pct_null_when_no_market_data_row` | yes | `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_gap_pct_null_when_no_market_data_row` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_sql_joins_market_data_daily` | yes | `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_sql_joins_market_data_daily` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_daily_partitions_into_two_sections` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_daily_partitions_into_two_sections` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_empty_section_omitted` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_empty_section_omitted` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_per_section_cap_independent` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_per_section_cap_independent` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_no_earnings_renders_placeholder` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_no_earnings_renders_placeholder` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_positive_gap_renders_with_chart_up` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_positive_gap_renders_with_chart_up` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_negative_gap_renders_with_chart_down` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_negative_gap_renders_with_chart_down` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_below_threshold_gap_suppressed` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_below_threshold_gap_suppressed` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_null_gap_renders_no_arrow` | yes | `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_null_gap_renders_no_arrow` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_eps_actual_propagates_from_yahoo_row` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_eps_actual_propagates_from_yahoo_row` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_negative_surprise_preserved` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_negative_surprise_preserved` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_null_actual_keeps_null` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_null_actual_keeps_null` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_beat_renders_check_mark` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_beat_renders_check_mark` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_miss_renders_x_mark` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_miss_renders_x_mark` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_inline_renders_bullseye` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_inline_renders_bullseye` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_no_actual_falls_back_to_estimate` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_no_actual_falls_back_to_estimate` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_surprise_derived_when_yahoo_missing_pct` | yes | `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_surprise_derived_when_yahoo_missing_pct` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_walks_back_over_weekend` | yes | `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_walks_back_over_weekend` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_skips_rows_with_null_gap` | yes | `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_skips_rows_with_null_gap` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_sorts_by_absolute_gap_desc` | yes | `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_sorts_by_absolute_gap_desc` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_top_n_caps_results` | yes | `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_top_n_caps_results` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_no_cloud_sql_returns_empty` | yes | `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_no_cloud_sql_returns_empty` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_section_renders_when_reactions_present` | yes | `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_section_renders_when_reactions_present` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_amc_reactions_row_has_no_tier_badge` | yes | `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_amc_reactions_row_has_no_tier_badge` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_a_verdict_on_todays_row_is_never_rendered` | yes | `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_legacy_today_pick_and_verdict_not_rendered` | Keep today/replay leakage protection; no strategy, strike, verdict or Whispers output. |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_ew_verdict_omitted_when_not_evaluated` | yes | `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_legacy_unscored_pick_not_rendered` | No strategy/strike section even without a verdict. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_strategy_does_not_render_in_bmo_row` | yes | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_legacy_strategy_renders_in_no_section` | Preserve BMO absence; extend absence to whole embed. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_whispers_section_when_no_strategy` | yes | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_whispers_section_when_no_strategy` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_whispers_section_only_lists_strategy_rows` | yes | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_mixed_legacy_strategy_rows_create_no_whispers` | Retain mixed rows; absence of Whispers, non-EW rows preserved. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_reactions_render_between_bmo_and_amc` | yes | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_reactions_render_between_bmo_and_amc` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_section_when_reactions_empty` | yes | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_section_when_reactions_empty` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_section_when_key_absent` | yes | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_section_when_key_absent` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_low_conviction_renders_compact_line_per_bucket` | yes | `tests/gcp/test_premarket_brief.py::test_low_conviction_renders_compact_line_per_bucket` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_low_conviction_included_in_title_and_section_counts` | yes | `tests/gcp/test_premarket_brief.py::test_low_conviction_included_in_title_and_section_counts` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_loader_routes_q1_to_low_conviction_not_dropped` | yes | `tests/gcp/test_premarket_brief.py::test_loader_routes_q1_to_low_conviction_not_dropped` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_empty_when_no_rows` | yes | `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_empty_when_no_rows` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_empty_when_all_realtime` | yes | `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_empty_when_all_realtime` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_footer_when_any_row_used_fallback` | yes | `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_footer_when_any_row_used_fallback` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_accepts_single_dict` | yes | `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_accepts_single_dict` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_handles_rows_missing_data_source` | yes | `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_handles_rows_missing_data_source` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestCalibrationOptionsLoaderObservable::test_logger_exception_fires_on_calibration_failure` | yes | `tests/gcp/test_premarket_brief.py::TestCalibrationOptionsLoaderObservable::test_logger_exception_fires_on_calibration_failure` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestCalibrationOptionsLoaderObservable::test_empty_dict_still_propagates_after_failure` | yes | `tests/gcp/test_premarket_brief.py::TestCalibrationOptionsLoaderObservable::test_empty_dict_still_propagates_after_failure` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_returns_none_when_no_tickers_have_gamma` | yes | `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_returns_none_when_no_tickers_have_gamma` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_returns_none_when_all_unavailable` | yes | `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_returns_none_when_all_unavailable` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_all_realtime_renders_green_live_line` | yes | `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_all_realtime_renders_green_live_line` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_any_eod_fallback_demotes_to_amber` | yes | `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_any_eod_fallback_demotes_to_amber` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_any_stale_fallback_demotes_to_red` | yes | `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_any_stale_fallback_demotes_to_red` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_unavailable_alongside_realtime_still_renders_live` | yes | `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_unavailable_alongside_realtime_still_renders_live` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_formats_utc_iso_as_et_short` | yes | `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_formats_utc_iso_as_et_short` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_overnight_timestamp_gets_weekday_prefix` | yes | `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_overnight_timestamp_gets_weekday_prefix` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_handles_none_and_invalid_gracefully` | yes | `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_handles_none_and_invalid_gracefully` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_real_rowcount_on_success` | yes | `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_real_rowcount_on_success` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_when_no_rows_matched` | yes | `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_when_no_rows_matched` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_when_cloud_sql_not_configured` | yes | `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_when_cloud_sql_not_configured` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_and_swallows_on_execute_error` | yes | `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_and_swallows_on_execute_error` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::test_mondays_brief_recaps_fridays_session` | yes | `tests/gcp/test_premarket_brief.py::test_mondays_brief_has_no_recap_lookup` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_thursday_after_close_pick_is_recapped_monday_not_friday` | yes | `tests/gcp/test_premarket_brief.py::test_legacy_after_close_pick_does_not_trigger_recap` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_todays_rows_never_carry_a_verdict` | yes | `tests/gcp/test_premarket_brief.py::test_retired_columns_absent_from_loader_query` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_the_recap_renders_the_last_sessions_verdicts` | yes | `tests/gcp/test_premarket_brief.py::test_legacy_last_session_verdicts_not_rendered` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_the_recap_renders_on_a_day_without_earnings` | yes | `tests/gcp/test_premarket_brief.py::test_empty_day_ignores_legacy_recap` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_an_unavailable_recap_is_said_not_hidden` | yes | `tests/gcp/test_premarket_brief.py::test_legacy_recap_unavailable_warning_not_rendered` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_failed_recap_query_reads_as_unavailable_not_as_no_picks` | yes | `tests/gcp/test_premarket_brief.py::test_recap_query_is_never_attempted` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_the_recap_survives_a_busy_days_description_cut` | yes | `tests/gcp/test_premarket_brief.py::test_busy_supported_day_has_no_recap_and_is_bounded` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. Use supported-source busy fixture; retain 4090 bound. Old EW-only whole-line reservation is retired; do not assert an unimplemented general whole-line guarantee. |
| `tests/gcp/test_premarket_brief.py::test_the_cut_keeps_whole_lines` | yes | `tests/gcp/test_premarket_brief.py::test_retired_recap_reservation_is_absent` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. Use supported-source busy fixture; retain 4090 bound. Old EW-only whole-line reservation is retired; do not assert an unimplemented general whole-line guarantee. |
| `tests/gcp/test_premarket_brief.py::test_an_unavailable_recap_survives_the_cut_too` | yes | `tests/gcp/test_premarket_brief.py::test_busy_supported_day_has_no_ew_warning` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. Use supported-source busy fixture; retain 4090 bound. Old EW-only whole-line reservation is retired; do not assert an unimplemented general whole-line guarantee. |
| `tests/gcp/test_premarket_brief.py::test_a_database_error_reaches_discord_as_its_class_only` | yes | `tests/gcp/test_premarket_brief.py::test_retired_recap_database_error_cannot_reach_embed` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_quiet_day_is_not_cut` | yes | `tests/gcp/test_premarket_brief.py::test_quiet_supported_day_preserves_complete_content` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_null_metric_read_back_as_nan_renders_as_absent` | yes | `tests/gcp/test_premarket_brief.py::test_legacy_nan_recap_metrics_are_ignored` | Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. This is NOT finite-number proof: numeric classes separately remain in finite-value item 4 on reachable non-EW fields. |
| `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_live_run_keeps_the_now_clock` | no | `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_live_run_keeps_the_now_clock` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_replay_uses_the_premarket_clock_of_the_replay_date` | no | `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_replay_uses_the_premarket_clock_of_the_replay_date` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_replay_ftfc_matches_that_morning_on_the_captured_iwm_history` | no | `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_replay_ftfc_matches_that_morning_on_the_captured_iwm_history` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_tf_bias_labels_and_ftfc_lines_in_order` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_tf_bias_labels_and_ftfc_lines_in_order` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_mixed_and_at_open` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_mixed_and_at_open` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_frames_render_quarter_month_week_day_whatever_the_stored_order` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_frames_render_quarter_month_week_day_whatever_the_stored_order` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_names_the_frame_and_reason` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_names_the_frame_and_reason` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_keeps_judged_frames_and_says_which_open_today` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_keeps_judged_frames_and_says_which_open_today` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_a_period_opening_on_a_later_day_names_its_date` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_a_period_opening_on_a_later_day_names_its_date` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_row_written_before_the_columns_says_not_recorded` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_row_written_before_the_columns_says_not_recorded` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_cached_replay_of_a_migrated_null_row_says_not_recorded[None]` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_cached_replay_of_a_migrated_null_row_says_not_recorded[None]` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_cached_replay_of_a_migrated_null_row_says_not_recorded[nan]` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_cached_replay_of_a_migrated_null_row_says_not_recorded[nan]` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_frames_that_are_not_an_object_render_as_no_frames` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_frames_that_are_not_an_object_render_as_no_frames` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_explanation_inputs_read_a_null_row_as_unavailable[None]` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_explanation_inputs_read_a_null_row_as_unavailable[None]` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_explanation_inputs_read_a_null_row_as_unavailable[nan]` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_explanation_inputs_read_a_null_row_as_unavailable[nan]` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_tf_bias_is_labelled_tf_bias` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_tf_bias_is_labelled_tf_bias` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_overview_summary_line_reads_tf_bias` | no | `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_overview_summary_line_reads_tf_bias` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_row_builder_writes_both_columns_to_history_and_canonical` | no | `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_row_builder_writes_both_columns_to_history_and_canonical` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_missing_state_stays_null` | no | `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_missing_state_stays_null` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_writers_drop_the_new_keys_on_tables_without_the_columns` | no | `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_writers_drop_the_new_keys_on_tables_without_the_columns` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestExplanationInputsReadTfBias::test_overview_ticker_and_playbook_inputs` | no | `tests/gcp/test_premarket_brief.py::TestExplanationInputsReadTfBias::test_overview_ticker_and_playbook_inputs` | Unchanged non-EW behavior/assertions. |
| `tests/gcp/test_premarket_brief.py::TestExplanationInputsReadTfBias::test_missing_score_and_state_read_unavailable` | no | `tests/gcp/test_premarket_brief.py::TestExplanationInputsReadTfBias::test_missing_score_and_state_read_unavailable` | Unchanged non-EW behavior/assertions. |

## Caller files

`tests/gcp/test_strat_snapshot_parity.py::_brief` and `tests/api/test_brief_level_break_response.py::_run_brief_and_persist`: remove only obsolete `_ew_recap_or_unavailable` monkeypatch. Preserve all collected caller nodes and assertions; the accompanying caller-node receipt lists exact parametrized IDs. No finite-values code is changed.

Proposed dispositions: 24 existing nodes require explicit retirement/fixture adaptation; 187 remain unchanged. Add the eight acceptance groups in the P-D spec in addition to mapped replacements, with duplicates consolidated only by an explicit node-to-item map. Counts alone are never acceptance.


## November 11 caller-scope successor proposal qualification

Current-main base: `3991c628ff2a614ce5f74a1aa9ca1843d1faca80`. The shared-level caller inventory is now **45 collected nodes**, superseding the historical 43-node count for current qualification only. Base and isolated preparation collect exactly the same list below. The preparation applies the preserved P-D source diff and removes only the obsolete recap monkeypatch in `tests/lib/strat_2026_11_06.py::run_brief` (main line 152). This is uncommitted proposal qualification, not admitted or published implementation. No assertion, fixture setup, parametrization, skip or xfail changes. The two previously admitted caller files likewise lose only their obsolete stub; incoming #1784 setup remains intact.

The three current-main caller suites pass **45 tests in 22.75s**. Before the additional stub is removed from the preparation, `tests/gcp/test_premarket_provenance.py::test_brief_level_basis_carries_provenance` fails with `AttributeError` at line 152, because `_ew_recap_or_unavailable` has been removed. Final preparation results are recorded in the proposal PR; no historical receipt proves a new source head.

| Base collected node | Preparation disposition |
|---|---|
| `tests/lib/test_brief_planner_parity.py::test_brief_and_planner_pick_the_same_levels[IWM]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/lib/test_brief_planner_parity.py::test_brief_and_planner_pick_the_same_levels[QQQ]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/lib/test_brief_planner_parity.py::test_brief_and_planner_pick_the_same_levels[SPY]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/lib/test_brief_planner_parity.py::test_origin_main_level_code_reproduces_the_stored_picks[IWM]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/lib/test_brief_planner_parity.py::test_origin_main_level_code_reproduces_the_stored_picks[QQQ]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/lib/test_brief_planner_parity.py::test_origin_main_level_code_reproduces_the_stored_picks[SPY]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_brief_basis_is_plain_json_with_what_the_spec_lists` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_persist_writes_level_basis_to_both_tables` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_writers_drop_the_column_when_it_is_absent` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_upsert_binds_level_basis_as_jsonb_when_present` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_planner_for_a_brief_ticker_loads_no_daily_bars` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_rewriting_daily_bars_after_the_brief_changes_no_planner_level` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_planner_applies_a_newer_premarket_snapshot` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_a_declining_low_replaces_the_short_candidate` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_read_live_level_basis_ignores_a_replay_row` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_each_live_reader_ignores_a_replay_row[planner]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_each_live_reader_ignores_a_replay_row[signal_monitor]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_each_live_reader_ignores_a_replay_row[movement_statement]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_each_reader_builds_when_the_column_is_absent[planner]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_each_reader_builds_when_the_column_is_absent[signal_monitor]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_each_reader_builds_when_the_column_is_absent[movement_statement]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_resolver_reads_live_basis_ignores_replay_and_builds_without_the_column` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_read_session_premarket_raises_on_a_failed_query` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_read_session_premarket_retries_without_provenance_on_a_missing_column` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_level_basis.py::test_read_live_level_basis_raises_on_a_failed_query_and_none_on_a_missing_column` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_daily_frame_snapshot_carries_provenance_into_level_basis` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_naive_fetch_time_is_read_as_utc` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_level_basis_round_trip_keeps_provenance` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_brief_level_basis_carries_provenance` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_planner_reads_provenance_from_market_data_daily` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_refresh_writer_records_fetch_time_and_counts` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_nightly_writer_records_fetch_time_and_counts` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_writes_provenance_when_the_columns_exist` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[columns0]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[columns1]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[None]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[columns3]` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_nightly_row_to_a_table_without_the_columns_drops_them` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_frame_without_the_columns_builds_with_null_provenance` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_read_session_premarket_falls_back_without_the_columns` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_read_session_premarket_falls_back_when_the_query_swallows_errors` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_resolver_builds_from_a_table_without_the_columns` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_data_loader_retries_without_the_columns` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_data_loader_transient_error_does_not_mark_the_columns_missing` | Same node and unchanged assertion body; obsolete helper stub only. |
| `tests/gcp/test_premarket_provenance.py::test_data_loader_reads_the_columns_when_present` | Same node and unchanged assertion body; obsolete helper stub only. |

## Executed current-main reconciliation — 2026-11-12

Base `75493a4753ec4dbcfbaa8663477c3943710a2069`. The opening 211-node inventory is historical; this section records the actual implementation inputs. The six scoped suites collect 271 base nodes and 282 candidate nodes; base passed 271 (26.82s), candidate passed 282 (24.81s), five existing pandas warnings in each, no skips. All 54 caller nodes are identical. The three caller files change only their one obsolete recap stub each. Current RSI calibration and holiday-freshness implementation, `_valid_num`, and all finite-values obligations are preserved.

191 retained brief test function bodies are byte-identical. Retained adapted tests (explicit original inventory obligations, no lost assertions): `TestConfirmedOnlyFilter::test_default_drops_tier_5_uw_only`, `TestTradeabilityRanking::test_tier_breaks_ties_at_same_score`, `test_top_n_keeps_highest_tier_first`.

The mixed NULL/string source display sort previously raised TypeError on both original and current baseline. The minimal key orders NULL first and leaves string ordering unchanged; it is necessary for the admitted NULL-retention control. This is not numeric normalization.

### Exact current node dispositions

| Base node | Candidate disposition |
|---|---|
| `tests/gcp/test_premarket_brief.py::test_returns_empty_when_cloud_sql_not_configured` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_returns_empty_envelope_when_query_returns_no_rows` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_tier_1_when_all_three_sources_agree` | `tests/gcp/test_premarket_brief.py::test_av_uw_mixed_ew_equals_ew_removed` — Actual SQL excludes EW; retained AV/UW tier 2, empty compatibility keys. |
| `tests/gcp/test_premarket_brief.py::test_tier_6_av_only_long_tail` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_tier_2_av_plus_uw_no_strategy` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_tier_2_uw_plus_yahoo_promotes_av_disagreement` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_tier_1_three_dates_plus_ew` | `tests/gcp/test_premarket_brief.py::test_three_date_sources_mixed_ew_stay_tier2` — Three retained date sources remain tier 2; no EW promotion. |
| `tests/gcp/test_premarket_brief.py::test_tier_4_yahoo_only` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_tier_4_uw_alone_demoted_from_legacy_tier_5` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_tier_3_yahoo_plus_ew` | `tests/gcp/test_premarket_brief.py::test_yahoo_mixed_ew_stays_tier4` — Actual SQL removes EW, preserves Yahoo tier 4 in include-unconfirmed path. |
| `tests/gcp/test_premarket_brief.py::test_top_n_keeps_highest_tier_first` | Same node; adapted fixture per original inventory |
| `tests/gcp/test_premarket_brief.py::test_top_n_zero_returns_all_rows` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_default_top_n_is_25` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_market_cap_coalesces_across_sources` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_weekly_mode_starts_next_monday` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_weekly_mode_on_thursday_jumps_to_next_week` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_daily_mode_query_uses_today` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_no_high_impact_returns_5m` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_830_high_impact_returns_15m` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_1000_high_impact_returns_30m` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_empty_events_returns_5m` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestSelectOrbWindow::test_high_impact_at_other_time_returns_5m` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_skips_when_no_playbook` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_renders_when_playbook_present` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_orb_explanation_appears_in_description` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_per_ticker_playbook_explanation_field` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPlaybookEmbed::test_playbook_explanation_omitted_when_blank` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_pegged_top_is_overbought` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_pegged_bottom_is_oversold` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_mid_range_is_neutral` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_either_line_pegged_top_triggers_overbought` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStochRegimeTag::test_none_input_returns_blank` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_bullish_ftfc_gates_to_call_even_when_put_score_higher` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_bearish_ftfc_gates_to_put_even_when_call_score_higher` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_mixed_ftfc_picks_higher_score_side` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_mixed_ftfc_ties_resolve_to_call` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_below_building_threshold_returns_no_signal` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_setup_threshold_picks_setup_label_over_building` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_none_ftfc_treated_as_mixed` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveSignalStatus::test_capitalized_bullish_still_gates_correctly` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_one_day_gap_is_fresh` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_zero_day_gap_is_fresh` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_six_day_gap_flags_stale` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_friday_to_monday_weekend_exemption` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_sunday_weekly_brief_friday_data_is_fresh` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_thursday_to_monday_is_stale` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveDataFreshness::test_none_last_bar_returns_unknown` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBriefRsiBands::test_tier_a_band_is_resolved_as_of_the_analysis_date` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBriefRsiBands::test_no_calibration_row_scores_as_before` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBriefRsiBands::test_the_brief_never_scores_with_default_bands` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBriefAfterHoliday::test_friday_after_thanksgiving_is_scored` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBriefAfterHoliday::test_missing_wednesday_is_still_stale` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_renders_at_market_close_in_et` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_is_stable_across_dst_transitions` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDataAsOfAnchor::test_anchor_display_no_longer_renders_prior_day_at_8pm` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_healthy_single_bar_window` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_stale_includes_warning_emoji_and_session_count` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFormatDataFreshnessSummary::test_none_input_returns_none` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_322_bull_continuation_capitalized` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_failed_2u_keeps_2u_uppercase` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_clean_2d_bull` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_212_bull_reversal` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtCombo::test_none_or_empty_returns_blank` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_lowercase_day_to_uppercase` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_lowercase_week_to_uppercase` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_1mo_collapses_to_1M` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_4h_to_4H` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtTimeframe::test_blank_passthrough` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_prev_h_and_prev_l_on_separate_lines` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_ema9_and_ema20_on_separate_lines` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_rsi_and_stoch_on_separate_lines` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_renders_with_overbought_regime_tag` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_renders_with_oversold_regime_tag` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_stochrsi_neutral_renders_with_neutral_tag` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_three_inline_fields_per_ticker_when_no_llm_analysis` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_strat_field_renders_combo_title_case` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_daily_and_combo_render_on_separate_lines` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_strat_field_renders_timeframes_uppercase` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_llm_analysis_appends_full_width_field` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTickerFieldsLayout::test_two_tickers_each_get_their_own_explanation_block` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestOverviewEmbedSetupExplanation::test_setup_explanation_renders_under_ftfc` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestOverviewEmbedSetupExplanation::test_overview_unchanged_when_no_explanation` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_default_returns_today` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_explicit_past_date_honoured` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_blank_falls_back_to_today` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_future_date_rejected` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_default_unchanged_when_unset` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_comma_separated` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_space_separated` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_semicolon_separated` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_blank_falls_back_to_default` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_cloud_sql_watchlist_supersedes_default` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveBriefTickers::test_brief_tickers_env_supersedes_watchlist` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBriefAsOfDfCutoff::test_strict_less_than_excludes_analysis_date` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBriefAsOfDfCutoff::test_tz_aware_index_normalized` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_cli_flag_wins` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_brief_update_env_implies_update` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_brief_as_of_set_implies_update` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_cloud_scheduler_triggered_by_default_no_update` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestResolveRunKindAndUpdate::test_no_env_no_flag_defaults_to_manual_replay` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_playbook_failed_writes_to_history_only` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_no_data_skips_both_tables` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_all_playbook_failed_returns_zero_canonical` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistPlaybookFailedHandling::test_playbook_failed_skipped_in_default_path` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_overview_embed_renders_stale_degraded_line` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_overview_embed_does_not_crash_on_missing_per_ticker_fields` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_ticker_fields_renders_stale_degraded_field` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStaleEmbedRenders::test_singular_session_when_gap_one_treated_as_one_session` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_stale_writes_history_only_skips_canonical` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_data_as_of_columns_propagate_to_history_rows` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistStaleDataHandling::test_all_stale_canonical_write_short_circuits` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_brief_level_and_per_ticker_llm_fields_propagate_to_history` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_missing_llm_fields_persist_as_null` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestPersistLLMCommentary::test_canonical_upsert_carries_llm_fields` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_high_flow_tier2_beats_zero_flow_tier1` | `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_high_flow_beats_zero_flow_supported_sources` — Remove EW sibling; retain zero-volume rejection and exact SBUX result. |
| `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_tier_breaks_ties_at_same_score` | Same node; adapted fixture per original inventory |
| `tests/gcp/test_premarket_brief.py::TestConfirmedOnlyFilter::test_default_drops_tier_5_uw_only` | Same node; adapted fixture per original inventory |
| `tests/gcp/test_premarket_brief.py::TestConfirmedOnlyFilter::test_override_keeps_unconfirmed` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_zero_options_volume_filtered_out` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_null_options_volume_filtered_out` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestOptionsFlowFilter::test_options_volume_propagates_max_across_sources` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_specific_time_beats_unknown` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_uw_wins_over_av_on_time_when_both_specific` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsTimePicker::test_all_unknown_stays_unknown` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_gap_pct_propagates_to_output_row` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_gap_pct_null_when_no_market_data_row` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestGapPctPropagation::test_sql_joins_market_data_daily` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_daily_partitions_into_two_sections` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_empty_section_omitted` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_per_section_cap_independent` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedSectionSplit::test_no_earnings_renders_placeholder` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_positive_gap_renders_with_chart_up` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_negative_gap_renders_with_chart_down` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_below_threshold_gap_suppressed` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEarningsEmbedGapRender::test_null_gap_renders_no_arrow` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_eps_actual_propagates_from_yahoo_row` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_negative_surprise_preserved` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissPropagation::test_null_actual_keeps_null` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_beat_renders_check_mark` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_miss_renders_x_mark` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_inline_renders_bullseye` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_no_actual_falls_back_to_estimate` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBeatMissRender::test_surprise_derived_when_yahoo_missing_pct` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_walks_back_over_weekend` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_skips_rows_with_null_gap` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_sorts_by_absolute_gap_desc` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_top_n_caps_results` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestYesterdayAmcReactionsLoader::test_no_cloud_sql_returns_empty` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_section_renders_when_reactions_present` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_amc_reactions_row_has_no_tier_badge` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_a_verdict_on_todays_row_is_never_rendered` | `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_legacy_today_pick_and_verdict_not_rendered` — Keep today/replay leakage protection; no strategy, strike, verdict or Whispers output. |
| `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_ew_verdict_omitted_when_not_evaluated` | `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_legacy_unscored_pick_not_rendered` — No strategy/strike section even without a verdict. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_strategy_does_not_render_in_bmo_row` | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_legacy_strategy_renders_in_no_section` — Preserve BMO absence; extend absence to whole embed. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_whispers_section_when_no_strategy` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_whispers_section_only_lists_strategy_rows` | `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_mixed_legacy_strategy_rows_create_no_whispers` — Retain mixed rows; absence of Whispers, non-EW rows preserved. |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_reactions_render_between_bmo_and_amc` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_section_when_reactions_empty` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_no_section_when_key_absent` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_low_conviction_renders_compact_line_per_bucket` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_low_conviction_included_in_title_and_section_counts` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_loader_routes_q1_to_low_conviction_not_dropped` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_empty_when_no_rows` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_empty_when_all_realtime` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_footer_when_any_row_used_fallback` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_accepts_single_dict` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestEmpiricalFallbackFooter::test_handles_rows_missing_data_source` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestCalibrationOptionsLoaderObservable::test_logger_exception_fires_on_calibration_failure` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestCalibrationOptionsLoaderObservable::test_empty_dict_still_propagates_after_failure` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_returns_none_when_no_tickers_have_gamma` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_returns_none_when_all_unavailable` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_all_realtime_renders_green_live_line` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_any_eod_fallback_demotes_to_amber` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_any_stale_fallback_demotes_to_red` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestBuildGammaFooter::test_unavailable_alongside_realtime_still_renders_live` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_formats_utc_iso_as_et_short` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_overnight_timestamp_gets_weekday_prefix` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFmtGammaTs::test_handles_none_and_invalid_gracefully` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_real_rowcount_on_success` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_never_deletes_the_sessions_own_premarket_row` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_when_no_rows_matched` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_when_cloud_sql_not_configured` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestDeleteNullCloseRows::test_returns_zero_and_swallows_on_execute_error` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::test_mondays_brief_recaps_fridays_session` | `tests/gcp/test_premarket_brief.py::test_mondays_brief_has_no_recap_lookup` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_thursday_after_close_pick_is_recapped_monday_not_friday` | `tests/gcp/test_premarket_brief.py::test_legacy_after_close_pick_does_not_trigger_recap` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_todays_rows_never_carry_a_verdict` | `tests/gcp/test_premarket_brief.py::test_retired_columns_absent_from_loader_query` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_the_recap_renders_the_last_sessions_verdicts` | `tests/gcp/test_premarket_brief.py::test_legacy_last_session_verdicts_not_rendered` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_the_recap_renders_on_a_day_without_earnings` | `tests/gcp/test_premarket_brief.py::test_empty_day_ignores_legacy_recap` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_an_unavailable_recap_is_said_not_hidden` | `tests/gcp/test_premarket_brief.py::test_legacy_recap_unavailable_warning_not_rendered` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_failed_recap_query_reads_as_unavailable_not_as_no_picks` | `tests/gcp/test_premarket_brief.py::test_recap_query_is_never_attempted` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_the_recap_survives_a_busy_days_description_cut` | `tests/gcp/test_premarket_brief.py::test_busy_supported_day_has_no_recap_and_is_bounded` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. Use supported-source busy fixture; retain 4090 bound. Old EW-only whole-line reservation is retired; do not assert an unimplemented general whole-line guarantee. |
| `tests/gcp/test_premarket_brief.py::test_the_cut_keeps_whole_lines` | `tests/gcp/test_premarket_brief.py::test_retired_recap_reservation_is_absent` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. Use supported-source busy fixture; retain 4090 bound. Old EW-only whole-line reservation is retired; do not assert an unimplemented general whole-line guarantee. |
| `tests/gcp/test_premarket_brief.py::test_an_unavailable_recap_survives_the_cut_too` | `tests/gcp/test_premarket_brief.py::test_busy_supported_day_has_no_ew_warning` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. Use supported-source busy fixture; retain 4090 bound. Old EW-only whole-line reservation is retired; do not assert an unimplemented general whole-line guarantee. |
| `tests/gcp/test_premarket_brief.py::test_a_database_error_reaches_discord_as_its_class_only` | `tests/gcp/test_premarket_brief.py::test_retired_recap_database_error_cannot_reach_embed` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_quiet_day_is_not_cut` | `tests/gcp/test_premarket_brief.py::test_quiet_supported_day_preserves_complete_content` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. |
| `tests/gcp/test_premarket_brief.py::test_a_null_metric_read_back_as_nan_renders_as_absent` | `tests/gcp/test_premarket_brief.py::test_legacy_nan_recap_metrics_are_ignored` — Replace EW-only recap assertion with retirement absence on same scenario; preserve non-EW output. This is NOT finite-number proof: numeric classes separately remain in finite-value item 4 on reachable non-EW fields. |
| `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_live_run_keeps_the_now_clock` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_replay_uses_the_premarket_clock_of_the_replay_date` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestStratReplayClock::test_replay_ftfc_matches_that_morning_on_the_captured_iwm_history` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_tf_bias_labels_and_ftfc_lines_in_order` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_mixed_and_at_open` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_frames_render_quarter_month_week_day_whatever_the_stored_order` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_names_the_frame_and_reason` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_keeps_judged_frames_and_says_which_open_today` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_a_period_opening_on_a_later_day_names_its_date` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_row_written_before_the_columns_says_not_recorded` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_cached_replay_of_a_migrated_null_row_says_not_recorded[None]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_cached_replay_of_a_migrated_null_row_says_not_recorded[nan]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_frames_that_are_not_an_object_render_as_no_frames` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_explanation_inputs_read_a_null_row_as_unavailable[None]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_explanation_inputs_read_a_null_row_as_unavailable[nan]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_tf_bias_is_labelled_tf_bias` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_overview_summary_line_reads_tf_bias` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_row_builder_writes_both_columns_to_history_and_canonical` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_missing_state_stays_null` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestFtfcPersistence::test_writers_drop_the_new_keys_on_tables_without_the_columns` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestExplanationInputsReadTfBias::test_overview_ticker_and_playbook_inputs` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_brief.py::TestExplanationInputsReadTfBias::test_missing_score_and_state_read_unavailable` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_foundation_brief_unavailable_is_not_inside` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_nov5_brief_strat_box_shows_tf_bias_and_ftfc[QQQ-FTFC: bearish (Q red, M red, W red)-TF bias: +0.5 (bullish)-1D:2U 1W:2D 1M:2D-bearish]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_nov5_brief_strat_box_shows_tf_bias_and_ftfc[IWM-FTFC: bullish (Q green, M green, W green)-TF bias: +1.0 (bullish)-1D:2U 1W:2U 1M:2U-bullish]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_nov5_brief_strat_box_shows_tf_bias_and_ftfc[SPY-FTFC: bullish (Q green, M green, W green)-TF bias: +1.0 (bullish)-1D:2U 1W:2U 1M:1-bullish]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_first_session_of_month_and_week_keeps_judged_frames[QQQ-FTFC: unavailable (Q red, M opens today, W opens today)]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_first_session_of_month_and_week_keeps_judged_frames[IWM-FTFC: unavailable (Q green, M opens today, W opens today)]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_first_session_of_month_and_week_keeps_judged_frames[SPY-FTFC: unavailable (Q red, M opens today, W opens today)]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_strat_snapshot_parity.py::test_captured_foundation_diagnostic_matches_actual_producers` | Same node; unchanged test body/assertions |
| `tests/api/test_brief_level_break_response.py::test_a_level_break_changes_the_published_brief_status` | Same node; unchanged test body/assertions |
| `tests/lib/test_brief_planner_parity.py::test_brief_and_planner_pick_the_same_levels[IWM]` | Same node; unchanged test body/assertions |
| `tests/lib/test_brief_planner_parity.py::test_brief_and_planner_pick_the_same_levels[QQQ]` | Same node; unchanged test body/assertions |
| `tests/lib/test_brief_planner_parity.py::test_brief_and_planner_pick_the_same_levels[SPY]` | Same node; unchanged test body/assertions |
| `tests/lib/test_brief_planner_parity.py::test_origin_main_level_code_reproduces_the_stored_picks[IWM]` | Same node; unchanged test body/assertions |
| `tests/lib/test_brief_planner_parity.py::test_origin_main_level_code_reproduces_the_stored_picks[QQQ]` | Same node; unchanged test body/assertions |
| `tests/lib/test_brief_planner_parity.py::test_origin_main_level_code_reproduces_the_stored_picks[SPY]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_brief_basis_is_plain_json_with_what_the_spec_lists` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_persist_writes_level_basis_to_both_tables` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_writers_drop_the_column_when_it_is_absent` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_upsert_binds_level_basis_as_jsonb_when_present` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_planner_for_a_brief_ticker_loads_no_daily_bars` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_rewriting_daily_bars_after_the_brief_changes_no_planner_level` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_planner_applies_a_newer_premarket_snapshot` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_a_declining_low_replaces_the_short_candidate` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_read_live_level_basis_ignores_a_replay_row` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_each_live_reader_ignores_a_replay_row[planner]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_each_live_reader_ignores_a_replay_row[signal_monitor]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_each_live_reader_ignores_a_replay_row[movement_statement]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_each_reader_builds_when_the_column_is_absent[planner]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_each_reader_builds_when_the_column_is_absent[signal_monitor]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_each_reader_builds_when_the_column_is_absent[movement_statement]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_resolver_reads_live_basis_ignores_replay_and_builds_without_the_column` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_read_session_premarket_raises_on_a_failed_query` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_read_session_premarket_retries_without_provenance_on_a_missing_column` | Same node; unchanged test body/assertions |
| `tests/gcp/test_level_basis.py::test_read_live_level_basis_raises_on_a_failed_query_and_none_on_a_missing_column` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_daily_frame_snapshot_carries_provenance_into_level_basis` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_naive_fetch_time_is_read_as_utc` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_level_basis_round_trip_keeps_provenance` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_brief_level_basis_carries_provenance` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_planner_reads_provenance_from_market_data_daily` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_refresh_writer_records_fetch_time_and_counts` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_nightly_writer_records_fetch_time_and_counts` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_writes_provenance_when_the_columns_exist` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[columns0]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[columns1]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[None]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_refresh_upsert_leaves_the_columns_out_when_absent[columns3]` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_nightly_row_to_a_table_without_the_columns_drops_them` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_frame_without_the_columns_builds_with_null_provenance` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_read_session_premarket_falls_back_without_the_columns` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_read_session_premarket_falls_back_when_the_query_swallows_errors` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_resolver_builds_from_a_table_without_the_columns` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_data_loader_retries_without_the_columns` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_data_loader_transient_error_does_not_mark_the_columns_missing` | Same node; unchanged test body/assertions |
| `tests/gcp/test_premarket_provenance.py::test_data_loader_reads_the_columns_when_present` | Same node; unchanged test body/assertions |

Additional candidate nodes (beyond base):

- `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_legacy_today_pick_and_verdict_not_rendered`
- `tests/gcp/test_premarket_brief.py::TestEmbedAmcReactionsSection::test_legacy_unscored_pick_not_rendered`
- `tests/gcp/test_premarket_brief.py::TestTradeabilityRanking::test_high_flow_beats_zero_flow_supported_sources`
- `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_legacy_strategy_renders_in_no_section`
- `tests/gcp/test_premarket_brief.py::TestWhispersSection::test_mixed_legacy_strategy_rows_create_no_whispers`
- `tests/gcp/test_premarket_brief.py::test_av_uw_mixed_ew_equals_ew_removed`
- `tests/gcp/test_premarket_brief.py::test_brief_pipeline_never_acquires_ew_recap[2026-04-26-False]`
- `tests/gcp/test_premarket_brief.py::test_brief_pipeline_never_acquires_ew_recap[2026-04-27-False]`
- `tests/gcp/test_premarket_brief.py::test_brief_pipeline_never_acquires_ew_recap[2026-04-27-True]`
- `tests/gcp/test_premarket_brief.py::test_busy_supported_day_has_no_ew_warning`
- `tests/gcp/test_premarket_brief.py::test_busy_supported_day_has_no_recap_and_is_bounded`
- `tests/gcp/test_premarket_brief.py::test_empty_day_ignores_legacy_recap`
- `tests/gcp/test_premarket_brief.py::test_legacy_after_close_pick_does_not_trigger_recap`
- `tests/gcp/test_premarket_brief.py::test_legacy_ew_payload_cannot_render[daily]`
- `tests/gcp/test_premarket_brief.py::test_legacy_ew_payload_cannot_render[weekly]`
- `tests/gcp/test_premarket_brief.py::test_legacy_last_session_verdicts_not_rendered`
- `tests/gcp/test_premarket_brief.py::test_legacy_nan_recap_metrics_are_ignored`
- `tests/gcp/test_premarket_brief.py::test_legacy_recap_unavailable_warning_not_rendered`
- `tests/gcp/test_premarket_brief.py::test_mondays_brief_has_no_recap_lookup`
- `tests/gcp/test_premarket_brief.py::test_non_ew_brief_contract_after_retirement`
- `tests/gcp/test_premarket_brief.py::test_non_ew_embed_golden_after_retirement`
- `tests/gcp/test_premarket_brief.py::test_quiet_supported_day_preserves_complete_content`
- `tests/gcp/test_premarket_brief.py::test_recap_query_is_never_attempted`
- `tests/gcp/test_premarket_brief.py::test_retired_columns_absent_from_loader_query`
- `tests/gcp/test_premarket_brief.py::test_retired_recap_database_error_cannot_reach_embed`
- `tests/gcp/test_premarket_brief.py::test_retired_recap_reservation_is_absent`
- `tests/gcp/test_premarket_brief.py::test_retired_sources_excluded_by_real_brief_sql[False-0]`
- `tests/gcp/test_premarket_brief.py::test_retired_sources_excluded_by_real_brief_sql[False-1]`
- `tests/gcp/test_premarket_brief.py::test_retired_sources_excluded_by_real_brief_sql[True-0]`
- `tests/gcp/test_premarket_brief.py::test_retired_sources_excluded_by_real_prior_amc_sql`
- `tests/gcp/test_premarket_brief.py::test_three_date_sources_mixed_ew_stay_tier2`
- `tests/gcp/test_premarket_brief.py::test_yahoo_mixed_ew_stays_tier4`

### Current-base discriminating controls and capacity

The ten selected retirement/golden controls run against actual base source with only candidate tests installed: 8 fail and 2 pass (2.59s). Against candidate source all 10 pass (0.51s). Baseline failures cover both SQL boundaries, daily legacy rendering and all three real caller paths; the weekly legacy case and non-EW golden control already pass and are not claimed as discriminating controls. The mixed NULL/string baseline error is retained in that failure log; candidate ordering leaves retained strings unchanged.

Measured seven actual-query/caller controls: 7 pass (0.71s pytest; 2.571s including child startup), peak child RSS 113252 KiB. Each loader retains one SQL statement; weekday generation executes the two loaders and Sunday executes only the weekly loader. Tests assert these counts and predicate-removed maxima 9/30000 versus retained 5/20000. Fixtures are finite in-memory SQLite rows; no provider, socket, webhook or live database is used. This is local qualification, not production latency or billed savings. Earlier invocation of /usr/bin/time was unavailable; the successful measurement uses Python monotonic timing and resource.getrusage(RUSAGE_CHILDREN).

### First implementation review and correction

One complete local review of `8e5b36e3f7d59832fa0b8e9ec6b0c7189f673232` finished 2026-11-12 09:29:01 UTC. It found one P2 coverage defect: the initial busy fixture was capped at ten BMO rows and rendered only 656 characters, so the bound assertions were vacuous. No other consequential finding or runtime defect was reported. This is review round 1; all earlier spec reviews remain historical and no allowance resets.

The single correction batch adds a supported-source uncapped watchlist to that fixture, preserves every node and legacy-absence assertion, and asserts the exact 4090-character limit for the three large-output cases. Removing only the production final description slice in an isolated temporary copy now produces 3 failures and 1 quiet-case pass (1.07s); unchanged production with the strengthened fixture produces 4 passes (0.74s). No production code changed in this correction. The temporary mutation was restored. Final current-head external review remains required.

Fixture JSON envelopes measured with sorted-key serialization and date strings: daily 13 calendar rows / 6587 bytes; prior-AMC 5 rows / 2563 bytes. The measured 7-case resource receipt above precedes only this busy-fixture correction; its actual query/caller inputs remain byte-identical.


## November 13 confirmed review regressions

Current main `61bbd17e` retains the same six-suite base test bytes as `75493a47`; the earlier node inventory remains historical. Hosted CODE on owner-reconciled `42453e04` found two P2 regressions: empty Track A hid retained daily sections, and the final character slice could truncate a financial value. Five new cases fail before correction: three section-only cases, an actual five-quarter Track B loader case, and an oversized financial-row case. The correction retains daily watchlist/low-conviction/prior-AMC content and complete lines with an omission notice under the unchanged 4090-character bound. Weekly and quiet golden outputs remain unchanged.

The six scoped suites now pass 287 cases (26.80 seconds, five existing pandas warnings). All original 282 candidate nodes remain; the five added nodes are `test_non_ew_section_survives_empty_track_a` (three parameters), `test_actual_track_b_only_loader_still_renders`, and `test_long_non_ew_output_keeps_complete_financial_rows`. The three existing large-output cases preserve their absence and content assertions, replace exact character saturation with the maximum bound, and add whole-line/notice assertions. This supersedes the earlier claim that whole-line protection was purely an EW reservation concern: the review demonstrated an independent non-EW financial-value obligation. No numeric helper, source predicate, shared calendar, calibration behavior or finite-values obligation changes.
