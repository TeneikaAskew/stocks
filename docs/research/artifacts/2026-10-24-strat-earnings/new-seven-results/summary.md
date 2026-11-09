# Seven new earnings cases: bounded news comparison

Seven single-attempt news reads completed HTTP200; 365 returned articles. One record at/after its exclusive cutoff was excluded; twelve duplicates removed. Six nonempty events yield 352 numeric deduplicated stories. TWLO is a valid empty feed, so its mean is missing.

Full 48h vendor-only Spearman versus opening gap: **−0.142857 (n=6)**; versus unchanged native five-day sustain: **−0.142857 (n=6)**. Exactly two coefficients were calculated for this new cohort. These small, post-hoc associations establish neither forecast accuracy nor causation. Original publisher/publication and syndication are unverified; independently publisher-qualified primary means remain null for all seven.

|Ticker|News n|Mean|Own label|Gap %|Native5d %|Prior daily opposite steps|Target first opposite close|
|---|---:|---:|---|---:|---:|---:|---|
|FDX|20|0.017694|neutral|-0.7786|-0.5210|4/4|2026-06-24|
|LLY|34|0.285475|positive|+5.2273|+4.3099|3/4|2026-08-05|
|STX|24|0.045105|neutral|+5.2924|+7.4347|4/4|2026-07-29|
|INTC|70|0.094614|neutral|+0.1297|-9.1969|4/4|2026-07-24|
|AMD|186|0.191235|positive|-6.5728|-2.1001|4/4|2026-08-06|
|TWLO|0|missing|empty|+21.7650|+6.0234|4/4|2026-08-12|
|VLO|18|0.202264|positive|-1.6295|-2.7975|4/4|2026-07-30|

The daily extension uses four cached mature priors and the fixed target per ticker: 35 episodes and 185 reaction-through-nativeD+5 closing observations. The first step compares reaction-day close with reaction-day open; later steps compare consecutive closes. A reversal here means the first strictly opposite nonzero closing step to the opening-gap sign; ties stay flat. This is a separately declared sampled-path description, not the legacy native reversal flag. A single opposite step does not mean the entire earnings move reversed, or that a trade was executable.

All 35 episodes have a nonzero initial gap; an opposite closing step occurs in 27/28 priors and 7/7 targets within the fixed horizon. These selected small windows do not demonstrate a predictive rule. Closing gap-fill is separate: first close beyond the pre-gap close, not proof of intraday touch. Missing, zero-gap and right-censoring definitions were frozen; zero-gap count is 0 and reversal right-censor count is 1.

All selected action-horizon split coefficients are actual 1; 3 cash-dividend rows are recorded. Values are nominal raw prices; no dividend adjustment, factor imputation or total-return claim. The copied native BMO sustain starts from reaction-day close; AMC sustain starts at next-session open. The separately described daily sequence always starts at reaction open.

Continuous/intraday reversal duration remains unobserved. Covering the fixed reaction-throughD+5 windows for all 35 episodes would require at least 48 distinct ticker-month intraday captures; just the seven target reaction days require 7. This is a metadata/request-unit count, not acquisition authority or proof that a complete response is available. No intraday or new price request was made.

News timestamps/scores are current vendor records, not immutable historical availability or independent publisher receipts. Means use unique exact target-ticker finite scores in [-1,1], deterministic URL/headline dedup across the full48h window, and unchanged thresholds ≤−.15 negative/≥.15 positive. Recent24h includes the exact24h boundary; release time is excluded. Old studies and legacy criteria were not changed. Prior target/outcome exposure is disclosed; this is research reconstruction, not originalPIT.
