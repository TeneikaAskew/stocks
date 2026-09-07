# GCP cost audit — 2026-09-06

Prompted by the Firebase console showing $41.94 for Sep 1–6 on a project
whose Firebase usage is close to zero. Every number below was read from
the BigQuery billing export
(`billing_export.gcp_billing_export_v1_0164FA_957DC0_7D90C4` and the FOCUS
table under `gcp_billing_immutable_0164FA_957DC0_7D90C4_us`) or from
`gcloud`, not inferred. The export covers the billing account the project
was on until 2026-09-02; see §1.

## 1. Why the bill "appeared" in September

It did not appear. It stopped being hidden.

| Month | List cost | Promo credit applied | Billed |
|---|---|---|---|
| 2026-07 (partial) | — | $5.85 | — |
| 2026-08 | $212.06 | $171.59 (`FreeTrialUpgrade`) | $35.24 |
| 2026-09-01 | $6.76 | $0.00 | $4.66 |

The free-trial promotional credit absorbed ~80% of August. It applied
$0.00 to Sep 1 usage. At 2026-09-02 00:48 UTC the project was moved to
billing account `0145DE-524AA2-7AF359` (`AssignResourceToBillingAccount`,
`teneika@bictech.org`), which has no credit and **no BigQuery export**, so
the export tables end on Sep 2. Enable billing export on the new account
(Billing → Billing export → BigQuery) or every query in this document goes
blind after Sep 2.

Firebase's free tier covers Firebase products (Auth, Firestore, Hosting).
The project's spend is Google Cloud infrastructure, which the Firebase
dashboard reports as "Non-Firebase Services". "Agent Platform" in that
dashboard is Firebase's label for the Vertex AI Gemini API.

## 2. Where the money goes (late-August run rate, list price)

| Service | $/day | $/month | Driver |
|---|---|---|---|
| Cloud Run | 3.71 | 111 | `discord-interactions` always warm ($51/mo); jobs ($44/mo, §5) |
| Cloud SQL | 2.35 | 70 | `trading-db` db-g1-small always on (~$25), 191 GB SSD (~$32), 7 snapshots + PITR |
| Artifact Registry | 0.99 | 30 | 448 + 175 untagged image versions, never deleted (§3) |
| Cloud Scheduler | 0.27 | 8 | 84 entries at $0.10 past the first 3 (§4); 66 after this audit |
| Cloud Storage | 0.08 | 2.4 | 89 GiB trading-data, 23 GiB `_cloudbuild` sources |
| Secret Manager | 0.05 | 1.6 | 22 secrets |
| Vertex AI | 0.02–0.03 | ~1 | Gemini 3.1 Flash Lite; one Gemini 2.5 Pro batch on Sep 1 ($0.34) |
| **Total** | **~6.5** | **~197** | |

## 3. Artifact Registry — fixed in this PR

`trading/trading-system` had 448 versions (282 GiB) for an image with 7
tags; `gcr.io/trading-platform` had 175 (63 GiB). Every
`gcloud builds submit --tag` moves `:latest` and strands the previous
digest untagged.

Deleting untagged versions blindly is unsafe: a Cloud Run Job resolves its
image tag to a digest at create/update time and every later execution runs
that digest (verified: `signal-monitor`, updated 08-30, still executed the
08-30 digest after `:latest` moved on 09-01). The 76 jobs pinned 30
distinct digests, 23 untagged, the oldest from April.

What shipped:

- `gcp/deploy.sh pin-images` tags each pinned digest `inuse-job-<job>` /
  `inuse-svc-<revision>` (every traffic-receiving, tagged, or latest-ready
  revision of each service, not only the newest); runs at the start of
  every `build_image` and after every deploy command. A job's deployed
  digest is taken from its latest execution when that execution's
  `jobGeneration` label matches the job's current generation, otherwise
  the job's image reference is resolved to a digest at pin time. Every
  read or write failure aborts the run; an unreadable inventory is never
  treated as an empty one (Codex review on #1004).
- `gcp/deploy.sh registry-cleanup` applies the policy to both repos: keep
  tagged, keep 10 newest, delete untagged older than 14 days. On `gcr.io`
  the delete rule is scoped to the retired `trading-platform*` packages
  only: `solyra-api` is also built by the Cloud Build trigger from #990,
  which cannot run `pin-images` before it moves `:latest`, so a prod
  revision's digest could otherwise lose its only tag on a later staging
  build. `platform/deploy.sh` now pins before its build; widen the prefix
  once the trigger does too. Applied 2026-09-06, re-applied with the
  scoped rule 2026-09-07 (`--no-dry-run`). Sweeps are asynchronous.
- Both image builds (`build_image`, `build_research_image`) pin before
  moving their tag and refuse to build if pinning fails; the dispatcher
  runs deploy steps one at a time (never as `a && b`) so a failed build
  cannot be masked by a later successful command.

Expected effect (computed against the live inventory after pinning):

| Package | Versions | Deleted | Freed |
|---|---|---|---|
| trading/trading-system | 448 | 389 | 245 GiB of 282 |
| gcr.io/trading-platform | 175 | 127 | 45 GiB of 63 |
| gcr.io/trading-platform-staging | 9 | 0 | 0 |
| gcr.io/solyra-api | 2 | 0 (excluded from delete, see above) | 0 |

Saves ~$25/month.

### 3a. `gcr.io/trading-platform` and `trading-platform-staging` — retire after #990

PR #990 renames the API image to `gcr.io/solyra-api` and the services to
`solyra-api-prod` / `solyra-api-staging`. As of 2026-09-06 the rename is
half-landed live: `solyra-api-staging` runs `solyra-api@fa6e1908`
(deployed twice today by the new Cloud Build trigger), while
`solyra-api-prod` still runs `trading-platform@f35433c4` from its only
revision (2026-09-05). That is the "crossed names" state — transitional,
not a config bug.

There is no "archive" tier for container images; they are rebuildable from
git, so the right disposition is deletion. Sequence:

1. Merge #990.
2. Run the manual `deploy-solyra-api-prod` trigger once. It promotes the
   digest staging is serving, so prod moves onto `solyra-api`.
3. `./gcp/deploy.sh retire-legacy-images`. It refuses while any live
   service revision still references `trading-platform`, then deletes the
   `trading-platform` and `trading-platform-staging` packages outright.

After step 3 the cleanup policy keeps `gcr.io` at ~2 versions of
`solyra-api` (~1 GiB).

## 4. Cloud Scheduler — fixed in this PR

24 entries that were byte-identical apart from the hour (same `:run` URI,
no body) became 3, same cadence:

| Was | Now |
|---|---|
| `news-sentiment-0800` … `-1700` (10) | `news-sentiment-hourly` `0 8-17 * * 1-5` |
| `news-topics-0805` … `-1705` (10) | `news-topics-hourly` `5 8-17 * * 1-5` |
| `sec-filings-0700/1000/1300/1700` (4) | `sec-filings-intraday` `0 7,10,13,17 * * 1-5` |

Applied via `./gcp/deploy.sh schedulers` on 2026-09-06; the retirement
loop deleted the 24. 84 → 64 entries, 66 with the two Discord warm-window
entries from §6. Saves ~$2/month. The `top-movers-intraday-hourly` /
`-close` pair stays: `30 9-15` and `5 16` cannot share one cron.

Each replacement entry is created-or-updated and read back (schedule,
target URI, `ENABLED`) before its predecessors are deleted; a replacement
that fails to verify leaves the old entries in place and fails the
deploy (Codex review on #1004).

## 5. Cloud Run jobs — analysed, no change recommended beyond two checks

August list cost by resource (`ResourceName`, FOCUS export):

| Resource | Aug $ | CPU-sec | Note |
|---|---|---|---|
| discord-interactions (service) | 50.95 | 2.68M | 1 vCPU allocated 24×31 h. §6 |
| strat-engine | 11.58 | 445k | 4 vCPU / 16 GiB, ~40 min/run, daily + manual runs |
| signal-monitor | 11.02 | 501k | 1 vCPU for the whole RTH session, 21 days. Structural |
| backfill-daily-indicators | 5.05 | 252k | 2 vCPU, **~1 h per nightly run** for a "NULL atr_14 in last 7d" repair |
| freshness-watchdog | 2.97 | 156k | 12 runs/day, **~5 min each** for a freshness check |
| magnitude-engine | 2.26 | 103k | research, manual |
| fetch-av-options-realtime | 2.25 | 119k | 78 runs/day × ~57 s |
| fetch-earnings-history | 1.97 | 99k | ~1 h/run, 4 runs |
| db-query | 1.10 | 42k | ad-hoc SQL dispatches |
| everything else (30 jobs) | ~4.5 | | |

Jobs total ≈ $44/month. The top three are what they cost by design:
signal-monitor must be up for the session, and strat-engine's 16 GiB
requires 4 vCPU (Cloud Run's memory/CPU ladder), so its CPU cannot be cut
without cutting memory. The two worth a look are correctness questions
that happen to cost money:

- `backfill-daily-indicators` should be a no-op most nights. An hour at
  2 vCPU suggests it recomputes far more than the NULL rows, or hits the
  per-ticker-query pattern Rule 0 forbids. Check its logs for
  `processed=` counts.
- `freshness-watchdog` at ~5 min/run is probably `count(*)` over
  `etf_options_snapshots` (141M rows). Use `max(snapshot_ts)` per ticker
  against an index instead.

## 6. `discord-interactions` — the single largest lever, needs a decision

**What the 3-second window is.** Discord's Interactions contract: an
application must return an initial response within 3 seconds of receiving
an interaction or Discord discards the interaction token and shows the
user "The application did not respond". The response can be a *deferred*
acknowledgement (type 5, the "thinking…" spinner), after which the app
has 15 minutes to edit the reply. `gcp/discord_interactions/main.py`
already does exactly that: `/replay`, `/validate`, `/backtest` defer and
edit later via FastAPI BackgroundTasks; `/watchlist` answers directly.

**What min-instances=1 buys.** The 3 seconds include container start when
no instance is warm. The deploy comment records 4–10 s cold start on this
image (it is the full `trading-system` image: pandas, google-cloud-run,
the Cloud SQL connector, all imported at boot). The module docstring
still claims "1–2 sec cold start fits the 3s ack"; the deploy.sh
measurement is the newer of the two, and this PR corrects the docstring.

**Implications of dropping to min-instances=0.**

- The first slash command after ~15 min idle fails with "did not respond".
  The instance is warm by then, so a retry succeeds. Autocomplete (type 4)
  on a cold instance silently shows no suggestions.
- Nothing else is affected. `insight-discord-push`, `signal-monitor`
  alerts and the briefs post to Discord *webhooks* from jobs; they never
  traverse this service. Command registration is a script. The deferred
  BackgroundTasks still finish: with `--no-cpu-throttling` the CPU stays
  allocated for the instance's lifetime, and Cloud Run keeps an idle
  instance up for ~15 min after the last request, well past the 540 s
  job wait.
- `--cpu-boost` (startup CPU boost) and a slimmer image would shrink the
  cold start; whether they get it under 3 s is a measurement, not a
  guess. Measure before relying on it.

**Cost of warm-during-market-hours only.** Instance-based billing at
1 vCPU + 512 MiB is $0.000018/vCPU-s + $0.000002/GiB-s ≈ $1.64/day
always-on, which is the $51/month observed.

| Warm window (ET, weekdays) | Hours/month | $/month | Saves |
|---|---|---|---|
| 24×7 (today) | 730 | 51 | — |
| 07:00–17:00 | ~215 | 15 | 36 |
| 09:00–16:30 | ~160 | 11 | 40 |
| never (min 0) | 0 | ~1 (request-based) | 50 |

**Applied 2026-09-07 00:41 UTC, window 09:00–16:30 ET weekdays.** Two
Cloud Scheduler entries (`discord-warm-open` `0 9 * * 1-5`,
`discord-warm-close` `30 16 * * 1-5`, $0.20/month) POST to the Cloud Run
v2 service with `X-HTTP-Method-Override: PATCH` and
`updateMask=template.scaling.minInstanceCount` (1 at open, 0 at close)
under `trading-runner@`'s OAuth token.

Two things had to be true first, and both were verified rather than
assumed:

- The PATCH produces a revision that differs from its predecessor only in
  `minScale` (env, secrets, command, CPU allocation and startup boost all
  unchanged), and the override header reaches Cloud Run as
  `UpdateService` with that mask.
- Cloud Run requires the caller to hold `iam.serviceAccounts.actAs` on
  the revision's runtime service account, which is `trading-runner@`
  itself. It did not have that self-binding, and the sandbox deploy
  identity (`claude-web@`, `roles/editor`) cannot grant it, since
  `setIamPolicy` on a service account is owner-only. The helper refuses
  to create the schedulers without it (a scheduler that 403s twice a day
  is a slow leak) and prints the grant; the owner ran it on 2026-09-07:

  ```bash
  gcloud iam service-accounts add-iam-policy-binding \
    trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com \
    --member=serviceAccount:trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com \
    --role=roles/iam.serviceAccountUser
  ```

End-to-end check after the grant: `gcloud scheduler jobs run
discord-warm-close` returned HTTP 200, the Cloud Run audit log shows
`UpdateService` by `trading-runner@` with no error, and the service moved
from revision `00034` (minScale 1) to `00035` (minScale 0) with an
identical container spec and 100% traffic. The first scheduled open is
Monday 2026-09-07 09:00 ET.

`deploy_discord_interactions` picks the value the schedule would have in
force at deploy time, so a redeploy cannot silently re-warm the service
until the next boundary. Outside the window the service behaves as the
min-0 case above. The Sunday-evening `premarket-brief-sunday` run posts
via webhook, so it is unaffected.

## 7. Cloud SQL — the disk, in plain terms

Cloud SQL charges for the disk you have *reserved*, not the bytes you
use, like renting a storage unit by its size. `storageAutoResize` grew
`trading-db`'s SSD to 191 GB over time. Google lets a disk grow but never
shrink, so even deleting half the data leaves you paying for 191 GB.

Measured 2026-09-06: the database is **167 GB**, so the disk is 87% full
and the "if the data is much smaller than the disk" case does not apply.
Two tables are 141 GB of the 167:

| Table | Total | Table only | Indexes etc. | Rows |
|---|---|---|---|---|
| `etf_options_snapshots` | 74 GB | 39 GB | 35 GB | 141M |
| `market_data_intraday_other` | 67 GB | 30 GB | 37 GB | 5.7M |

`market_data_intraday_other` carries more index than data for 5.7M rows;
that is either over-indexing or bloat, and `pg_stat_user_indexes` will
say which. `etf_options_snapshots` grows by ~78 snapshots/day from
`av-options-realtime` (every 5 min in RTH) under a 30-day retention job.
Auto-resize will keep growing the disk as these grow.

The saving path is therefore: shrink the data first (retention window,
drop unused indexes, `VACUUM FULL` the two tables), then move to a new
instance with a right-sized disk (clone or export/import, then cut over),
because that is the only way to get a smaller disk. At $0.17/GB/month
SSD, every 50 GB not reserved is ~$8.50/month; an HDD disk on the new
instance would be $0.09/GB. Until the data shrinks there is nothing to
save here, and the two tables are worth understanding before touching.

## 8. Not worth doing

- Cloud Storage: `_cloudbuild` source bucket is 23 GiB ($0.50/month). A
  30-day lifecycle rule is fine but not material.
- Vertex AI: ~$1/month. Leave it.
- Secret Manager, Logging, Pub/Sub, BigQuery: under $2/month combined.
