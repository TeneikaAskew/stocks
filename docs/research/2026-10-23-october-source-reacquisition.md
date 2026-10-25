# Bounded October source reacquisition checkpoint

This is source availability and timestamp-label coverage, not market performance, original-capture restoration or qualified production input.

## Exact scope and completion

Fixed tickers: **SPY, QQQ, IWM, ANGO, TLRY, PEP, BYRN, HELE, NG, NRIX, DAL, APLD**. No additional ticker, month or provider calls are planned for this capture batch.

Per ticker, one `TIME_SERIES_INTRADAY` request: `interval=1min`, `month=2026-10`, `adjusted=false`, `extended_hours=true`, `outputsize=full`, JSON. The provider month endpoint has no sub-month date filter. Returned timestamp spans are listed below; October17–22 and other observations outside declared analysis clocks remain quarantined. There is no claim that October23–31 was returned.

Per ticker, one `TIME_SERIES_DAILY_ADJUSTED`, `outputsize=full`, JSON. This endpoint offers full or compact rather than an explicit date range. Preserve full raw OHLC, adjusted-close and split/dividend fields separately; no raw/adjusted mixing, factor1 or normalization has been performed. Exact provider-returned daily spans below are source labels, not validated issuer continuity or historical acquisition knowledge.

**24/24 responses acquired; zero pending;46,443,812 raw bytes.** All response-file hashes were checked during local export verification. Full month/history acquisition is separate from the bounded production replay workload; it does not certify replay read/memory/time compliance.

| Ticker | Daily labels, inclusive | Daily rows | October minute labels, inclusive (provider US/Eastern) | Minute rows | Oct1–9 RTH labels /2730 | Oct10–16 RTH labels /1950 |
|---|---|---:|---|---:|---:|---:|
| SPY | 1999-11-01–2026-10-22 | 6785 | 2026-10-01 04:00:00–2026-10-22 20:00:00 | 15368 | 2730 | 1950 |
| QQQ | 1999-11-01–2026-10-22 | 6785 | 2026-10-01 04:00:00–2026-10-22 19:59:00 | 15360 | 2730 | 1950 |
| IWM | 2000-05-26–2026-10-22 | 6641 | 2026-10-01 04:00:00–2026-10-22 20:00:00 | 14059 | 2730 | 1950 |
| ANGO | 2004-06-01–2026-10-22 | 5635 | 2026-10-01 04:40:00–2026-10-22 19:30:00 | 5353 | 2050 | 1505 |
| TLRY | 2018-07-19–2026-10-22 | 2077 | 2026-10-01 04:00:00–2026-10-22 19:57:00 | 8699 | 2643 | 1897 |
| PEP | 1999-11-01–2026-10-22 | 6785 | 2026-10-01 04:00:00–2026-10-22 19:59:00 | 13430 | 2730 | 1950 |
| BYRN | 2011-02-23–2026-10-22 | 3929 | 2026-10-01 04:00:00–2026-10-22 19:51:00 | 4859 | 1812 | 1337 |
| HELE | 1999-11-01–2026-10-22 | 6785 | 2026-10-01 06:25:00–2026-10-22 19:30:00 | 4221 | 1780 | 1275 |
| NG | 2003-12-04–2026-10-22 | 5757 | 2026-10-01 04:00:00–2026-10-22 20:00:00 | 7178 | 2704 | 1927 |
| NRIX | 2020-07-24–2026-10-22 | 1570 | 2026-10-01 04:03:00–2026-10-22 19:30:00 | 6580 | 2447 | 1935 |
| DAL | 2007-05-03–2026-10-22 | 4900 | 2026-10-01 04:00:00–2026-10-22 19:59:00 | 10736 | 2730 | 1950 |
| APLD | 2008-10-22–2026-10-22 | 4092 | 2026-10-01 04:00:00–2026-10-22 19:59:00 | 14951 | 2730 | 1950 |

## Expected denominator and gaps

Baseline October1–9: October1,2,5,6,7,8,9 — **7 full sessions**,84 ticker-sessions,390 RTH minute slots per ticker-session (`09:30 <= label < 16:00`, Eastern). Expected **32,760** slots; returned **29,816** timestamp labels; **2,944** absent slots.

Retrospective holdout October10–16: October12,13,14,15,16 — **5 full sessions**,60 ticker-sessions. October10–11 is a weekend; October12 is an NYSE trading session. Expected **23,400** slots; returned **21,576** labels; **1,824** absent slots. Across both windows: **56,160** expected versus **51,392** returned. This is a planning session-grid denominator, not genuine merged-calendar production acceptance.

Only timestamp keys/metadata were inspected for these counts. No held-out OHLC values, movement, activation, earnings outcome or returns were scored. A returned timestamp is not yet a valid/completed/admitted bar; source/session/basis/age guards still apply. An absent slot is not automatically a provider error or no-trade minute. Do not fill forward, invent observations or hide missingness; classification requires evidence for its declared coverage.

All raw responses together contain120,794minute labels and61,741daily labels across their full returned ranges. Those wider ranges are quarantined inputs, not an enlarged replay admission or silently expanded evaluation cohort. Daily/history/extended-session completeness and semantic qualification remain separate checks.

## Requests, quota, cost and measured timing

Runtime-key budget for this fixed batch: **24 data requests total** —12 daily plus12 minute. The earlier successful SPY minute probe was reused; the subsequent run made exactly23 new requests, with no retries or pending work. A separate connector-key probe was refused as premium-only; its generic rate-limit label is not evidence of runtime-key throttling. No provider calls are needed to fill this timing estimate.

Repository `lib/config.py::AlphaVantageConfig.rpm` declares150RPM. The acquisition process imposed30RPM (one request start no faster than every2seconds), one in-flight request,16MiB maximum response and180seconds maximum invocation. **Configured150RPM and process-local pacing do not establish subscription/account quota, remaining shared capacity or contention with other jobs.** Exact missing dependency: provider account usage/rate allocation plus aggregate usage by other processes/workloads. Those were not queried or inferred.

**Marginal dollar cost is unknown.** Existing runtime credential/entitlement worked; no plan purchase, new infrastructure or recurring schedule was created. Exact cost dependency: the existing provider billing/overage contract and billed usage, including any failed-call accounting. No zero-cost or unused-quota claim is made.

Observed final23-request run: **48.232seconds**, including credential/setup, pacing and I/O. Request starts in saved receipts are approximately2seconds apart. The first SPY minute response was already acquired separately. Remaining capture duration for this batch is **zero**. No per-request latency measurement was recorded, so do not present a fabricated average/p95. Engine qualification, private export, code repair and replay are separate work with no defensible completion ETA yet.

## Original data versus new retrieval; safe export

These24files were acquired October23,2026. They are **new current-vintage retrievals**, with new timestamps/hashes, not the missing original467-file capture set. They cannot establish the inputs known at the original October8–9 publication clocks. Current adjusted daily fields can reflect later corporate-action knowledge; actual merged DATA admission must decide eligibility, and a retrospective diagnostic cannot be relabeled contemporaneous validation.

The separate read-only GCS inventory for SPY/QQQ/IWM minute/intraday prefixes contains February–May2026 archives. They do not restore October. Existing generation-pinned SQL archives/native system records are another distinct recovered source, not the original AV capture set. Two2759-row-query boundary timestamps were conservatively excluded from the separate baseline extraction; all original archives remain unchanged. Its2757minute and336daily source rows remain unqualified and separate from these new responses.

A complete local tar.xz export of all24raw responses, manifest, coverage metadata and credential-free acquisition script is verified: `october-2026-reacquisition-current-vintage.tar.xz`, **2609568bytes**, SHA256 `c9ba95f09af60564c9c061f20bb7f5ec7cab1e8b0f91b1bbfd2813ee13934635`,30members. It is currently at `/workspace/strat-rebuild-control/october-2026-reacquisition-current-vintage.tar.xz`. Off-runtime full-payload backup is **not yet verified**.

The stocks repository was verified PUBLIC. Source code and non-price manifests/review documents are backed up on recoveryPR1573; full paid-provider payloads and native production rows have not been uploaded publicly. An approved private artifact destination/write path is the remaining full-data durability dependency. No GCP write, public raw-data upload, merge, deployment or new provider-access expansion was performed.

Holdout outcomes remain unscored until both repaired engines/settings freeze. No PMG/custom-anchor, financial-fill or live threshold decision was selected to make this capture usable.
