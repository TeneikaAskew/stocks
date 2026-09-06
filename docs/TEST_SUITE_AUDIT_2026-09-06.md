# Test suite audit — why 4,000+ tests missed these bugs

**Date:** 2026-09-06
**Question asked:** why are there over 4K tests, what are they, and why aren't
they catching these bugs — are they faulty, written to pass?

**Short answer:** they are not faulty and not written to pass. Of 4,095 test
functions, 21 have no assertion and all 21 are legitimate "this must not
raise" checks. Zero assert on a literal.

The problem is **where** the tests are, not whether they are honest.

---

## 1. What the suite is

237 files, 4,095 test functions (4,326 collected including parametrised cases).

| Tests | Area |
|---:|---|
| 1,492 | other / misc |
| 1,052 | signals / strategy / backtest |
| 431 | insights / narrative |
| 295 | options + gamma math |
| 257 | data ingestion / fetchers |
| **253** | **API / routers** |
| 114 | indicators / features |
| 102 | journal / trades |
| 99 | schema / database |

Roughly **1,900 tests cover computation** — signals, gamma, indicators,
backtests. That layer is genuinely well tested, and it is where the
intellectual property is, so that is not an accident.

**253 tests cover the API**, which is the only layer users actually touch.

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
withdrawn — 253 API tests covering 78 of 101 routes is a different situation
from 253 covering 20.

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

Even within the 253 API tests, three structural limits mean whole bug classes
are unreachable:

**The database is mocked.** 67 test files monkeypatch `query_to_dataframe` /
`execute_sql`; 12 touch a real database, and those are the integration suite.
A mocked DB returns canned rows, so it cannot surface:
- a query that reads 10M rows to return 43 (no cost signal exists)
- `DATE(ts)` framing time in UTC instead of ET (fixtures carry no timezone)
- an index that cannot be used because of a function on the column

**Handlers are called directly, not over HTTP.** 38 files call handler
functions; 59 use `TestClient`. Direct calls bypass FastAPI's dispatch, which
is exactly the layer where `async def` vs `def` matters.

**Nothing exercises concurrency.** Every test is single-threaded, so races
that only exist under threadpool dispatch — the engine singleton, the rate
limiter, the journal read-modify-write — are invisible by construction.

**Nothing asserts on cost.** There is no test anywhere that fails when a query
gets slower. The 9,870 ms query was correct; it returned exactly the right 43
dates. Every test that could have covered it would have passed.

## 4. What was added

Guard tests targeting the mechanism rather than the symptom:

- `tests/test_api_handler_dispatch.py` — no `async def` route handler without
  an `await`; nothing may `await` a plain `def`. AST-based, because a regex
  anchored to `^async def` cannot see a handler nested inside an `if`, and one
  was.
- `tests/test_market_dates_cache_expiry.py` — pins that cache freshness follows
  the **data** (a `MAX(ts)` probe plus a bounded TTL), and asserts the previous
  schedule-modelling constants are *gone*. An earlier version of this file
  anchored expiry to a 23:00 UTC ingestion; that approach was wrong three times
  over and was removed, so the test now guards its absence.
- `tests/test_platform_api.py` — gained the case that could not previously be
  written: a configured-but-broken Cloud SQL returns 503 rather than a 200 from
  the GCS fallback, and the driver's exception text does **not** reach the
  response body.

**Not present:** an earlier draft of this document listed
`tests/test_market_dates_timezone.py`. That file was deleted along with the
timezone change it guarded, once production data showed the table holds two
timestamp conventions and the conversion would corrupt premarket bars. Nothing
currently guards timezone framing on that table; it needs the data migration
first.

## 5. Recommended, not yet done

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
