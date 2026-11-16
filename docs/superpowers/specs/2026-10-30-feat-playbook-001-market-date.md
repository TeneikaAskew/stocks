---
feat_id: FEAT-PLAYBOOK-001
req_ids: [REQ-PLAYBOOK-001, REQ-REL-001]
issues: [1308]
canvases: []
site_source_notes: [PLAYBOOK-09]
done_when:
  - "tests/api/test_playbook_evaluate.py::test_playbook_age_uses_market_midnight passes all four summer/winter cases through the actual router, fresh and cached responses, and explicit historical dates; the UTC-midnight summer and winter cases fail on MAIN54fa457c and pass with canonical market_today."
  - "tests/api/test_playbook_evaluate.py::test_playbook_age_boundary and test_playbook_cached_set_is_rechecked_on_every_hit preserve the seven-day freshness boundary and recheck cached age; test_playbook_as_of_is_judged_against_the_requested_date preserves explicit date semantics; test_cards_from_db_converts_and_preserves_nulls preserves generated_at and nullable fields; the complete test_playbook_evaluate.py suite passes."
  - "FEAT-PLAYBOOK-001 catalog and PR traceability identify the repair and truthful evidence; the existing bounded source producer/verifier proves committed source identity with only the declared PLAYBOOK-09 source note changed; matched MAIN/candidate docs audit has no new findings, normal full PR-context gate and current required CODE/security/CI pass before merge."
status: approved
supersedes: null
---

# Playbook freshness uses the canonical market date

## Problem
Existing issue #1308 is reproduced on MAIN54fa457c. platform/api/routers/playbook.py:get_playbook uses datetime.now(timezone.utc).date() as the live freshness reference. At 2026-10-30T00:01Z it reports an October29 card one day old although Eastern time is still October29. The same error occurs before05:00Z in winter. Cache hits recompute with the same wrong reference.

## Authority and scope
The user explicitly requested the timezone mismatch/root-cause repair and audit on October30 at00:02:36UTC, Sentinel_69d79e3d6c5c8191b1c171e37f2a4ac4. This prepared approved contract records that bounded instruction; it is not a new product choice or permission to bypass normal spec-before-runtime review/publication. It addresses existing issue1308 only.

## Non-goals
No changes to ORB, LLM fallback, producer analysis dates, catalyst dates, trading calendars, database types, UTC storage, generated timestamps, financial calculations, frontend age labels, or the seven-day threshold. No data rewrite, provider call, replay, schema change, new endpoint or cache-key change.

## Approaches considered
Use existing lib.eastern_time.market_today (chosen: one DST-correct exchange-date authority); duplicate ZoneInfo/date logic (unnecessary second policy); recalculate the label in the browser (leaves server freshness rejection wrong).

## Design
Import market_today in platform/api/routers/playbook.py after the established project path setup. Set reference = as_of or market_today() once per request. Keep explicit YYYY-MM-DD dates as date values; do not reinterpret them as instants. Both database and cache paths continue using the existing freshness guard and max-age limit. Preserve UTC/offset-aware generated_at values and response schema. Update test clock fixtures to freeze the canonical clock rather than a no-longer-used router clock. The named regression tests actual API responses at summer00:01Z/04:00Z and winter04:59Z/05:00Z, including cache hits and explicit as-of dates.

Capacity: one existing O(1) timezone/date conversion per request; zero added database/provider requests or rows, unchanged payload/cache volume and configured deadlines/resources. No scheduled workload or incremental external service cost. Existing suite execution measured53tests/1.39seconds locally; this is test timing, not production latency proof.

## Risks
Incorrect calendar-date truncation could still shift age at DST-dependent midnight; paired summer/winter fixtures detect it. A stale cache could hide reference changes; existing cache recheck and new same-reference cases cover both. Explicit dates must not inherit the wall clock; every new case tests the historical request too. The API age remains calendar-day freshness, not a new trading-day rule.

## Source identity and close-out
Declare only PLAYBOOK-09 for this capability's appended implementation-source note. Use the existing bounded producer/verifier and actual immutable approved spec binding after this specification merges; never handcraft a successful receipt. No source-protocol implementation or ceiling changes. After runtime merge, record genuine MAIN source proof/required close-out, qualified serving-image revision and actual API/UI age evidence through already authorized access. These post-merge observations are not pre-merge checkboxes and no deployment claim follows from local tests.
