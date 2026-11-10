# #1766 calibrated evidence as of 2026-11-06 (run 84421818-74f3-40bd-929e-a9a9a7e8eed8)

## SPY

| key | calibrated | status | sample | input | #1753 |
|---|---|---|---|---|---|
| trigger_window_long_atr | 1.9894 | ok | 750 | 2023-11-09 to 2026-11-05 | 3.0 |
| trigger_window_short_atr | 2.7710 | ok | 750 | 2023-11-09 to 2026-11-05 | 3.0 |
| pm_spike_atr | 0.9265 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.5 |
| pm_stale_print_atr | 0.0409 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.1 |
| level_cluster_atr | 0.0515 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.15 |
| entry_buffer_aggressive_lo_atr | 0.0000 | ok | 740 | 2023-11-09 to 2026-11-05 | 0.0 |
| entry_buffer_aggressive_hi_atr | 1.1245 | ok | 740 | 2023-11-09 to 2026-11-05 | 0.5 |
| entry_buffer_neutral_lo_atr | 0.0000 | ok | 740 | 2023-11-09 to 2026-11-05 | 0.0 |
| entry_buffer_neutral_hi_atr | 0.4179 | ok | 740 | 2023-11-09 to 2026-11-05 | 0.25 |
| entry_buffer_conservative_lo_atr | 0.0330 | ok | 740 | 2023-11-09 to 2026-11-05 | 0.1 |
| entry_buffer_conservative_hi_atr | 0.8234 | ok | 740 | 2023-11-09 to 2026-11-05 | 0.4 |
| stop_aggressive_atr |  | insufficient_history | 136 | 2024-07-25 to 2026-11-05 | 2.0 |
| stop_neutral_atr | 0.3299 | ok | 164 | 2024-07-25 to 2026-11-05 | 1.0 |
| stop_conservative_atr |  | insufficient_history | 147 | 2024-07-25 to 2026-11-05 | 0.7 |
| min_stop_atr | 0.1780 | ok | 164 | 2024-07-25 to 2026-11-05 | 0.5 |
| target_aggressive_1_r |  | insufficient_history | 136 | None to None | 2.0 |
| target_aggressive_2_r |  | insufficient_history | 136 | None to None | 3.5 |
| target_aggressive_3_r |  | insufficient_history | 136 | None to None | 5.0 |
| target_neutral_1_r | 0.4532 | ok | 331 | 2023-11-14 to 2026-11-05 | 1.0 |
| target_neutral_2_r | 0.7076 | ok | 331 | 2023-11-14 to 2026-11-05 | 2.0 |
| target_neutral_3_r | 1.1824 | ok | 331 | 2023-11-14 to 2026-11-05 | 3.0 |
| target_conservative_1_r |  | insufficient_history | 147 | None to None | 1.0 |
| target_conservative_2_r |  | insufficient_history | 147 | None to None | 1.75 |

long window 1.989 x ATR: share of sessions whose excursion passed it, per year (and at the #1753 3.0):

| year | sessions | passed | share | share at 3.0 |
|---|---|---|---|---|
| 2016 | 169 | 2 | 0.012 | 0.000 |
| 2017 | 251 | 4 | 0.016 | 0.000 |
| 2018 | 251 | 1 | 0.004 | 0.000 |
| 2019 | 252 | 0 | 0.000 | 0.000 |
| 2020 | 253 | 4 | 0.016 | 0.000 |
| 2021 | 252 | 1 | 0.004 | 0.000 |
| 2022 | 251 | 1 | 0.004 | 0.000 |
| 2023 | 250 | 0 | 0.000 | 0.000 |
| 2024 | 252 | 2 | 0.008 | 0.000 |
| 2025 | 250 | 3 | 0.012 | 0.004 |
| 2026 | 213 | 2 | 0.009 | 0.000 |

short window 2.771 x ATR: share of sessions whose excursion passed it, per year (and at the #1753 3.0):

| year | sessions | passed | share | share at 3.0 |
|---|---|---|---|---|
| 2016 | 169 | 2 | 0.012 | 0.012 |
| 2017 | 251 | 3 | 0.012 | 0.004 |
| 2018 | 251 | 4 | 0.016 | 0.008 |
| 2019 | 252 | 2 | 0.008 | 0.004 |
| 2020 | 253 | 6 | 0.024 | 0.016 |
| 2021 | 252 | 3 | 0.012 | 0.008 |
| 2022 | 251 | 1 | 0.004 | 0.000 |
| 2023 | 250 | 0 | 0.000 | 0.000 |
| 2024 | 252 | 2 | 0.008 | 0.004 |
| 2025 | 250 | 3 | 0.012 | 0.004 |
| 2026 | 213 | 2 | 0.009 | 0.009 |

premarket drops, 20 sessions through 2026-11-06, calibrated (stale 0.0409, spike 0.9265 x ATR): 288 prints

| session | time ET | field | price | rule |
|---|---|---|---|---|
| 2026-10-12 | 08:12 | low | 778.5700 | stale_prior_close |
| 2026-10-13 | 07:02 | open | 778.1000 | stale_prior_close |
| 2026-10-13 | 07:36 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 07:38 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 07:41 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 07:41 | open | 778.1000 | stale_prior_close |
| 2026-10-13 | 07:42 | close | 778.1000 | stale_prior_close |
| 2026-10-13 | 07:42 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 07:43 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 08:11 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 08:47 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 08:51 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 08:53 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 08:55 | high | 778.1000 | stale_prior_close |
| 2026-10-13 | 08:57 | high | 778.1000 | stale_prior_close |
| 2026-10-14 | 04:00 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:01 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:35 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:38 | close | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:38 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:39 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:39 | open | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:40 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:41 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:41 | open | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:00 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:07 | close | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:07 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:08 | close | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:08 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:47 | high | 778.0100 | stale_prior_close |
| 2026-10-15 | 04:00 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:00 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:00 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:01 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:35 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:36 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:36 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:37 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:37 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:38 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:38 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:39 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:40 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:08 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:11 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:16 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:47 | high | 769.6000 | stale_prior_close |
| 2026-10-16 | 04:00 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:00 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:01 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:14 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:35 | close | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:35 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:37 | close | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:37 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:38 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:38 | open | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:07 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:08 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:08 | open | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:47 | low | 771.7900 | stale_prior_close |
| 2026-10-19 | 07:00 | close | 763.2489 | stale_prior_close |
| 2026-10-19 | 07:00 | low | 763.2489 | stale_prior_close |
| 2026-10-19 | 07:02 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:35 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:36 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:37 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:37 | open | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:38 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 08:20 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 08:47 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 08:57 | low | 763.2500 | stale_prior_close |
| 2026-10-20 | 07:01 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:02 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:35 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:36 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:36 | open | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:37 | close | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:37 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:38 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:38 | open | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:41 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:42 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:42 | open | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:03 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:04 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:07 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:10 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:47 | high | 766.4800 | stale_prior_close |
| 2026-10-21 | 04:00 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:00 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:01 | low | 769.0454 | stale_prior_close |
| 2026-10-21 | 07:35 | close | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:35 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:36 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:37 | close | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:37 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:38 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:38 | open | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:39 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:40 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:07 | close | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:07 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:08 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:08 | open | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:47 | low | 769.0500 | stale_prior_close |
| 2026-10-22 | 04:00 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:01 | close | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:01 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:02 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:35 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:37 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:38 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:39 | close | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:39 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 08:05 | high | 774.0832 | spike |
| 2026-10-22 | 08:12 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 08:13 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 08:47 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 09:22 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 09:23 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 09:29 | high | 773.0900 | stale_prior_close |
| 2026-10-23 | 07:35 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:36 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:36 | open | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:37 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:38 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:39 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:39 | open | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:40 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 08:05 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 08:08 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 08:47 | high | 763.9600 | stale_prior_close |
| 2026-10-26 | 07:00 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:35 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:36 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:37 | close | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:37 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:38 | close | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:38 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:39 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:40 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 08:20 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 08:39 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 08:47 | low | 759.9700 | stale_prior_close |
| 2026-10-27 | 07:00 | close | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:00 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:01 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:02 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:02 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:35 | close | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:35 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:36 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:36 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:37 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:38 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:38 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:39 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:04 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:05 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:16 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:17 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:18 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:19 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:20 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:21 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:22 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:23 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:47 | low | 765.3700 | stale_prior_close |
| 2026-10-28 | 04:00 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 04:02 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:01 | low | 769.6563 | stale_prior_close |
| 2026-10-28 | 07:01 | open | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:02 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:35 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:36 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:37 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:38 | close | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:38 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:39 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:40 | close | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:40 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:41 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 08:00 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 08:05 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 08:47 | low | 769.6600 | stale_prior_close |
| 2026-10-29 | 04:00 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:00 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:01 | high | 772.3136 | stale_prior_close |
| 2026-10-29 | 07:35 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:36 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:37 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:38 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:39 | close | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:39 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:40 | close | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:40 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:41 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:05 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:08 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:09 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:11 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:11 | open | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:13 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:16 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:47 | high | 772.3100 | stale_prior_close |
| 2026-10-30 | 04:00 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:00 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:01 | high | 769.3633 | stale_prior_close |
| 2026-10-30 | 07:02 | high | 769.3642 | stale_prior_close |
| 2026-10-30 | 07:35 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:37 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:38 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:38 | open | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:59 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:00 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:05 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:39 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:47 | high | 769.3600 | stale_prior_close |
| 2026-11-02 | 07:00 | close | 755.7243 | stale_prior_close |
| 2026-11-02 | 07:01 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:35 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:37 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:38 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:39 | close | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:39 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:40 | close | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:40 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:15 | close | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:15 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:24 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:32 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:47 | low | 755.7200 | stale_prior_close |
| 2026-11-03 | 04:00 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:00 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:01 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:02 | close | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:02 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:03 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:05 | high | 760.6241 | spike |
| 2026-11-03 | 08:43 | low | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:43 | open | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:44 | low | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:45 | low | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:47 | low | 752.1000 | stale_prior_close |
| 2026-11-04 | 04:00 | low | 748.0000 | spike |
| 2026-11-04 | 05:22 | low | 751.9500 | spike |
| 2026-11-04 | 07:00 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:02 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:03 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:35 | close | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:35 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:36 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:36 | open | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:37 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:37 | open | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:38 | close | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:38 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:39 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:05 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:26 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:27 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:47 | low | 754.3500 | stale_prior_close |
| 2026-11-05 | 04:00 | high | 766.8100 | stale_prior_close |
| 2026-11-05 | 04:03 | high | 766.8100 | stale_prior_close |
| 2026-11-05 | 07:01 | low | 766.8051 | stale_prior_close |
| 2026-11-05 | 08:17 | low | 766.8100 | stale_prior_close |
| 2026-11-05 | 08:19 | low | 766.8100 | stale_prior_close |
| 2026-11-05 | 08:20 | low | 766.8100 | stale_prior_close |
| 2026-11-05 | 08:47 | low | 766.8100 | stale_prior_close |
| 2026-11-06 | 04:25 | close | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:00 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:01 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:02 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:35 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:37 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:38 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:39 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:40 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:41 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:41 | open | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:05 | high | 765.5267 | spike |
| 2026-11-06 | 08:05 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:09 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:10 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:39 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:47 | low | 733.0000 | stale_prior_close |

premarket drops, 20 sessions through 2026-11-06, #1753 (stale 0.1000, spike 0.5000 x ATR): 252 prints

| session | time ET | field | price | rule |
|---|---|---|---|---|
| 2026-10-13 | 08:47 | high | 778.1000 | stale_prior_close |
| 2026-10-14 | 04:00 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:01 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:35 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:38 | close | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:38 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:39 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:39 | open | 778.0100 | stale_prior_close |
| 2026-10-14 | 07:40 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:00 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:07 | close | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:07 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:08 | close | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:08 | low | 778.0100 | stale_prior_close |
| 2026-10-14 | 08:47 | high | 778.0100 | stale_prior_close |
| 2026-10-15 | 04:00 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:00 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:00 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:01 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:35 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:36 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:36 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:37 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:37 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:38 | close | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:38 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:39 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 07:40 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:05 | high | 770.6750 | spike |
| 2026-10-15 | 08:08 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:11 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:16 | high | 769.6000 | stale_prior_close |
| 2026-10-15 | 08:47 | high | 769.6000 | stale_prior_close |
| 2026-10-16 | 04:00 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:00 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:01 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 07:14 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:05 | low | 767.2361 | spike |
| 2026-10-16 | 08:07 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:08 | low | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:08 | open | 771.7900 | stale_prior_close |
| 2026-10-16 | 08:47 | low | 771.7900 | stale_prior_close |
| 2026-10-19 | 07:00 | close | 763.2489 | stale_prior_close |
| 2026-10-19 | 07:00 | low | 763.2489 | stale_prior_close |
| 2026-10-19 | 07:01 | low | 763.5714 | spike |
| 2026-10-19 | 07:02 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:35 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:36 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:37 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:37 | open | 763.2500 | stale_prior_close |
| 2026-10-19 | 07:38 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 08:05 | high | 773.2000 | spike |
| 2026-10-19 | 08:05 | low | 762.7850 | spike |
| 2026-10-19 | 08:20 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 08:47 | low | 763.2500 | stale_prior_close |
| 2026-10-19 | 08:57 | low | 763.2500 | stale_prior_close |
| 2026-10-20 | 07:01 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:02 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:35 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 07:41 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:03 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:04 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:05 | high | 768.5509 | spike |
| 2026-10-20 | 08:07 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:10 | high | 766.4800 | stale_prior_close |
| 2026-10-20 | 08:47 | high | 766.4800 | stale_prior_close |
| 2026-10-21 | 04:00 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:00 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:01 | low | 769.0454 | stale_prior_close |
| 2026-10-21 | 07:35 | close | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:35 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:36 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:37 | close | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:37 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:38 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:38 | open | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:39 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 07:40 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:07 | close | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:07 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:08 | low | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:08 | open | 769.0500 | stale_prior_close |
| 2026-10-21 | 08:47 | low | 769.0500 | stale_prior_close |
| 2026-10-22 | 04:00 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:01 | close | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:01 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:02 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:35 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:37 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:38 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:39 | close | 773.0900 | stale_prior_close |
| 2026-10-22 | 07:39 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 08:05 | high | 774.0832 | spike |
| 2026-10-22 | 08:12 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 08:13 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 08:47 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 09:22 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 09:23 | high | 773.0900 | stale_prior_close |
| 2026-10-22 | 09:29 | high | 773.0900 | stale_prior_close |
| 2026-10-23 | 07:35 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:36 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:36 | open | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:37 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:38 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:39 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:39 | open | 763.9600 | stale_prior_close |
| 2026-10-23 | 07:40 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 08:05 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 08:08 | high | 763.9600 | stale_prior_close |
| 2026-10-23 | 08:47 | high | 763.9600 | stale_prior_close |
| 2026-10-26 | 07:35 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:36 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:39 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 07:40 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 08:20 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 08:39 | low | 759.9700 | stale_prior_close |
| 2026-10-26 | 08:47 | low | 759.9700 | stale_prior_close |
| 2026-10-27 | 07:00 | close | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:00 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:01 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:02 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:02 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:35 | close | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:35 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:36 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:36 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:37 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:38 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:38 | open | 765.3700 | stale_prior_close |
| 2026-10-27 | 07:39 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:04 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:05 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:16 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:17 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:18 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:19 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:20 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:21 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:22 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:23 | low | 765.3700 | stale_prior_close |
| 2026-10-27 | 08:47 | low | 765.3700 | stale_prior_close |
| 2026-10-28 | 04:00 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:02 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:35 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:36 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:37 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:38 | close | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:38 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:39 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:40 | close | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:40 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 07:41 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 08:00 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 08:05 | low | 769.6600 | stale_prior_close |
| 2026-10-28 | 08:47 | low | 769.6600 | stale_prior_close |
| 2026-10-29 | 04:00 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:00 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:01 | high | 772.3136 | stale_prior_close |
| 2026-10-29 | 07:35 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:36 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:37 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:38 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:39 | close | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:39 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:40 | close | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:40 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 07:41 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:05 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:08 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:09 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:11 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:11 | open | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:13 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:16 | high | 772.3100 | stale_prior_close |
| 2026-10-29 | 08:47 | high | 772.3100 | stale_prior_close |
| 2026-10-30 | 04:00 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:00 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:01 | high | 769.3633 | stale_prior_close |
| 2026-10-30 | 07:02 | high | 769.3642 | stale_prior_close |
| 2026-10-30 | 07:35 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:37 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:38 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:38 | open | 769.3600 | stale_prior_close |
| 2026-10-30 | 07:59 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:00 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:05 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:39 | high | 769.3600 | stale_prior_close |
| 2026-10-30 | 08:47 | high | 769.3600 | stale_prior_close |
| 2026-11-02 | 07:00 | close | 755.7243 | stale_prior_close |
| 2026-11-02 | 07:01 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:35 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:37 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:38 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:39 | close | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:39 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:40 | close | 755.7200 | stale_prior_close |
| 2026-11-02 | 07:40 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:15 | close | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:15 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:24 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:32 | low | 755.7200 | stale_prior_close |
| 2026-11-02 | 08:47 | low | 755.7200 | stale_prior_close |
| 2026-11-03 | 04:00 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:00 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:01 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:02 | close | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:02 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 07:03 | high | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:05 | high | 760.6241 | spike |
| 2026-11-03 | 08:43 | low | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:43 | open | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:44 | low | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:45 | low | 752.1000 | stale_prior_close |
| 2026-11-03 | 08:47 | low | 752.1000 | stale_prior_close |
| 2026-11-04 | 04:00 | low | 748.0000 | spike |
| 2026-11-04 | 04:07 | low | 748.9200 | spike |
| 2026-11-04 | 05:22 | low | 751.9500 | spike |
| 2026-11-04 | 07:00 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:02 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:03 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:35 | close | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:35 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:36 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:36 | open | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:37 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:37 | open | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:38 | close | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:38 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 07:39 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:05 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:26 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:27 | low | 754.3500 | stale_prior_close |
| 2026-11-04 | 08:47 | low | 754.3500 | stale_prior_close |
| 2026-11-05 | 04:03 | high | 766.8100 | stale_prior_close |
| 2026-11-05 | 07:01 | low | 766.8051 | stale_prior_close |
| 2026-11-05 | 08:47 | low | 766.8100 | stale_prior_close |
| 2026-11-06 | 04:25 | close | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:00 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:01 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:02 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:35 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:37 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:38 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:39 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:40 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:41 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 07:41 | open | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:05 | high | 765.5267 | spike |
| 2026-11-06 | 08:09 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:10 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:39 | low | 733.0000 | stale_prior_close |
| 2026-11-06 | 08:47 | low | 733.0000 | stale_prior_close |

breaks per side and year (sessions with one-minute bars):

| side | year | breaks | held |
|---|---|---|---|
| long | 2022 | 1 | 1 |
| long | 2024 | 6 | 6 |
| long | 2025 | 79 | 58 |
| long | 2026 | 110 | 77 |
| short | 2017 | 165 | 31 |
| short | 2018 | 241 | 65 |
| short | 2019 | 243 | 63 |
| short | 2020 | 244 | 67 |
| short | 2021 | 243 | 62 |
| short | 2022 | 242 | 96 |
| short | 2023 | 240 | 72 |
| short | 2024 | 238 | 60 |
| short | 2025 | 148 | 50 |
| short | 2026 | 126 | 62 |

## QQQ

| key | calibrated | status | sample | input | #1753 |
|---|---|---|---|---|---|
| trigger_window_long_atr | 1.8872 | ok | 750 | 2023-11-09 to 2026-11-05 | 3.0 |
| trigger_window_short_atr | 2.4720 | ok | 750 | 2023-11-09 to 2026-11-05 | 3.0 |
| pm_spike_atr | 1.0716 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.5 |
| pm_stale_print_atr | 0.0421 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.1 |
| level_cluster_atr | 0.0488 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.15 |
| entry_buffer_aggressive_lo_atr | 0.0000 | ok | 777 | 2023-11-09 to 2026-11-05 | 0.0 |
| entry_buffer_aggressive_hi_atr | 0.4796 | ok | 777 | 2023-11-09 to 2026-11-05 | 0.5 |
| entry_buffer_neutral_lo_atr | 0.0000 | ok | 777 | 2023-11-09 to 2026-11-05 | 0.0 |
| entry_buffer_neutral_hi_atr | 0.1281 | ok | 777 | 2023-11-09 to 2026-11-05 | 0.25 |
| entry_buffer_conservative_lo_atr | 0.0139 | ok | 777 | 2023-11-09 to 2026-11-05 | 0.1 |
| entry_buffer_conservative_hi_atr | 0.3370 | ok | 777 | 2023-11-09 to 2026-11-05 | 0.4 |
| stop_aggressive_atr | 0.5481 | ok | 283 | 2023-11-09 to 2026-11-04 | 2.0 |
| stop_neutral_atr | 0.3221 | ok | 283 | 2023-11-09 to 2026-11-04 | 1.0 |
| stop_conservative_atr | 0.2046 | ok | 284 | 2023-11-09 to 2026-11-04 | 0.7 |
| min_stop_atr | 0.1547 | ok | 283 | 2023-11-09 to 2026-11-04 | 0.5 |
| target_aggressive_1_r | 0.5929 | ok | 477 | 2023-11-09 to 2026-11-04 | 2.0 |
| target_aggressive_2_r | 0.8854 | ok | 477 | 2023-11-09 to 2026-11-04 | 3.5 |
| target_aggressive_3_r | 1.2252 | ok | 477 | 2023-11-09 to 2026-11-04 | 5.0 |
| target_neutral_1_r | 0.5086 | ok | 552 | 2023-11-09 to 2026-11-04 | 1.0 |
| target_neutral_2_r | 0.8245 | ok | 552 | 2023-11-09 to 2026-11-04 | 2.0 |
| target_neutral_3_r | 1.2147 | ok | 552 | 2023-11-09 to 2026-11-04 | 3.0 |
| target_conservative_1_r | 0.5061 | ok | 502 | 2023-11-09 to 2026-11-04 | 1.0 |
| target_conservative_2_r | 0.9233 | ok | 502 | 2023-11-09 to 2026-11-04 | 1.75 |

long window 1.887 x ATR: share of sessions whose excursion passed it, per year (and at the #1753 3.0):

| year | sessions | passed | share | share at 3.0 |
|---|---|---|---|---|
| 2016 | 169 | 3 | 0.018 | 0.006 |
| 2017 | 251 | 2 | 0.008 | 0.004 |
| 2018 | 251 | 4 | 0.016 | 0.000 |
| 2019 | 252 | 0 | 0.000 | 0.000 |
| 2020 | 253 | 5 | 0.020 | 0.000 |
| 2021 | 252 | 1 | 0.004 | 0.000 |
| 2022 | 251 | 3 | 0.012 | 0.000 |
| 2023 | 250 | 3 | 0.012 | 0.000 |
| 2024 | 252 | 3 | 0.012 | 0.000 |
| 2025 | 250 | 1 | 0.004 | 0.004 |
| 2026 | 213 | 3 | 0.014 | 0.000 |

short window 2.472 x ATR: share of sessions whose excursion passed it, per year (and at the #1753 3.0):

| year | sessions | passed | share | share at 3.0 |
|---|---|---|---|---|
| 2016 | 169 | 3 | 0.018 | 0.012 |
| 2017 | 251 | 4 | 0.016 | 0.012 |
| 2018 | 251 | 5 | 0.020 | 0.008 |
| 2019 | 252 | 3 | 0.012 | 0.004 |
| 2020 | 253 | 8 | 0.032 | 0.008 |
| 2021 | 252 | 1 | 0.004 | 0.004 |
| 2022 | 251 | 1 | 0.004 | 0.000 |
| 2023 | 250 | 0 | 0.000 | 0.000 |
| 2024 | 252 | 3 | 0.012 | 0.004 |
| 2025 | 250 | 1 | 0.004 | 0.004 |
| 2026 | 213 | 3 | 0.014 | 0.009 |

premarket drops, 20 sessions through 2026-11-06, calibrated (stale 0.0421, spike 1.0716 x ATR): 312 prints

| session | time ET | field | price | rule |
|---|---|---|---|---|
| 2026-10-12 | 08:12 | high | 751.2700 | stale_prior_close |
| 2026-10-12 | 08:47 | high | 751.2700 | stale_prior_close |
| 2026-10-12 | 08:47 | open | 751.2700 | stale_prior_close |
| 2026-10-13 | 04:00 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:35 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:35 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:36 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:36 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:37 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:37 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:38 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:38 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:39 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:39 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:40 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:40 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:41 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:41 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:42 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:42 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:43 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:43 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:44 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:44 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:11 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:12 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:12 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:47 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:50 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:53 | high | 746.0400 | stale_prior_close |
| 2026-10-14 | 07:01 | high | 743.5700 | stale_prior_close |
| 2026-10-14 | 07:40 | high | 743.5700 | stale_prior_close |
| 2026-10-14 | 07:41 | high | 743.5700 | stale_prior_close |
| 2026-10-14 | 07:41 | open | 743.5700 | stale_prior_close |
| 2026-10-14 | 08:47 | high | 743.5700 | stale_prior_close |
| 2026-10-15 | 04:00 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:00 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:01 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:02 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:35 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:37 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:37 | open | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:38 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:39 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:39 | open | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:40 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:05 | high | 738.0550 | spike |
| 2026-10-15 | 08:07 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:08 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:09 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:09 | open | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:16 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:17 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:47 | high | 728.9500 | stale_prior_close |
| 2026-10-16 | 04:00 | low | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:00 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:01 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:35 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:37 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:38 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:38 | open | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:39 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 08:05 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 08:47 | high | 728.0000 | stale_prior_close |
| 2026-10-19 | 07:02 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:02 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:35 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:36 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:36 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:37 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:37 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:38 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:38 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:39 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 08:20 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 08:47 | low | 709.8000 | stale_prior_close |
| 2026-10-20 | 07:01 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:02 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:03 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:03 | open | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:35 | close | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:35 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:36 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:37 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:38 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:39 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:40 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:41 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:42 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:42 | open | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:01 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:02 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:03 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:04 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:06 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:07 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:09 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:47 | high | 718.3600 | stale_prior_close |
| 2026-10-21 | 04:00 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:00 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:35 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:36 | close | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:36 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:37 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:38 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:39 | close | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:39 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:40 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 08:07 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 08:08 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 08:47 | low | 717.6300 | stale_prior_close |
| 2026-10-22 | 04:00 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:01 | close | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:01 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:02 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:02 | open | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:35 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:36 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:37 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:38 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:39 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:39 | open | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:40 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:40 | open | 725.2000 | stale_prior_close |
| 2026-10-22 | 08:05 | high | 726.7050 | spike |
| 2026-10-22 | 08:12 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 08:13 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 08:47 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:21 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:22 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:23 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:24 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:25 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:26 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:27 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:28 | high | 725.2000 | stale_prior_close |
| 2026-10-23 | 07:01 | high | 704.4700 | stale_prior_close |
| 2026-10-23 | 07:02 | high | 704.4697 | stale_prior_close |
| 2026-10-23 | 07:39 | high | 704.4700 | stale_prior_close |
| 2026-10-23 | 07:40 | high | 704.4700 | stale_prior_close |
| 2026-10-23 | 07:41 | high | 704.4700 | stale_prior_close |
| 2026-10-23 | 08:08 | high | 704.4700 | stale_prior_close |
| 2026-10-23 | 08:47 | high | 704.4700 | stale_prior_close |
| 2026-10-26 | 07:01 | high | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:35 | close | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:35 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:36 | close | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:36 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:38 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:39 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:40 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 08:20 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 08:47 | low | 704.4000 | stale_prior_close |
| 2026-10-27 | 07:00 | close | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:00 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:01 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:02 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:35 | close | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:35 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:36 | close | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:36 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:37 | close | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:37 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:38 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:38 | open | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:04 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:15 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:16 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:17 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:18 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:19 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:20 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:21 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:22 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:22 | open | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:23 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:47 | low | 712.2000 | stale_prior_close |
| 2026-10-28 | 04:00 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:01 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:02 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:02 | open | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:35 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:36 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:37 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:38 | close | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:38 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:39 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:40 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:41 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:42 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:43 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:44 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 08:00 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 08:47 | low | 721.2500 | stale_prior_close |
| 2026-10-29 | 04:00 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:00 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:01 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:01 | open | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:35 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:37 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:38 | close | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:38 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:39 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:40 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:41 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:05 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:08 | close | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:08 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:09 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:10 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:11 | close | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:11 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:12 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:14 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:15 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:18 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:20 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:47 | high | 725.6100 | stale_prior_close |
| 2026-10-30 | 04:00 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:00 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:01 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:03 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:35 | close | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:35 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:36 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:36 | open | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:37 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:38 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:39 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:59 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 08:00 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 08:05 | high | 715.6000 | spike |
| 2026-10-30 | 08:37 | low | 623.8900 | spike |
| 2026-10-30 | 08:47 | high | 715.3400 | stale_prior_close |
| 2026-11-02 | 07:01 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:02 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:35 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:36 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:37 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:38 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:39 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:40 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:41 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:15 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:16 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:16 | open | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:24 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:47 | low | 690.4900 | stale_prior_close |
| 2026-11-03 | 07:35 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 07:36 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 07:36 | open | 681.0900 | stale_prior_close |
| 2026-11-03 | 07:37 | close | 681.0900 | stale_prior_close |
| 2026-11-03 | 07:37 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 07:38 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:05 | high | 698.2300 | spike |
| 2026-11-03 | 08:05 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:40 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:44 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:46 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:47 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:48 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:49 | low | 681.0900 | stale_prior_close |
| 2026-11-04 | 07:00 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:01 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:02 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:03 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:35 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:36 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:36 | open | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:37 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:38 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:39 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:40 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 08:27 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 08:47 | low | 685.2800 | stale_prior_close |
| 2026-11-05 | 04:00 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:01 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:35 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:36 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:37 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:38 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:39 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:40 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:41 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:05 | high | 700.8000 | spike |
| 2026-11-05 | 08:15 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:17 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:18 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:19 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:21 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:22 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:24 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:47 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 09:05 | close | 691.9500 | stale_prior_close |
| 2026-11-05 | 09:05 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 09:06 | high | 691.9500 | stale_prior_close |
| 2026-11-06 | 04:00 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:00 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:01 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:35 | close | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:35 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:36 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:37 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:38 | close | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:38 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:39 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:40 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:05 | high | 683.5000 | spike |
| 2026-11-06 | 08:05 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:09 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:10 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:47 | low | 647.0500 | stale_prior_close |

premarket drops, 20 sessions through 2026-11-06, #1753 (stale 0.1000, spike 0.5000 x ATR): 299 prints

| session | time ET | field | price | rule |
|---|---|---|---|---|
| 2026-10-13 | 04:00 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:00 | high | 751.2700 | spike |
| 2026-10-13 | 07:01 | high | 751.2700 | spike |
| 2026-10-13 | 07:02 | high | 751.2700 | spike |
| 2026-10-13 | 07:35 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:35 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:36 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:36 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:37 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:37 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:38 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:38 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:39 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:39 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:40 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:40 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:41 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:41 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:42 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:42 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:43 | close | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:43 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:44 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 07:44 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:05 | high | 748.0700 | spike |
| 2026-10-13 | 08:11 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:12 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:12 | open | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:15 | high | 745.4810 | spike |
| 2026-10-13 | 08:47 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:50 | high | 746.0400 | stale_prior_close |
| 2026-10-13 | 08:53 | high | 746.0400 | stale_prior_close |
| 2026-10-14 | 07:01 | high | 743.5700 | stale_prior_close |
| 2026-10-14 | 08:47 | high | 743.5700 | stale_prior_close |
| 2026-10-15 | 04:00 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:00 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:01 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:02 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:35 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:37 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:37 | open | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:38 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:39 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:39 | open | 728.9500 | stale_prior_close |
| 2026-10-15 | 07:40 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:05 | high | 738.0550 | spike |
| 2026-10-15 | 08:07 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:08 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:09 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:09 | open | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:12 | high | 728.4040 | spike |
| 2026-10-15 | 08:16 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:17 | high | 728.9500 | stale_prior_close |
| 2026-10-15 | 08:47 | high | 728.9500 | stale_prior_close |
| 2026-10-16 | 04:00 | low | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:00 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:01 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:35 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:37 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 07:39 | high | 728.0000 | stale_prior_close |
| 2026-10-16 | 08:05 | low | 718.0400 | spike |
| 2026-10-16 | 08:47 | high | 728.0000 | stale_prior_close |
| 2026-10-19 | 07:02 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:02 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:35 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:36 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:36 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:37 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:37 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:38 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:38 | open | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:39 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 07:59 | low | 709.2680 | spike |
| 2026-10-19 | 08:05 | low | 710.2850 | spike |
| 2026-10-19 | 08:20 | low | 709.8000 | stale_prior_close |
| 2026-10-19 | 08:47 | low | 709.8000 | stale_prior_close |
| 2026-10-20 | 07:01 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:02 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:03 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:03 | open | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:35 | close | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:35 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:36 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:37 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:38 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:39 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:40 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:41 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:42 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 07:42 | open | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:01 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:02 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:03 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:04 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:05 | high | 721.3400 | spike |
| 2026-10-20 | 08:06 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:07 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:09 | high | 718.3600 | stale_prior_close |
| 2026-10-20 | 08:47 | high | 718.3600 | stale_prior_close |
| 2026-10-21 | 04:00 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:00 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:35 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:36 | close | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:36 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:37 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:38 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:39 | close | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:39 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 07:40 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 08:05 | low | 715.2200 | spike |
| 2026-10-21 | 08:07 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 08:08 | low | 717.6300 | stale_prior_close |
| 2026-10-21 | 08:47 | low | 717.6300 | stale_prior_close |
| 2026-10-22 | 04:00 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:01 | close | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:01 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:02 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:02 | open | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:35 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:36 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:37 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:38 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:39 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:39 | open | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:40 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 07:40 | open | 725.2000 | stale_prior_close |
| 2026-10-22 | 08:05 | high | 726.7050 | spike |
| 2026-10-22 | 08:09 | high | 724.6570 | spike |
| 2026-10-22 | 08:12 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 08:13 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 08:47 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:21 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:22 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:23 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:24 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:25 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:26 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:27 | high | 725.2000 | stale_prior_close |
| 2026-10-22 | 09:28 | high | 725.2000 | stale_prior_close |
| 2026-10-23 | 08:05 | high | 713.2703 | spike |
| 2026-10-23 | 08:47 | high | 704.4700 | stale_prior_close |
| 2026-10-26 | 07:38 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:39 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 07:40 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 08:20 | low | 704.4000 | stale_prior_close |
| 2026-10-26 | 08:47 | low | 704.4000 | stale_prior_close |
| 2026-10-27 | 07:01 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:02 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:35 | close | 712.2000 | stale_prior_close |
| 2026-10-27 | 07:35 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:04 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:05 | low | 706.2900 | spike |
| 2026-10-27 | 08:15 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:16 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:17 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:18 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:19 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:20 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:21 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:22 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:22 | open | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:23 | low | 712.2000 | stale_prior_close |
| 2026-10-27 | 08:47 | low | 712.2000 | stale_prior_close |
| 2026-10-28 | 04:00 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:01 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:02 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:02 | open | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:35 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:36 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:37 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:38 | close | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:38 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:39 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:40 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:41 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:42 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:43 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 07:44 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 08:00 | low | 721.2500 | stale_prior_close |
| 2026-10-28 | 08:47 | low | 721.2500 | stale_prior_close |
| 2026-10-29 | 04:00 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:00 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:01 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:01 | open | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:35 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:37 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:38 | close | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:38 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:39 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:40 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 07:41 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:05 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:08 | close | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:08 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:09 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:10 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:11 | close | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:11 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:12 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:14 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:15 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:16 | high | 726.1540 | spike |
| 2026-10-29 | 08:18 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:20 | high | 725.6100 | stale_prior_close |
| 2026-10-29 | 08:47 | high | 725.6100 | stale_prior_close |
| 2026-10-30 | 04:00 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:00 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:01 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:03 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:35 | close | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:35 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:36 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:36 | open | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:37 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:38 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:39 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 07:59 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 08:00 | high | 715.3400 | stale_prior_close |
| 2026-10-30 | 08:05 | high | 715.6000 | spike |
| 2026-10-30 | 08:37 | low | 623.8900 | spike |
| 2026-10-30 | 08:47 | high | 715.3400 | stale_prior_close |
| 2026-11-02 | 07:01 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:02 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:35 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:36 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:37 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:38 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:39 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:40 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 07:41 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:05 | low | 686.2850 | spike |
| 2026-11-02 | 08:15 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:16 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:16 | open | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:24 | low | 690.4900 | stale_prior_close |
| 2026-11-02 | 08:47 | low | 690.4900 | stale_prior_close |
| 2026-11-03 | 07:35 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 07:38 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:05 | high | 698.2300 | spike |
| 2026-11-03 | 08:05 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:40 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:44 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:46 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:47 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:48 | low | 681.0900 | stale_prior_close |
| 2026-11-03 | 08:49 | low | 681.0900 | stale_prior_close |
| 2026-11-04 | 04:00 | low | 676.2100 | spike |
| 2026-11-04 | 04:07 | low | 676.4100 | spike |
| 2026-11-04 | 07:00 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:01 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:02 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:03 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:35 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:36 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:36 | open | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:37 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:38 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:39 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 07:40 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 08:27 | low | 685.2800 | stale_prior_close |
| 2026-11-04 | 08:47 | low | 685.2800 | stale_prior_close |
| 2026-11-05 | 04:00 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:01 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:35 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:36 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:37 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:38 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:39 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:40 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 07:41 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:05 | high | 700.8000 | spike |
| 2026-11-05 | 08:15 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:17 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:18 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:19 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:21 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:22 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:24 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 08:47 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 09:05 | close | 691.9500 | stale_prior_close |
| 2026-11-05 | 09:05 | high | 691.9500 | stale_prior_close |
| 2026-11-05 | 09:06 | high | 691.9500 | stale_prior_close |
| 2026-11-06 | 04:00 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:00 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:01 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:35 | close | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:35 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:36 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:37 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:38 | close | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:38 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:39 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 07:40 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:05 | high | 683.5000 | spike |
| 2026-11-06 | 08:05 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:09 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:10 | low | 647.0500 | stale_prior_close |
| 2026-11-06 | 08:32 | low | 647.5350 | spike |
| 2026-11-06 | 08:47 | low | 647.0500 | stale_prior_close |

breaks per side and year (sessions with one-minute bars):

| side | year | breaks | held |
|---|---|---|---|
| long | 2020 | 11 | 11 |
| long | 2021 | 2 | 2 |
| long | 2022 | 24 | 24 |
| long | 2023 | 35 | 34 |
| long | 2024 | 67 | 59 |
| long | 2025 | 124 | 89 |
| long | 2026 | 115 | 79 |
| short | 2017 | 165 | 30 |
| short | 2018 | 241 | 66 |
| short | 2019 | 243 | 60 |
| short | 2020 | 239 | 56 |
| short | 2021 | 242 | 70 |
| short | 2022 | 233 | 94 |
| short | 2023 | 234 | 68 |
| short | 2024 | 200 | 59 |
| short | 2025 | 119 | 55 |
| short | 2026 | 116 | 68 |

## IWM

| key | calibrated | status | sample | input | #1753 |
|---|---|---|---|---|---|
| trigger_window_long_atr | 2.1942 | ok | 750 | 2023-11-09 to 2026-11-05 | 3.0 |
| trigger_window_short_atr | 2.2699 | ok | 750 | 2023-11-09 to 2026-11-05 | 3.0 |
| pm_spike_atr | 0.5365 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.5 |
| pm_stale_print_atr | 0.0408 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.1 |
| level_cluster_atr | 0.0517 | ok | 60 | 2026-08-13 to 2026-11-05 | 0.15 |
| entry_buffer_aggressive_lo_atr | 0.0000 | ok | 805 | 2023-11-09 to 2026-11-05 | 0.0 |
| entry_buffer_aggressive_hi_atr | 0.6837 | ok | 805 | 2023-11-09 to 2026-11-05 | 0.5 |
| entry_buffer_neutral_lo_atr | 0.0000 | ok | 805 | 2023-11-09 to 2026-11-05 | 0.0 |
| entry_buffer_neutral_hi_atr | 0.2867 | ok | 805 | 2023-11-09 to 2026-11-05 | 0.25 |
| entry_buffer_conservative_lo_atr | 0.0221 | ok | 805 | 2023-11-09 to 2026-11-05 | 0.1 |
| entry_buffer_conservative_hi_atr | 0.4918 | ok | 805 | 2023-11-09 to 2026-11-05 | 0.4 |
| stop_aggressive_atr | 0.5233 | ok | 234 | 2023-11-14 to 2026-11-05 | 2.0 |
| stop_neutral_atr | 0.3212 | ok | 250 | 2023-12-01 to 2026-11-05 | 1.0 |
| stop_conservative_atr | 0.2302 | ok | 244 | 2023-11-14 to 2026-11-05 | 0.7 |
| min_stop_atr | 0.1812 | ok | 250 | 2023-12-01 to 2026-11-05 | 0.5 |
| target_aggressive_1_r | 0.7287 | ok | 438 | 2023-11-13 to 2026-11-05 | 2.0 |
| target_aggressive_2_r | 0.9839 | ok | 438 | 2023-11-13 to 2026-11-05 | 3.5 |
| target_aggressive_3_r | 1.2665 | ok | 438 | 2023-11-13 to 2026-11-05 | 5.0 |
| target_neutral_1_r | 0.5304 | ok | 513 | 2023-11-15 to 2026-11-05 | 1.0 |
| target_neutral_2_r | 0.8822 | ok | 513 | 2023-11-15 to 2026-11-05 | 2.0 |
| target_neutral_3_r | 1.3623 | ok | 513 | 2023-11-15 to 2026-11-05 | 3.0 |
| target_conservative_1_r | 0.5045 | ok | 467 | 2023-11-14 to 2026-11-05 | 1.0 |
| target_conservative_2_r | 0.8702 | ok | 467 | 2023-11-14 to 2026-11-05 | 1.75 |

long window 2.194 x ATR: share of sessions whose excursion passed it, per year (and at the #1753 3.0):

| year | sessions | passed | share | share at 3.0 |
|---|---|---|---|---|
| 2016 | 169 | 1 | 0.006 | 0.000 |
| 2017 | 251 | 1 | 0.004 | 0.000 |
| 2018 | 251 | 0 | 0.000 | 0.000 |
| 2019 | 252 | 0 | 0.000 | 0.000 |
| 2020 | 253 | 1 | 0.004 | 0.004 |
| 2021 | 252 | 1 | 0.004 | 0.000 |
| 2022 | 251 | 1 | 0.004 | 0.000 |
| 2023 | 250 | 1 | 0.004 | 0.000 |
| 2024 | 252 | 4 | 0.016 | 0.008 |
| 2025 | 250 | 2 | 0.008 | 0.000 |
| 2026 | 213 | 0 | 0.000 | 0.000 |

short window 2.270 x ATR: share of sessions whose excursion passed it, per year (and at the #1753 3.0):

| year | sessions | passed | share | share at 3.0 |
|---|---|---|---|---|
| 2016 | 169 | 3 | 0.018 | 0.012 |
| 2017 | 251 | 3 | 0.012 | 0.004 |
| 2018 | 251 | 3 | 0.012 | 0.004 |
| 2019 | 252 | 3 | 0.012 | 0.000 |
| 2020 | 253 | 7 | 0.028 | 0.004 |
| 2021 | 252 | 2 | 0.008 | 0.004 |
| 2022 | 251 | 0 | 0.000 | 0.000 |
| 2023 | 250 | 0 | 0.000 | 0.000 |
| 2024 | 252 | 3 | 0.012 | 0.004 |
| 2025 | 250 | 2 | 0.008 | 0.004 |
| 2026 | 213 | 2 | 0.009 | 0.005 |

premarket drops, 20 sessions through 2026-11-06, calibrated (stale 0.0408, spike 0.5365 x ATR): 237 prints

| session | time ET | field | price | rule |
|---|---|---|---|---|
| 2026-10-12 | 08:12 | low | 278.9400 | stale_prior_close |
| 2026-10-13 | 04:00 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:00 | low | 277.8993 | stale_prior_close |
| 2026-10-13 | 07:35 | close | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:35 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:36 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:36 | open | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:37 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:37 | open | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:38 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:39 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:40 | close | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:40 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:42 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:42 | open | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:43 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:05 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:11 | close | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:11 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:12 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:12 | open | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:48 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:49 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:51 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:52 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:53 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:54 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:55 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:56 | low | 277.9000 | stale_prior_close |
| 2026-10-14 | 04:00 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 07:01 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 07:35 | close | 276.7000 | stale_prior_close |
| 2026-10-14 | 07:35 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 07:40 | close | 276.7000 | stale_prior_close |
| 2026-10-14 | 07:40 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 08:07 | close | 276.7000 | stale_prior_close |
| 2026-10-14 | 08:07 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 08:47 | high | 276.7000 | stale_prior_close |
| 2026-10-15 | 07:02 | low | 271.3735 | stale_prior_close |
| 2026-10-15 | 07:02 | open | 271.3735 | stale_prior_close |
| 2026-10-15 | 07:35 | close | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:35 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:36 | close | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:36 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:37 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:38 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:39 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:39 | open | 271.3700 | stale_prior_close |
| 2026-10-15 | 08:08 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 08:10 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 08:16 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 08:47 | low | 271.3700 | stale_prior_close |
| 2026-10-16 | 04:00 | low | 275.0800 | stale_prior_close |
| 2026-10-16 | 07:36 | close | 275.0800 | stale_prior_close |
| 2026-10-16 | 07:36 | low | 275.0800 | stale_prior_close |
| 2026-10-16 | 07:38 | low | 275.0800 | stale_prior_close |
| 2026-10-16 | 07:39 | low | 275.0800 | stale_prior_close |
| 2026-10-16 | 08:05 | low | 273.4518 | spike |
| 2026-10-16 | 08:08 | low | 275.0800 | stale_prior_close |
| 2026-10-16 | 08:08 | open | 275.0800 | stale_prior_close |
| 2026-10-19 | 07:02 | low | 270.4400 | stale_prior_close |
| 2026-10-19 | 07:36 | low | 270.4400 | stale_prior_close |
| 2026-10-19 | 08:20 | low | 270.4400 | stale_prior_close |
| 2026-10-19 | 08:47 | low | 270.4400 | stale_prior_close |
| 2026-10-20 | 07:35 | close | 271.2800 | stale_prior_close |
| 2026-10-20 | 07:35 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 07:38 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:01 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:02 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:03 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:04 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:04 | open | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:05 | open | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:07 | high | 271.2800 | stale_prior_close |
| 2026-10-21 | 04:01 | high | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:35 | close | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:35 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:37 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:37 | open | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:38 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:38 | open | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:39 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:39 | open | 275.7800 | stale_prior_close |
| 2026-10-21 | 07:40 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 08:05 | low | 271.5500 | spike |
| 2026-10-21 | 08:08 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 08:08 | open | 275.7800 | stale_prior_close |
| 2026-10-21 | 08:47 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 08:52 | low | 275.7800 | stale_prior_close |
| 2026-10-22 | 04:00 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:35 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:35 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:36 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:36 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:37 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:37 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:38 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:38 | open | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:39 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:39 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 08:05 | high | 277.2600 | spike |
| 2026-10-22 | 08:13 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 08:47 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:20 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:21 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:23 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:24 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:25 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:26 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:26 | open | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:27 | high | 276.4800 | stale_prior_close |
| 2026-10-23 | 07:35 | close | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:35 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:36 | close | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:36 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:42 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:42 | open | 276.6700 | stale_prior_close |
| 2026-10-23 | 08:08 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 08:08 | open | 276.6700 | stale_prior_close |
| 2026-10-23 | 08:47 | high | 276.6700 | stale_prior_close |
| 2026-10-26 | 07:01 | low | 275.7500 | stale_prior_close |
| 2026-10-26 | 07:39 | low | 275.7500 | stale_prior_close |
| 2026-10-26 | 07:39 | open | 275.7500 | stale_prior_close |
| 2026-10-26 | 08:20 | low | 275.7500 | stale_prior_close |
| 2026-10-27 | 07:35 | close | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:35 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:36 | close | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:36 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:37 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:37 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:38 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:38 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:04 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:04 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:05 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:05 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:16 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:17 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:17 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:19 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:23 | low | 276.9900 | stale_prior_close |
| 2026-10-28 | 04:00 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:01 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:02 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:02 | open | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:35 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:35 | open | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:36 | close | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:36 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:43 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:44 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 07:44 | open | 280.1800 | stale_prior_close |
| 2026-10-28 | 08:00 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 08:00 | open | 280.1800 | stale_prior_close |
| 2026-10-28 | 08:05 | high | 280.1800 | stale_prior_close |
| 2026-10-29 | 04:00 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:35 | close | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:35 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:37 | close | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:37 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:38 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:40 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:40 | open | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:41 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:08 | close | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:08 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:09 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:16 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:18 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:20 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:47 | low | 281.2900 | stale_prior_close |
| 2026-10-30 | 07:01 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:36 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:37 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:38 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:38 | open | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:59 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 08:00 | high | 284.0100 | stale_prior_close |
| 2026-11-02 | 07:02 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:35 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:35 | open | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:40 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:40 | open | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:05 | close | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:05 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:15 | close | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:15 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:23 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:23 | open | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:47 | low | 279.3300 | stale_prior_close |
| 2026-11-03 | 07:35 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 07:37 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 07:37 | open | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:05 | high | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:40 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:43 | close | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:43 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:45 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:46 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:47 | low | 279.1400 | stale_prior_close |
| 2026-11-04 | 04:00 | low | 278.5200 | spike |
| 2026-11-04 | 07:02 | close | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:02 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:37 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:38 | close | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:38 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:39 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:05 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:26 | close | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:26 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:27 | low | 279.7900 | stale_prior_close |
| 2026-11-05 | 07:35 | close | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:35 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:36 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:36 | open | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:37 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:37 | open | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:38 | close | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:38 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:40 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:40 | open | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:41 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 07:41 | open | 284.0200 | stale_prior_close |
| 2026-11-05 | 08:07 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 08:17 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 08:47 | low | 284.0200 | stale_prior_close |
| 2026-11-05 | 09:06 | low | 284.0200 | stale_prior_close |
| 2026-11-06 | 07:35 | close | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:35 | low | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:37 | low | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:38 | close | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:38 | low | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:39 | low | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:39 | open | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:40 | low | 270.9800 | stale_prior_close |
| 2026-11-06 | 08:05 | high | 283.7450 | spike |
| 2026-11-06 | 08:47 | low | 270.9800 | stale_prior_close |

premarket drops, 20 sessions through 2026-11-06, #1753 (stale 0.1000, spike 0.5000 x ATR): 160 prints

| session | time ET | field | price | rule |
|---|---|---|---|---|
| 2026-10-13 | 04:00 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:00 | low | 277.8993 | stale_prior_close |
| 2026-10-13 | 07:35 | close | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:35 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:36 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:36 | open | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:37 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:37 | open | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:38 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:39 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:40 | close | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:40 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:42 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:42 | open | 277.9000 | stale_prior_close |
| 2026-10-13 | 07:43 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:05 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:48 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:49 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:51 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:52 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:53 | low | 277.9000 | stale_prior_close |
| 2026-10-13 | 08:54 | low | 277.9000 | stale_prior_close |
| 2026-10-14 | 04:00 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 07:01 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 08:07 | close | 276.7000 | stale_prior_close |
| 2026-10-14 | 08:07 | low | 276.7000 | stale_prior_close |
| 2026-10-14 | 08:47 | high | 276.7000 | stale_prior_close |
| 2026-10-15 | 07:02 | low | 271.3735 | stale_prior_close |
| 2026-10-15 | 07:02 | open | 271.3735 | stale_prior_close |
| 2026-10-15 | 07:35 | close | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:35 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:36 | close | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:36 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:37 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:38 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:39 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 07:39 | open | 271.3700 | stale_prior_close |
| 2026-10-15 | 08:08 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 08:10 | low | 271.3700 | stale_prior_close |
| 2026-10-15 | 08:16 | low | 271.3700 | stale_prior_close |
| 2026-10-16 | 04:00 | low | 275.0800 | stale_prior_close |
| 2026-10-16 | 08:05 | low | 273.4518 | spike |
| 2026-10-19 | 07:02 | low | 270.4400 | stale_prior_close |
| 2026-10-19 | 07:36 | low | 270.4400 | stale_prior_close |
| 2026-10-19 | 08:20 | low | 270.4400 | stale_prior_close |
| 2026-10-19 | 08:47 | low | 270.4400 | stale_prior_close |
| 2026-10-20 | 07:38 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:01 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:02 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:03 | high | 271.2800 | stale_prior_close |
| 2026-10-20 | 08:07 | high | 271.2800 | stale_prior_close |
| 2026-10-21 | 04:01 | high | 275.7800 | stale_prior_close |
| 2026-10-21 | 08:05 | low | 271.5500 | spike |
| 2026-10-21 | 08:47 | low | 275.7800 | stale_prior_close |
| 2026-10-21 | 08:52 | low | 275.7800 | stale_prior_close |
| 2026-10-22 | 04:00 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:35 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:35 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:36 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:36 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:37 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:37 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:38 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:38 | open | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:39 | close | 276.4800 | stale_prior_close |
| 2026-10-22 | 07:39 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 08:05 | high | 277.2600 | spike |
| 2026-10-22 | 08:13 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 08:47 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:20 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:21 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:23 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:24 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:25 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:26 | high | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:26 | open | 276.4800 | stale_prior_close |
| 2026-10-22 | 09:27 | high | 276.4800 | stale_prior_close |
| 2026-10-23 | 07:35 | close | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:35 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:36 | close | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:36 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:42 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 07:42 | open | 276.6700 | stale_prior_close |
| 2026-10-23 | 08:08 | high | 276.6700 | stale_prior_close |
| 2026-10-23 | 08:08 | open | 276.6700 | stale_prior_close |
| 2026-10-23 | 08:47 | high | 276.6700 | stale_prior_close |
| 2026-10-26 | 08:20 | low | 275.7500 | stale_prior_close |
| 2026-10-27 | 07:35 | close | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:35 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:36 | close | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:36 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:37 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 07:37 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:04 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:04 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:05 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:05 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:16 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:17 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:17 | open | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:19 | low | 276.9900 | stale_prior_close |
| 2026-10-27 | 08:23 | low | 276.9900 | stale_prior_close |
| 2026-10-28 | 07:01 | high | 280.1800 | stale_prior_close |
| 2026-10-28 | 08:05 | high | 280.1800 | stale_prior_close |
| 2026-10-29 | 04:00 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:35 | close | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:35 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:37 | close | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:37 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:38 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:40 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:40 | open | 281.2900 | stale_prior_close |
| 2026-10-29 | 07:41 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:09 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:16 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:18 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:20 | low | 281.2900 | stale_prior_close |
| 2026-10-29 | 08:47 | low | 281.2900 | stale_prior_close |
| 2026-10-30 | 07:01 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:36 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:37 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:38 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:38 | open | 284.0100 | stale_prior_close |
| 2026-10-30 | 07:59 | high | 284.0100 | stale_prior_close |
| 2026-10-30 | 08:00 | high | 284.0100 | stale_prior_close |
| 2026-11-02 | 07:02 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:35 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:35 | open | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:40 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 07:40 | open | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:05 | close | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:05 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:15 | close | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:15 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:23 | low | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:23 | open | 279.3300 | stale_prior_close |
| 2026-11-02 | 08:47 | low | 279.3300 | stale_prior_close |
| 2026-11-03 | 08:40 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:43 | close | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:43 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:45 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:46 | low | 279.1400 | stale_prior_close |
| 2026-11-03 | 08:47 | low | 279.1400 | stale_prior_close |
| 2026-11-04 | 04:00 | low | 278.5200 | spike |
| 2026-11-04 | 07:02 | close | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:02 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:37 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:38 | close | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:38 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 07:39 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:05 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:26 | close | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:26 | low | 279.7900 | stale_prior_close |
| 2026-11-04 | 08:27 | low | 279.7900 | stale_prior_close |
| 2026-11-05 | 08:05 | low | 282.0450 | spike |
| 2026-11-05 | 08:47 | low | 284.0200 | stale_prior_close |
| 2026-11-06 | 07:37 | low | 270.9800 | stale_prior_close |
| 2026-11-06 | 07:40 | low | 270.9800 | stale_prior_close |
| 2026-11-06 | 08:05 | high | 283.7450 | spike |
| 2026-11-06 | 08:47 | low | 270.9800 | stale_prior_close |

breaks per side and year (sessions with one-minute bars):

| side | year | breaks | held |
|---|---|---|---|
| long | 2020 | 2 | 2 |
| long | 2023 | 7 | 7 |
| long | 2024 | 33 | 29 |
| long | 2025 | 99 | 70 |
| long | 2026 | 124 | 72 |
| short | 2017 | 164 | 44 |
| short | 2018 | 241 | 73 |
| short | 2019 | 243 | 66 |
| short | 2020 | 242 | 66 |
| short | 2021 | 243 | 82 |
| short | 2022 | 241 | 90 |
| short | 2023 | 237 | 74 |
| short | 2024 | 226 | 75 |
| short | 2025 | 166 | 77 |
| short | 2026 | 122 | 68 |

