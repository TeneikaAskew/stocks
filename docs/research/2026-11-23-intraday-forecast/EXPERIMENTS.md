# Experiment index

The stages follow the questions in the study. Each exhibit opens directly in the PR. Source paths below are relative to the companion’s studies directory. The index preserves earlier results even when a later replay changed the conclusion or used a different cohort.

| Stage | Question and scope | Results | Source |
|---|---|---|---|
| 1. Issued brief against minute prices | Issued ladders, original signals, skipped levels, target-before-stop and recrosses. | [Evidence](evidence/01-paired_targets.csv) | `brief_evaluation/replay.py` |
| 2. Six-month price and clock reconstruction | Separate the original snapshot subset from reconstructed maps, bias and historical daily baselines. | [Evidence](evidence/02-directional_horizons.csv) | `intraday_study/rebuild/reconstruct.py` |
| 3. Both sides, candle lengths and ATR spacing | Opposite-side trips, reversal confirmation at different clocks and 0/0.10/0.15/0.25 ATR spacing. | [Evidence](evidence/03-late_0920_target_close_summary.csv) | `intraday_followup/reversals/reversals.py` |
| 4. 09:20 nearest level versus premarket trigger | Same-date trigger selection, missed triggers, first contact, horizon and time to confirmation. | [Evidence](evidence/04-horizons.csv) | `trigger0920/analysis.py` |
| 5. Break versus retest and gap-day policies | Opening impulse versus late retest, structural versus ATR guides and gap stratification. | [Evidence](evidence/05-time_groups.csv) | `hold_retest0920/experiment.py` |
| 6. Direction, probabilities, confluence and published research | Forecast upper, lower or neither; compare geometry, individual indicators, controls and calibration. | [Evidence](evidence/06-scores.csv) | `path_forecast0920/fit.py` |
| 7. January–August calibration, September–November evaluation | Maps, native strategy replay, failed calls, preserved issued alerts and independent feature/parity audit. | [Evidence](evidence/07-path_scores.csv) | `fixed_holdout/maps/build_maps.py` |
| 8. Brief editions, opening update, notifications and Insights | 09:15/09:20/09:25 comparison, range, 09:35 update, local Postgres journey, four runtime draft lineages. | [Evidence](evidence/08-monitor-holdout.json) | `brief_signal_followup/delivery/verification/grade_opening.py` |
| 9. SPY opening range and intraday reversals | November 17–18 opening-range moves, early countertrend entries and later continuation attempts. | [Evidence](evidence/09-case_trade_ledger.csv) | `spy_orb_nov17_18/cases.py` |
| 10. SPY directional dots and strength at target | Pine indicator rows, all-day and regular-session sensitivities, full-T1 versus holding a runner. | [Evidence](evidence/10-at_target_summary.csv) | `spy_pine_dot_study/research.py` |
| 11. Ticker-specific IWM, QQQ and SPY profiles | Time-aligned signals, indicator scores, thresholds trained per ticker and paired forecast quality. | [Evidence](evidence/11-forecast-scores.csv) | `ticker_level_replay/replay.py` |
| 12. Four-day entry and exit charts per ticker | Visual entry, stop, target, baseline and proposal comparisons across individual sessions. | [Evidence](evidence/12-ETF-trades-and-exits.csv) | `four_session_atlas/atlas.py` |
| 13. Entry selection, stop wick, re-entry and runner experiments | Compare original stops, close confirmation, tolerance, confluence and changes in foregone entries. | [Evidence](evidence/13-Stop-policy-tests.csv) | `signal_attribution/stops.py` |
| 14. Three-target allocation and holding rules | Separately evaluate target touches and booked exits, original stops and partial trade management. | [Evidence](evidence/14-target-results.csv) | `target_confluence/replay_targets.py` |
| 15. IWM-specific attribution and cross-ticker ladders | Evaluate retests, spacing, full T1, thirds, protection and dependence on the best day. | [Evidence](evidence/15-profile-comparisons.csv) | `iwm_ladder/run_profiles.py` |
| 16. Distance forecast versus amount collected | Same session scored as target credit, independent full exits or a managed position. | [Evidence](evidence/16-comparison.csv) | `ladder_explanation/compare_scores.py` |
| 17. Three independent full exits from one entry | Initial stop fixed; value T1/T2/T3 separately. Include misses, score distribution and skipped opportunities. | [Evidence](evidence/17-four-approach-comparison.csv) | `fourth_approach/fourth.py` |
| 18. Notification quota, repeated crossings, relative volume and peer strength | Compare native attempts, eligible distinct episodes and uncapped candidates; 2m/5m breaks and replay versus original records. | [Evidence](evidence/18-flag-quality.csv) | `alert_workspace/policies/native_policies.py` |
| 19. IWM Friday full-session audit | Join an actual issued brief and five logged production alerts to frozen early rules and the full 390-minute tape. | [Evidence](evidence/19-independent-entries.csv) | `friday_iwm_nov20/replay_friday.py` |
