# Task5A fix round 1 of 5 — independent scoped re-review

**Disposition: scoped PASS. Spec compliance: PASS for the authorized Task5A fix scope. Code quality/correctness: PASS for this fix diff.** All four original findings are addressed: **R1, R2 and R3 (P1/Important), R4 (P2/Important)**. **Outstanding original findings: 0. New findings introduced by this fix: 0. Critical/Important findings remaining in this scoped review: 0.**

This completes one scoped re-review of the original R1–R4 batch and direct interactions of this fix. It is not a new whole-task audit, an expansion of the review loop, or whole-feature/production approval. The prior complete first review remains immutable historical evidence; this disposition supersedes its open R1–R4 status for the identified fix candidate only. The task completion gate remains distinct from the PR review-round/P1 cap. Root owns final task disposition, publication and subsequent work.

Reviewer: original independent reviewer `/root/review_rebuilt_strat5a`, 2026-10-23. Candidate: `/workspace/stocks-strat-rebuild`. No candidate source/test edits, Git mutations, application probes, suite reruns, network/DB/vendor/capture/holdout access, settings changes, production main/replay execution, notifications, nested agents or downstream implementation were performed in this re-review.

## Identity and preservation

Reviewed fix manifest SHA256: `2d333ebe539082066d6767da17cca872e74bb9e701624e7e19429a60cae62be5`.

Reviewed baseline manifest SHA256: `7180cd41670b5ddb84d1fc863ddbe6dd609ad7c142e742aea1eef87025961368`.

Independent read-only verification succeeded for:

- All **382** previously recorded artifacts, including the first review and original reviewer probe evidence.
- All **26** fix baseline files against their recorded identities and the preceding frozen tree.
- All **26** current live files against fix1 frozen bytes and manifest; **22** are unchanged.
- Exactly **4** changed paths: three production files and appended parity tests.
- The exact reconstructed baseline-to-candidate diff and independently derived source AST inventory.
- The prior parity file preserved byte-for-byte as a prefix of the new file.
- Accepted unchanged level source `fff237a96f75a3570bb1cc832ff8b136fbe9fe4b7f0bc766031b13087d5ea6d8` and main level test `81ac17b3e12262f656b3377649cfa9bc562fe74b673f8bf915404e80071caf98`.

| Changed path | Candidate SHA256 |
|---|---|
| `lib/data_loader.py` | `30cb80ff13e8c1c54a6d8d6b0f136e01baf181968aa713cf70aed0870cfec68f` |
| `lib/strat.py` | `31f6549b059fe242cf0305e0a54b4975c984b11efc985d9983892ef1b8081912` |
| `gcp/premarket_brief.py` | `c8927f9e7d4882b63a2e5cea3ae100faf0f245e097c30aad4778638c1220a63f` |
| `tests/gcp/test_strat_snapshot_parity.py` | `8a9b5e5108fad9458c270a4155ed6dd62d09913662a8558140a474c4733d72b9` |

The original review SHA remains `f7289de977b2c87910b9e41e6af634c7be1043abcafae32f1153fed9247d6812`. Verification script/result: `reviewer-identity-check.py`, `reviewer-identity-check.json`. The implementer's `freeze.py` was inspected, not run by the reviewer because it copies/rewrites artifacts.

## Finding dispositions and direct interactions

### R1 — P1 / Important — addressed

At `lib/strat.py:928–945`, the inserted/updated current candle's comparison barrier now checks current coverage, expected exchange-period adjacency, and the immediately preceding period's coverage record. A missing predecessor record fails closed. The code uses the existing calendar and period mapping rather than adding a new calendar primitive. Classification consumes this barrier through the existing classifier; no direction or threshold rule changed.

The sensitive actual-producer cases in `test_review_r1_current_merge_keeps_both_period_comparison_barriers` distinguish a missing prior session and incomplete previous week from malformed prior OHLC. The two original missing/incomplete cases fail against the preceding candidate and pass after the fix; a complete adjacent week remains directional/full continuity and invalid prior OHLC remains unavailable. Assertions also preserve the independent current-period coverage, price/open availability and observed price. The correction is appropriately limited to candle comparison evidence and does not turn valid independent current facts unavailable.

I inspected current-label insertion/update, period-key identity, predecessor lookup and its callers, including strict directional and price/open continuity. The completed-daily `legacy_frames` copy remains before minute merging and is untouched by the fix. No remaining R1 defect or fix-induced legacy-score change was identified.

### R2 — P1 / Important — addressed

At `lib/data_loader.py:1141–1155`, the adapter filters to completed observations for the observation session before rejecting completed off-grid timestamps. It normalizes OHLCV columns numerically on that admitted representation before deriving the regular frame, quotes, extrema, aggregate coverage or accepted intraday-level input. Under the retained recovered regular schedule, minute-aligned timestamps bounded by the RTH open/close align with the existing one-minute aggregate grid. Supplied differing calendar bounds remain explicitly refused.

The actual adapter/producer tests cover interior and latest completed off-grid input, numeric and numeric-string controls, normalized volume, consistent HOD/extrema/current candle, and exclusion of a future off-grid observation before admission. The original lexicographic maximum and off-grid current-candle problems are covered by meaningful RED failures. The explicit whole-input off-grid refusal matches the authorized conservative source-contract correction; it returns no substitute quote or current merge. No new source qualification, adjustment factor or financial policy was added.

The current merge and configured intraday aggregation both receive the normalized regular frame. The optional premarket boundary remains separate from regular evidence, and the original valid/missing/invalid cases remain present in the final parity selection. No remaining R2 defect or new interaction requiring an additional probe was identified.

### R3 — P1 / Important — addressed

At `gcp/premarket_brief.py:3252–3256`, `STRAT_UNAVAILABLE` now follows the existing `NO DATA` skip before any history or canonical row is assembled. Empty results return before either writer. The previously retained in-memory snapshot/reason is not removed. This is the authorized restoration of existing guards, not a Task5B migration or new history policy.

The actual-generator-to-actual-writer tests use empty and short inputs across update/no-update and existing/missing-row cases, replacing `gcp.database` with an in-memory capture module. They assert zero writes; mixed valid/unavailable cases assert valid SPY history and canonical writes still occur and unavailable IWM is omitted. Both writer branches and the post-filter empty check were inspected. Production logging in these tests is logging against stubs, not evidence of real database activity.

At `gcp/premarket_brief.py:2173–2180`, both the bullish count and denominator exclude unavailable/stale statuses. The all-unavailable and mixed-bullish cases now preserve the old neutral/valid-evidence behavior. Existing unavailable text guards remain intact. No remaining R3 defect or new writer/render regression was identified.

### R4 — P2 / Important — addressed

At `lib/data_loader.py:1184–1187`, the separately declared extended source no longer undergoes an extra RTH-close truncation. The regular frame is still bounded by open/close at 1165, and completion filtering still precedes selection at 1141–1142. Thus after-hours observations affect the explicitly extended/latest quote without contaminating regular open/extrema/current candle data.

Actual adapter and shared-producer tests cover premarket, RTH, after-close and future-bar cutoffs. Completed 16:29 quote 121 at 16:30 has age zero; at 16:30:30 it has age 30 seconds. The later 16:30 bar remains excluded. The final after-hours high of 1222 makes the separate regular-high assertion sensitive to accidental contamination. A declared `NYSE_regular` source retains its regular quote despite supplied after-hours data. Shared observed-price timestamp/age propagation is asserted, not just adapter output.

The existing 09:33 sentinel becomes completed by the after-hours clock, so expected regular quote 998 is correct for this test fixture; it does not indicate an accepted future leak. No after-hours trading/fill policy was introduced. No remaining R4 defect or new session/cutoff interaction was identified.

## Evidence and review limits

I read the binding fix brief first, report, complete fix-only diff, manifests, preservation and AST inventory, literal command log, original complete review, changed functions in surrounding source and their directly affected helpers/consumers, and all appended tests. The source AST changes are exactly `compute_strat_status`, `snapshot_minute_context`, `_build_overview_embed`, and `persist_to_cloud_sql`. The scope did not reopen unrelated original Task5A code or later partitions.

Actual retained output supports the recorded sequence:

| Evidence | Recorded result | Interpretation |
|---|---|---|
| `red.txt` | 17 failed, 5 passed, 59 deselected | Includes an incomplete valid-render fixture; original log retained. |
| `red-corrected-fixtures.txt` | 16 failed, 6 passed, 59 deselected, 1.22s | R1: 2; R2: 3; R3: 9; R4: 2 genuine regression failures. |
| `green-focused.txt` | 22 passed, 59 deselected, 1.35s | Corrected initial regression/control batch. |
| `green-parity.txt` | 85 passed, 4.52s | All 59 preserved plus 26 appended cases. |
| `green-final.txt` | **239 passed, 6.81s** | Necessary affected selection, including all 85 parity cases, after strengthening after-hours test extrema. |

The corrected fixtures and displayed failures are consistent with the retained baseline source and the reported source-unchanged RED phase. I independently verified preserved baseline/final bytes and inspected the recorded chronology; I did not re-execute historical commands or claim direct observation of the original edits. The final literal command uses explicit `--mode=mock` and blank `CLOUD_SQL_CONNECTION_NAME`, with the required environment and Python. Its selectors cover the changed producer/loader and actual brief rendering/persistence boundaries. No evidence here upgrades earlier 753/458 results into final-fix full-suite claims, and no such reruns were needed.

No unresolved concrete fix-specific doubt justified an application probe. Therefore there are **no new reviewer application probes** and no replacement output for the immutable original probes. The only reviewer execution beyond source/evidence reads was the static identity/diff/AST checker:

```sh
source /workspace/stocks-setup/shell-env.sh
/workspace/stocks-venv/bin/python /workspace/strat-rebuild-control/task5a-rebuild/fix1/reviewer-identity-check.py > /workspace/strat-rebuild-control/task5a-rebuild/fix1/reviewer-identity-check.json
```

## Requirements that remain separately open

This scoped approval closes R1–R4 for local Task5A correctness. It does **not** qualify actual sources or complete the approved feature:

- Genuine merged shared-calendar and DATA basis/restoration/source-vintage/PIT integration remain blocked. `current_action` remains explicitly unavailable. Coherent synthetic fixtures are not production or corporate-action qualification.
- Task5B persistence/migrations/all writer and dashboard parity, Task5C history/CLI, Task5D monitor, and Task5E remaining actual legacy goldens, M1/envelope/activation/resolver obligations remain under their existing partitions.
- Task6 actual production no-write orchestration, refused persistence/notification calls, captured-input replay identity/cutoff evidence and capacity/source-read checks remain required. This fix does not make ordinary production entrypoints safe dry runs.
- Approved-spec-on-main, remaining documentation/registry/spec gates, source publication/merge and whole-feature promotion requirements remain unchanged. No learned-feature migration, threshold retuning, financial/PMG/anchor/fill/PnL policy or acquisition lineage was approved here.

No new scoped findings are withheld, and this re-review stops after this complete pass.

## Durable exact scoped review evidence

Original report/identitychecker/result are in the [verified four-member archive](https://github.com/TeneikaAskew/stocks/pull/1573#issuecomment-6371428613),6,660bytes,SHA256`d7753a9d802bb4f1649d87c7bff09a6150adcd2d55a892198029baf154334a95`; originalreviewSHA256`e5810bfce5f2fdad86f65cb3d0830da4bc6c49f10cd38b59ac13ef490e0a49e1`. Local artifact links above are shown as filenames here; exactoriginalreportbytes remain in the archive. No new application probes or suites were run for this scoped approval.
