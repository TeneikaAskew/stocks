# Test suite audit — why 4,000+ tests missed these bugs

**Date:** 2026-09-06
**Question asked:** why are there over 4K tests, what are they, and why aren't
they catching these bugs — are they faulty, written to pass?

**Short answer:** they are not faulty and not written to pass. Of the 4,166
test functions counted below, **17** contain no `assert` and no `pytest.raises`
— re-measured by AST walk on this branch; the first draft said 21 — and all 17
are legitimate "this must not raise" checks, where the call under test is the
assertion (`test_default_config_passes_validation`,
`test_script_importable`, `test_nonzero_rows_passes`, …). Zero assert on a
literal.

The problem is **where** the tests are, not whether they are honest.

---

## 1. What the suite is

**Re-measured 2026-09-06 on this branch, after #1001 reorganised `tests/` into
per-area folders.** The first version of this section reported 237 files /
4,095 functions / 4,326 collected, and grouped them into thematic areas
(signals, insights, options…) by a method it did not state. Both are now
wrong: the reorg changed the tree, and an unstated method cannot be re-run to
check. Every number below is followed by the command that produces it, so the
next reader can re-measure instead of trusting this file — which is the whole
lesson of §2.

```
$ find tests -name 'test_*.py' | wc -l
240
$ grep -rhoE '^[[:space:]]*(async )?def test_[A-Za-z0-9_]+' tests \
      --include='test_*.py' | wc -l
4166
$ python -m pytest tests/ --collect-only -q | tail -1
4321 tests collected
```

**240 files, 4,166 test functions, 4,321 collected** including parametrised
cases. (Collected exceeds declared because parametrisation expands; 4,306 with
`--ignore=tests/integration`.)

The thematic table is replaced by the directory table, because after #1001 the
directory IS the grouping and it can be counted mechanically:

| Tests | Files | Directory | What lives there |
|---:|---:|---|---|
| 1,503 | 103 | `tests/gcp/` | fetchers, research jobs, schema, Cloud jobs |
| 1,456 | 59 | `tests/lib/` | signals, gamma, indicators, backtests — the math |
| **455** | **28** | **`tests/api/`** | **routers and the FastAPI app** |
| 396 | 27 | `tests/scripts/` | one-off and operational scripts |
| 201 | 10 | `tests/agents/` | agent definitions and prompts |
| 122 | 6 | `tests/audits/` | standing repo-wide audits |
| 15 | 4 | `tests/integration/` | the only tests touching a real database |
| 11 | 1 | `tests/e2e/` | archived static-site E2E |
| 7 | 2 | `tests/meta/` | guards on the repo itself |

Roughly **1,456 tests cover computation** — signals, gamma, indicators,
backtests. That layer is genuinely well tested, and it is where the
intellectual property is, so that is not an accident.

**455 tests cover the API**, which is the only layer users actually touch. The
earlier figure of 253 came from the unstated thematic grouping and is not
comparable: `tests/api/` collects files the old grouping scattered across
"API / routers", "journal / trades" and "other / misc". Nothing was added to
make the number rise.

## 2. The finding — CORRECTED 2026-09-06

> **This section first claimed "81 of 101 route handlers (80%) are never
> referenced by any test". That number was wrong and the method producing it
> was invalid.** It counted references to Python *handler function names*. The
> suite drives the API through `TestClient` with **URL paths**, so
> `client.get("/api/health")` never mentions `health_check` and was scored as
> uncovered. A proxy measurement was reported as the headline without checking
> that the proxy measured the thing (CLAUDE.md 3.11).

Re-measured by mapping tested request paths to registered routes, with path
parameters turned into patterns:

```
registered route handlers : 101
  exercised by a test URL :  78
  NOT exercised           :  23  (22%)
distinct /api URLs in tests/: 165
```

**22%, not 80%.** The rebalancing recommendation built on the old figure is
withdrawn — `tests/api/` covering 78 of 101 routes is a different situation
from it covering 20.

### What survives, and is still the point

The correction does not rescue the endpoints that actually broke. Grepping
tests for their URLs:

| Route | Test URL present? | What happened |
|---|---|---|
| `/api/options/{t}/{d}/levels` | **no** | returned 500 on every request; whole suite passed |
| `/api/options/dates/{t}` | **no** | 9,870 ms query |
| `/api/options/{t}/grid` | yes | — |
| `/api/market/dates/{t}` | yes | — |
| `/api/health` | yes | — |

So the accurate statement is narrower and still worth acting on: **coverage is
uneven rather than absent, and the gaps sat exactly where the defects were.**
23 uncovered routes is a tractable list, not a rewrite.

## 3. Why the shape of the tests hides the rest

Three structural limits mean whole bug classes are unreachable. These counts
were also re-measured on this branch — the first version gave 67 / 12 / 38 / 59
by an unstated method that does not reproduce, so the method is spelled out
here with each figure.

**The database is mocked.** **46** test files patch a database accessor
(`monkeypatch.setattr` / `mock.patch` naming `query_to_dataframe`,
`execute_sql`, `get_engine` or `connect`); **5** touch a real database, and
those are `tests/integration/`. A mocked DB returns canned rows, so it cannot
surface:
- a query that reads 10M rows to return 43 (no cost signal exists)
- `DATE(ts)` framing time in UTC instead of ET (fixtures carry no timezone)
- an index that cannot be used because of a function on the column

**Handlers are mostly reached over HTTP, and that is the good news.** Of the
**28** files importing an `api` module, **26** drive it through `TestClient`
and only **2** call handler functions directly
(`tests/api/test_catalysts_news_filter.py`,
`tests/api/test_journal_user_scoping.py`); **31** files use `TestClient` in
total. Direct calls bypass FastAPI's dispatch, which is exactly the layer
where `async def` vs `def` matters — so this is now a narrow exposure rather
than the broad one the first draft described. The measurement was wrong, not
the reasoning.

**No API route receives concurrent traffic.** The suite is not entirely
single-threaded — `tests/lib/test_strategy_isolation.py` drives 100 evaluations
through a `ThreadPoolExecutor` and `tests/gcp/test_insight_pipeline_job.py`
starts and joins a thread — but that concurrency exercises *library* code. No
test issues overlapping `TestClient` requests against a route, so races that
only appear under threadpool dispatch (the engine singleton, the rate limiter,
the journal read-modify-write) are invisible by construction.

**Nothing asserts on cost.** There is no test anywhere that fails when a query
gets slower. The 9,870 ms query was correct; it returned exactly the right 43
dates. Every test that could have covered it would have passed.

## 4. What was added

Guard tests targeting the mechanism rather than the symptom:

- `tests/api/test_market_dates_cache_expiry.py` — pins that cache freshness follows
  the **data** (a `MAX(ts)` probe plus a bounded TTL), and asserts the previous
  schedule-modelling constants are *gone*. An earlier version of this file
  anchored expiry to a 23:00 UTC ingestion; that approach was wrong three times
  over and was removed, so the test now guards its absence.
- `tests/api/test_platform_api.py` — gained the case that could not previously be
  written: a configured-but-broken Cloud SQL returns 503 rather than a 200 from
  the GCS fallback, and the driver's exception text does **not** reach the
  response body.

**Not in this branch, despite an earlier draft claiming it:**
`tests/api/test_api_handler_dispatch.py` (the AST guard asserting no `async def`
route handler lacks an `await`, and that nothing may `await` a plain `def`).
It lives on the threading-migration branch, #991, not here. The handlers this
PR touches still make synchronous database calls from `async def`, and nothing
in *this* tree prevents that regression — see §5.

**Also not present:** an earlier draft of this document listed
`tests/test_market_dates_timezone.py` (flat, pre-#1001). That file was deleted
along with the
timezone change it guarded, once production data showed the table holds two
timestamp conventions and the conversion would corrupt premarket bars. Nothing
currently guards timezone framing on that table; it needs the data migration
first.

## 5. Recommended, not yet done

0. **Port the dispatch guard from #991.** `tests/api/test_api_handler_dispatch.py`
   exists only on the threading-migration branch. Until that lands, nothing in
   this tree stops a synchronous database call being added to an `async def`
   handler — and this PR's own endpoints still do exactly that.


1. **Cover the remaining 23 routes.** A smoke test per route asserting status
   and response shape would have caught the `/levels` 500. 23 is a morning's
   work, not a programme.
2. **Assert on cost, not just correctness.** For the handful of queries
   against large tables, an integration test that fails when rows-read
   exceeds a bound would have caught the 9,870 ms scan the day it landed.
3. **Give fixtures a timezone.** Every market-data fixture should carry a bar
   at or after 20:00 ET, so any UTC/ET confusion fails a test instead of
   shipping 351 phantom dates.
4. ~~Rebalance the suite.~~ **Withdrawn** — it rested on the wrong 80% figure.
   With 78 of 101 routes exercised, the distribution is defensible; the gaps
   are specific, not systemic.
