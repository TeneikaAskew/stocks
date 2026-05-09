# Track B implementation plan — premarket brief recommendations

**Working branch:** `claude/audit-track-b-brief-ff3Qm`
**Reference docs (on `main`):**
- `docs/audit/2026-05-08/audit-summary.md`
- `docs/audit/2026-05-08/track-G.md`
- `docs/audit/2026-05-08/track-B.md`

---

## Context

Track B's audit (merged in #293) found the 8:30 AM premarket brief is
running every morning but operating on stale inputs because the daily
fetcher has been frozen on 2026-04-27 since 4-28. The brief silently
republishes byte-identical bias / levels / RSI for every session.

Track G's synthesis (merged in #294) prioritized Track B's findings as
two P0 items, four P1 items, and two P2 items — eight total. The
audit-summary's recommended sequencing is: clear P0s in dependency
order (G.P0.1 → G.P0.4 → G.P0.6 → G.P0.10 → G.P0.11), then P1s in
the next sprint, then P2s.

This plan implements every Track B recommendation in priority order,
respecting the cross-track dependencies surfaced in track-G §2 and §4.
When a Track B item is blocked by another track, this plan will:
1. file a GitHub issue making the wait explicit (per user's guidance), and
2. continue working downstream items that are not blocked.

User-confirmed decisions (from clarifying questions):
- **G.P1.5 fix shape**: gate `signal_status` by `ftfc_direction` (lose
  fade-bias plays in exchange for source-side consistency).
- **G.P2.11 scope**: persist all four LLM-generated commentary slots
  (`llm_overview`, `llm_orb_explanation`, `llm_analysis`,
  `llm_playbook`) to a sidecar table for audit trail, accepting that
  re-generation on replay will produce different text.

---

## Track B work items (mapped to Track G priorities)

| # | Track G ref | Type | Owns | Cross-track dep |
|---|---|---|---|---|
| W1 | G.P1.5 | Fix | Track B | none |
| W2 | G.P1.7 | Fix | Track B | none |
| W3 | G.P1.6 | Investigation | Track B | none |
| W4 | G.P1.10 | Investigation | Track B + D | none for diagnosis; fix may need D |
| W5 | G.P0.5 schema (and G.P0.4 + G.P2.11 schema bundled) | Schema | Track B | **#281 apply-schema-migrations job is failing — Track A** |
| W6 | G.P0.5 + G.P0.4 writer | Fix | Track B | W5 schema + Track A G.P0.1 for verification |
| W7 | G.P2.11 writer | Fix | Track B | W5 schema |
| W8 | G.P2.10 | Investigation | Track B | Track A G.P0.1 for "healthy data" sample |

Items W1–W4 have no cross-track dependencies and start immediately.
W5–W8 are gated; this plan files the blocker issues and proceeds with
the unblocked work first.

---

## Cross-track dependencies (issues to file before starting)

| Issue | Owner | Why Track B is waiting |
|---|---|---|
| **Track A — G.P0.1: unfreeze `fetch-market-data` Cloud Run Job** | Track A | Required for end-to-end verification of W6 (stale-warn must flip back to "healthy" when data is fresh). Without this, our new "Based on data from X to Y" Discord line will keep showing stale ranges and we can't validate the healthy rendering path. |
| **#281 apply-schema-migrations job failure** | Track A (or whoever owns the job) | W5 schema migration cannot land via the standard apply path. Workaround: apply via `db-query.yml` workflow with `commit=true` — we'll do that as a fallback if #281 isn't fixed within 48 h. |
| **Track A — G.P0.3: re-enable freshness watchdog** | Track A | Not strictly blocking, but co-mitigates the same failure mode. Mention in plan; do not block on it. |

These will be filed as GitHub issues in step 0 of execution (see
"Execution sequence" below) tagged `track-b-blocked-on:<owner>` so the
wait is visible to anyone looking at the project.

---

## Per-item implementation

### W1 — G.P1.5: gate `signal_status` by FTFC direction (PR: fix)

**Files to modify:**
- `gcp/premarket_brief.py:796-808` — replace the unconditional
  threshold ladder with an FTFC-gated variant. Pseudo-code:
  ```python
  ftfc_dir = (ftfc_dir or 'mixed').lower()
  if 'bull' in ftfc_dir:
      score, side = call_score, 'CALL'
  elif 'bear' in ftfc_dir:
      score, side = put_score, 'PUT'
  else:                       # mixed
      if call_score >= put_score:
          score, side = call_score, 'CALL'
      else:
          score, side = put_score, 'PUT'
  signal_status = (
      f'{side} setup ({score}/5)' if score >= signal_threshold
      else f'{side} building ({score}/5)' if score >= building_threshold
      else 'No signal'
  )
  ```
- `tests/test_premarket_brief.py` — add three regression tests:
  - bullish FTFC + put_score=4 + call_score=2 → "CALL building (2/5)"
  - bearish FTFC + call_score=4 + put_score=2 → "PUT building (2/5)"
  - mixed FTFC + ties go to higher score's side

**Effort:** 2 hr code + 30 min tests. **PR title:**
`fix(brief): gate signal_status by FTFC direction to prevent CONFLICTED bias`

### W2 — G.P1.7: suppress cleared-side trigger block (PR: fix)

**Files to modify:**
- `lib/strat_levels.py:987-1024` — when `regime_long == 'orb_only'` AND
  `ct['trigger_level'] < spot`, suppress the trigger block (keep only
  the per-side banner). Same logic mirror for PUTS at lines 1012-1024.
  Concretely, gate the `if ct:` body on `not (regime_long == 'orb_only'
  and ct['trigger_level'] < spot)`. The `_side_banner` already emits a
  meaningful "wait for ORB" warning in that case (lines 970-974), so
  the trigger block is redundant and confusing.
- `tests/test_strat_levels_playbook.py` — add a regression test
  asserting that a CALL trigger below spot under `regime_long='orb_only'`
  produces banner-only output (no "CALLS above N (PDH)" line).

**Effort:** 2 hr code + 30 min tests. **PR title:**
`fix(strat-levels): suppress cleared-side trigger block when regime is orb_only`

### W3 — G.P1.6: investigate `strat_setup` flag drift (PR: investigation)

The Track B audit flagged `strat_combo='322_bull_continuation'` with
`strat_setup=False` as "internally inconsistent." The Explore pass for
this plan revealed that `lib/strat.py:247` defines:
```python
result['strat_setup'] = (labels == '1') & (prev1.isin(['2U','2D','3']))
```
i.e. `strat_setup` is True ONLY when the latest bar is an inside bar
(`'1'`) following a directional bar — it's a "wait-for-inside-bar-break"
flag, orthogonal to the `strat_combo` label. A continuation combo
firing on a directional bar with `strat_setup=False` is **by design**.

**Action:** verify with a unit test (`tests/test_strat_classifier.py`
or new file) that asserts the orthogonality, then close the audit item
as not-a-bug with a docstring clarification on `detect_combos`. No
production code change. **PR title:**
`docs(strat): clarify strat_setup vs strat_combo orthogonality (closes audit B.5)`
**Effort:** 30 min investigation + 30 min test + docstring.

### W4 — G.P1.10: investigate `brief_bias` NULL on 5/4-5/6 (PR: investigation)

`signal_alerts.brief_bias` was NULL on 5/4-5/6 but populated on 5/7.
The Explore pass identified the writer (`gcp/signal_monitor.py:745-758`,
`_resolve_brief_bias` calls `lib.strategies.brief_bias.get_premarket_bias`).
Investigation steps:
1. `git log --follow --oneline gcp/signal_monitor.py | grep -i bias`
   to find the commit that introduced the writer.
2. `git log --follow --oneline lib/strategies/brief_bias.py` for the
   helper. Compare commit dates against the eval window.
3. Cross-reference Cloud Run Job revisions (`gcloud run jobs revisions
   list signal-monitor`) to confirm what was deployed on 5/4 vs 5/7.
4. If the writer shipped after 5/4 (likely): close as deploy-timing
   artifact, NO production code change. Add a regression test asserting
   `_resolve_brief_bias` returns a populated dict when a fresh
   `premarket_analysis` row exists.
5. If the writer was deployed before 5/4 but failing silently: real
   bug — log the failure mode, file as new P1.

**Effort:** 2 hr (mostly diagnosis). **PR title:**
`audit: investigate brief_bias NULL on 5/4-5/6 (closes audit cross-link G.P1.10)`

### W5 — Schema migration for W6 + W7 (PR: schema)

**File to modify:** `gcp/schema.sql` — add an idempotent
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` block at the bottom (mirroring
the existing pattern at lines 1142-1145):

```sql
-- Audit-followup: data freshness + LLM commentary persistence
ALTER TABLE premarket_analysis
    ADD COLUMN IF NOT EXISTS data_as_of            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_freshness_status VARCHAR(20),
    ADD COLUMN IF NOT EXISTS llm_overview          TEXT,
    ADD COLUMN IF NOT EXISTS llm_orb_explanation   TEXT,
    ADD COLUMN IF NOT EXISTS llm_analysis          TEXT,
    ADD COLUMN IF NOT EXISTS llm_playbook          TEXT;

ALTER TABLE premarket_analysis_history
    ADD COLUMN IF NOT EXISTS data_as_of            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_freshness_status VARCHAR(20),
    ADD COLUMN IF NOT EXISTS llm_overview          TEXT,
    ADD COLUMN IF NOT EXISTS llm_orb_explanation   TEXT,
    ADD COLUMN IF NOT EXISTS llm_analysis          TEXT,
    ADD COLUMN IF NOT EXISTS llm_playbook          TEXT;
```

`data_freshness_status` values: `'fresh'`, `'STALE_DAILY_DATA'`, or
`NULL` (pre-migration rows).

**Apply path:** the `apply-schema-migrations` Cloud Run Job
(issue #281, currently failing). If #281 is unresolved at PR time, fall
back to applying the ALTER block via `db-query.yml` with `commit=true`
as a one-shot. Both paths leave `gcp/schema.sql` as the canonical source.

**Tests:** none — schema-only PR. **PR title:**
`feat(schema): add freshness + LLM commentary columns to premarket_analysis`
**Effort:** 30 min code + dependency on #281.

### W6 — G.P0.5 + G.P0.4: data_as_of writer + stale-warn (PR: fix, batched)

These two items share a staleness-detection helper, so they ship in
one PR.

**Files to modify:**

1. **`gcp/premarket_brief.py:741-745` — staleness detection helper.**
   After `latest = df.iloc[-1]`, compute:
   ```python
   data_as_of = latest.name  # the index timestamp of the last good bar
   freshness_gap_days = (analysis_date - data_as_of.date()).days
   is_stale = freshness_gap_days > 1 and analysis_date.weekday() != 0  # not Monday
   data_freshness_status = 'STALE_DAILY_DATA' if is_stale else 'fresh'
   ```
   (Monday exemption avoids treating Friday→Monday as stale.)

2. **`gcp/premarket_brief.py:813-851` — populate per-ticker dict.**
   Add `'data_as_of': data_as_of, 'data_freshness_status': data_freshness_status`
   to the `brief['tickers'][ticker]` dict.

3. **`gcp/premarket_brief.py:865-880` — top-level summary.**
   Compute the min/max across all populated tickers; populate
   `brief['data_freshness_summary']` with a string like
   `"Based on data from 2026-04-27 → 2026-04-27 (1 trading day, stale by 6 sessions)"`.

4. **`gcp/premarket_brief.py:1206-1215` — overview embed.**
   Insert a description-suffix line (mirroring the `llm_overview`
   pattern) that renders `brief['data_freshness_summary']` with a
   warning emoji when `is_stale`. Place it before the FTFC summary so
   freshness is the first thing the trader sees.

5. **`gcp/premarket_brief.py:2049-2089` — persist row builder.**
   Add `'data_as_of': data.get('data_as_of')` and
   `'data_freshness_status': data.get('data_freshness_status')` to
   the `rows.append({...})` dict.

6. **`gcp/premarket_brief.py:persist_to_cloud_sql`** — populate the
   `notes` column on the `premarket_analysis_history` insert when
   any ticker is stale: `notes = "Stale daily data: gap of N sessions"`
   (closes B.3 — `premarket_analysis_history.notes` is currently unused).

7. **Tests** (`tests/test_premarket_brief.py`):
   - Mock daily df ending on D-7; assert `is_stale=True`,
     `data_freshness_status='STALE_DAILY_DATA'`, summary string contains
     "stale by".
   - Mock daily df ending on D-1 (Tuesday→Wed); assert `is_stale=False`.
   - Mock daily df ending on Friday + analysis_date=Monday; assert
     `is_stale=False` (weekend exemption).
   - Mock persist call; assert `notes` populated when stale.

**End-to-end verification deferred until Track A G.P0.1 lands** — at
that point, watch the next morning's brief; it should print
`"Based on data from <yesterday> → <yesterday> (1 trading day)"` with
no warning emoji. Until then, the brief renders the stale-state path,
which is a useful side-effect of the bug it's diagnosing.

**Effort:** 1 hr code + 1 hr tests. **PR title:**
`feat(brief): surface data freshness window and fail loud on stale daily inputs`

### W7 — G.P2.11: persist LLM-generated commentary (PR: fix)

**Files to modify:**
- `gcp/premarket_brief.py:2049-2089` — extend the row builder dict
  with the four LLM strings:
  ```python
  'llm_overview': brief.get('llm_overview'),
  'llm_orb_explanation': brief.get('llm_orb_explanation'),
  'llm_analysis': data.get('llm_analysis'),
  'llm_playbook': data.get('llm_playbook'),
  ```
  (Note: `llm_overview` and `llm_orb_explanation` are top-level on
  `brief`, while `llm_analysis` and `llm_playbook` are per-ticker on
  `data`.)
- `tests/test_premarket_brief.py` — add an integration test that mocks
  `generate_explanations` to set known values and asserts they land in
  the persisted row.

**Effort:** 30 min code + 30 min tests. **PR title:**
`feat(brief): persist Gemini-generated commentary for audit trail`

### W8 — G.P2.10: embed quality replay (PR: investigation)

After Track A G.P0.1 lands, replay one healthy morning via
`BRIEF_AS_OF=<recent-date> python -m gcp.premarket_brief --update` (or
the Discord `/replay` command) and capture the four embeds. Diff
against the actual earnings_calendar / economic_events tables for that
date. Document findings in
`docs/audit/2026-05-08/track-B-followup-embed-replay.md` and close.

**Effort:** 2 hr investigation. **PR title:**
`audit: full Discord brief render replay against earnings/calendar`

---

## Execution sequence (with wait-points)

The user's directive is "work top priorities from your track and
everything before another track blocks it … then when blocker removed
you can finish." Translation: attempt the top priorities, run into the
blockers, file issues, do the unblocked work in parallel.

### Step 0 — File cross-track blocker issues (~15 min)

Before any code is written, file two GitHub issues in `TeneikaAskew/stocks`:

- **"audit: track-B P0 implementation blocked on G.P0.1 (daily fetcher
  unfreeze)"** — labels `track-a-followup`, `audit-2026-05-08`,
  `blocking-track-b`. Body cross-references this plan's W6/W8 and
  asks Track A to confirm timeline.
- **Comment on existing #281** — note that Track B's W5 schema
  migration is blocked on the apply-schema-migrations job; offer the
  `db-query.yml` workaround as fallback if no fix in 48 h.

### Step 1 — Commit this plan to the branch (~5 min)

Copy `/root/.claude/plans/review-the-following-documenation-foamy-sparrow.md`
to `docs/audit/2026-05-08/track-B-implementation-plan.md` on the
working branch and push. This makes the plan visible to reviewers
without merging it through a PR (it's a planning doc, not code).

### Step 2 — Unblocked PRs in priority order

Per "one PR per investigation, batched fixes":

| Order | PR | Type | Track G priority |
|---|---|---|---|
| 2.1 | W1 (gate `signal_status` by FTFC) | fix | G.P1.5 |
| 2.2 | W2 (suppress cleared-side trigger) | fix | G.P1.7 |
| 2.3 | W3 (strat_setup orthogonality docstring + test) | investigation | G.P1.6 |
| 2.4 | W4 (brief_bias NULL diagnosis) | investigation | G.P1.10 |

Each PR ships independently. After 2.1-2.2 land, mark off in the
plan; if 2.3-2.4 reveal real bugs, file follow-up issues.

### Step 3 — Wait point: schema PR (#281 dependency)

If #281 is fixed (or 48 h have passed and we're using the workaround):
- 3.1 W5 (schema migration) — single PR.

If still blocked: pause this branch's W5/W6/W7 work; revisit weekly.

### Step 4 — Post-schema PRs

After W5 lands:
- 4.1 W6 (data_as_of + stale-warn writer + Discord embed) — fix
  (G.P0.5 + G.P0.4 + B.3 batched).
- 4.2 W7 (LLM commentary persistence) — fix (G.P2.11).

### Step 5 — Wait point: Track A G.P0.1

End-to-end verification of W6 needs healthy daily data. If G.P0.1
isn't done by 4.1 PR time, mark the PR as "merged but unverified" and
tag it for a follow-up post-G.P0.1 verification commit.

### Step 6 — Post-G.P0.1

- 6.1 W8 (embed quality replay) — investigation.
- 6.2 W6 verification follow-up if marked unverified at 4.1.

### Step 7 — Final cleanup

Update `docs/audit/2026-05-08/track-B.md` to mark each backlog item as
✅ resolved, then close the audit-followup issues filed in step 0.

---

## Critical files (single source of truth)

| File | Why |
|---|---|
| `gcp/premarket_brief.py` | The brief itself — every Track B P0/P1/P2 fix touches this file |
| `gcp/schema.sql:1142+` | Schema migration pattern to mirror for W5 |
| `lib/strat.py:247` | `strat_setup` definition (W3 investigation) |
| `lib/strat_levels.py:790-1040` | `format_levels_for_brief` (W2 fix) |
| `gcp/signal_monitor.py:745-758` | `_resolve_brief_bias` (W4 investigation) |
| `lib/strategies/brief_bias.py` | `get_premarket_bias` SQL path (W4) |
| `gcp/brief_explanations.py` | LLM commentary generator (W7 source) |
| `tests/test_premarket_brief.py` | Existing 1822-line test surface — add to, don't replace |
| `tests/test_strat_levels_playbook.py` | Existing 405-line test surface for W2 |

---

## Reuse / non-duplication notes

- The existing `_resolve_analysis_date` (`gcp/premarket_brief.py:609`)
  and the `BRIEF_AS_OF` replay flow already give us a clean way to
  test W6 against historical dates. Use it instead of building a new
  test harness.
- The `_build_overview_embed` description-suffix pattern (the
  `if overview_text:` block at lines 1213-1215) is exactly what W6's
  freshness summary line should mirror — same `lines.append('')` +
  `lines.append('emoji ' + str(...))` shape.
- The Cloud Run Job invocation pattern for the (deferred) auto-backfill
  kickoff lives at `gcp/discord_interactions/main.py:230-267`. If we
  later implement track-B item 9's backfill kickoff, extract that code
  into `gcp/cloud_run_helper.py:execute_job(job_name, env_overrides)`.
  Out of scope for this plan — Track A G.P0.1 makes the auto-kickoff
  unnecessary in steady state.
- The schema `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern at
  `gcp/schema.sql:1142-1145` is exactly what W5 mirrors. Don't invent
  a new migration system.

---

## Verification

For each shipped PR:

- **W1 (G.P1.5)**: run `pytest tests/test_premarket_brief.py -k signal_status -v`
  and verify the three new assertions pass. Manually replay a known
  bullish-FTFC date with mock data and confirm `signal_status`
  starts with "CALL" not "PUT".
- **W2 (G.P1.7)**: run `pytest tests/test_strat_levels_playbook.py -v`
  and verify the new banner-only assertion passes. Manually inspect a
  brief from a gap-up day and confirm the trigger block is suppressed.
- **W3 (G.P1.6)**: `pytest tests/test_strat_classifier.py -v`. Audit
  doc updated.
- **W4 (G.P1.10)**: investigation findings committed; either deploy
  timing artifact noted or new P1 issue filed.
- **W5 (schema)**: query `\d premarket_analysis` and
  `\d premarket_analysis_history` in Cloud SQL; confirm the 6 new
  columns exist on both. Re-running `gcp/apply_schema.py` is a no-op.
- **W6 (data_as_of + stale-warn)**: trigger one brief run with
  `BRIEF_AS_OF=2026-05-07` (the known-stale date) and inspect the
  Discord post — should show "Based on data from 2026-04-27 →
  2026-04-27 (1 trading day, stale by 6 sessions) ⚠". Then trigger
  another with a healthy date (post-G.P0.1) — should show "Based on
  data from <yesterday> → <yesterday>" with no warning.
- **W7 (LLM persistence)**: run brief, query
  `SELECT llm_overview, llm_analysis FROM premarket_analysis WHERE
  analysis_date = current_date AND ticker='SPY'` — both should be
  populated text strings.
- **W8 (embed replay)**: rendered Discord post matches expected
  earnings/calendar entries from the same morning's
  `earnings_calendar` and `economic_events` rows.

End-to-end: after all PRs land, replay 2026-05-04 with `BRIEF_AS_OF`
and confirm the historical brief shows the stale-warning banner.
Then trigger today's brief and confirm it shows healthy.

---

## What this plan deliberately does NOT do

- **Does NOT touch Track A's daily fetcher** (G.P0.1). That's outside
  Track B's scope; we file the dependency issue and wait.
- **Does NOT auto-backfill on staleness** (Track B audit doc item #9.1).
  Track A's G.P0.1 fix removes the need; auto-backfill from the brief
  layer would create dueling owners. If Track A's fix doesn't hold,
  revisit.
- **Does NOT rebuild `gcp/signal_monitor.py`'s level-break detection**
  (the `level_broken=NULL` finding from track-G §2.4). That's
  addressed by G.P0.1 (data) + G.P1.1 (Track D). Track B only needs
  to ensure the brief stops feeding stale levels into `strat_levels`,
  which W6's stale-warn does (the existing `persist_level_map` call
  becomes a no-op when `data_freshness_status='STALE_DAILY_DATA'`
  because the brief skips the per-ticker analysis loop entirely).
- **Does NOT re-touch `Architecture.drawio`** (Track F's domain).

---

## Status (live tracking)

This section is updated as implementation progresses. PR links are
appended once each lands.

- [x] Step 0: file cross-track blocker issues — closed [#300](https://github.com/TeneikaAskew/stocks/issues/300) as duplicate of [#295](https://github.com/TeneikaAskew/stocks/issues/295) (Track A G.P0.1) + comment on [#281](https://github.com/TeneikaAskew/stocks/issues/281#issuecomment-4410095931) (apply-schema-migrations). Meta tracking issue [#314](https://github.com/TeneikaAskew/stocks/issues/314) filed.
- [x] Step 1: commit this plan to branch (commit 4da7441)
- [x] Step 2.1: W1 G.P1.5 — PR [#306](https://github.com/TeneikaAskew/stocks/pull/306) **merged** (3ce818d on main); auto-closed [#298](https://github.com/TeneikaAskew/stocks/issues/298)
- [x] Step 2.2: W2 G.P1.7 — PR [#307](https://github.com/TeneikaAskew/stocks/pull/307) **merged** (6af89c6 on main); Codex review addressed in same PR (439288a)
- [x] Step 2.3: W3 G.P1.6 investigation — PR [#309](https://github.com/TeneikaAskew/stocks/pull/309) **merged** (42f6821 on main); orthogonality docstring + 4 regression tests; closed as not-a-bug
- [x] Step 2.4: W4 G.P1.10 investigation — PR [#310](https://github.com/TeneikaAskew/stocks/pull/310) **merged** (01e6373 on main); auto-closed [#299](https://github.com/TeneikaAskew/stocks/issues/299); deploy-timing artifact, no production change
- [x] Step 3 gate cleared: [#295](https://github.com/TeneikaAskew/stocks/issues/295) (Track A G.P0.1) closed at 2026-05-09 00:59 UTC; #281 schema-apply job stale (verified successful executions on 2026-05-07 12:59 + 13:08, plus Track E shipped #326 schema via same path on 2026-05-08).
- [x] Step 3.1: W5 schema — PR [#335](https://github.com/TeneikaAskew/stocks/pull/335) **merged** (dfa3ed7 on main); Codex P2 review (premarket_analysis_history ALTER ordering) addressed in same PR (84f19be)
- [x] Step 4.1: W6 stale-warn + data_as_of — PR [#336](https://github.com/TeneikaAskew/stocks/pull/336) **merged** (2d3974b on main); two Codex reviews addressed in same PR (95856d2): downstream embed-skip + Sunday weekend exemption
- [ ] Step 4.2: W7 LLM commentary — PR [#337](https://github.com/TeneikaAskew/stocks/pull/337) — open, rebased on post-W6 main (e1e11d8); awaiting CI
- [x] Step 5 gate cleared: Track A G.P0.1 #295 closed
- [ ] Step 6.1: W8 embed quality replay — PR [#340](https://github.com/TeneikaAskew/stocks/pull/340) — open, Codex P2 (earnings JOIN dependency) addressed (3980014); awaiting CI
- [ ] Step 7: close meta tracking issue [#314](https://github.com/TeneikaAskew/stocks/issues/314); mark Track B audit doc fully resolved (after #337 + #340 merge)

### Round 1 outcome (2026-05-08)

**All four unblocked items merged to main.** Two PRs are fixes (W1
+ W2), two are investigations (W3 + W4). One Codex review on W2
caught a logical hole in the spot-check; addressed in the same PR
with a redesigned regime-only suppression and an explicit
wick-and-fade regression test.

| W# | PR | Merge SHA | Auto-closed |
|---|---|---|---|
| W1 | #306 | 3ce818d | #298 |
| W2 | #307 | 6af89c6 | (no tracking issue) |
| W3 | #309 | 42f6821 | (closed as not-a-bug; no tracking issue) |
| W4 | #310 | 01e6373 | #299 |

### Round 2 outcome (2026-05-09 — partial)

Both blockers cleared: Track A G.P0.1 (#295) merged the daily
fetcher unfreeze + freshness watchdog + on_stale guard; #281's
apply-schema-migrations job verified working (Track E's #326
shipped via same path).

| W# | PR | Status | Merge SHA |
|---|---|---|---|
| W5 schema | #335 | ✅ merged | dfa3ed7 |
| W6 stale-warn writer | #336 | ✅ merged | 2d3974b |
| W7 LLM persistence | #337 | open, rebased post-W6 (e1e11d8) | (awaiting CI) |
| W8 embed audit | #340 | open, Codex addressed (3980014) | (awaiting CI) |

Codex review interactions in Round 2 (all addressed in same PR):

- **#335**: ALTER TABLE ordering — `premarket_analysis_history`
  ALTER would have run before its CREATE on a fresh DB. Fix moves
  the columns inline in the CREATE definition + a deferred ALTER
  block immediately after CREATE.
- **#336 P1**: downstream loops needed STALE_DAILY_DATA skip paths
  (playbook block, overview embed, ticker fields) — fix adds
  explicit `continue` + degraded "STALE (data N sessions old)"
  lines.
- **#336 P2**: Sunday weekly brief Friday-data exemption — fix
  extends weekend bridge to cover `weekday=6 AND gap=2`.
- **#337 P2**: cross-PR schema dependency on #335 — declined; the
  merge order is documented and tested, mirroring the existing
  PR-#129/#101 convention.
- **#340 P2**: earnings embed gap-reaction line depends on
  `market_data_daily` via LEFT JOIN — fix updates the audit doc
  with the asymmetric dependency and per-sub-section status table.

CI on every Round 2 PR ran the full `pytest tests/ -x -q` suite;
all green on every push.

CI on every PR ran the full `pytest tests/ -x -q` suite (no
exclusions); all green on every push. Downstream contracts
verified: W1's gate preserves the `signal_status` string format
that `lib/strategies/brief_bias.py:get_premarket_bias` parses, and
in fact obsoletes the parser's `CONFLICTED` branch (now unreachable).

### Round 2 trigger conditions

Resumes (W5 → W6 → W7 → W8) once either:
- #281 apply-schema-migrations is fixed by Track A, OR
- 48 h pass (~2026-05-10 21:46 ET) and we apply the schema
  migration via the `db-query.yml` workflow as a one-shot fallback
  (per plan §"Apply path" of W5).
