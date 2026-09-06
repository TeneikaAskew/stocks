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

## 2. The finding

**81 of 101 route handlers (80%) are never referenced by any test.**

Including: `/api/health`, `/api/me`, every `/api/options/*` endpoint, every
journal write endpoint, every admin endpoint, `/api/market/data/{ticker}/{date}`.

Specifically, the handlers behind the defects found this week:

| Handler | Defect | Tests referencing it |
|---|---|---|
| `get_gamma_levels` | 500 on every `/levels` request | **0** |
| `get_options_dates` | 9,870 ms query | **0** |
| `get_grid_live` | part of the 16.2 s load | **0** |
| `_insert_cloud_sql_trade` | fabricated trade IDs | **0** |
| `get_available_dates` | 351 phantom dates (UTC vs ET) | 1 |

A suite of 4,095 tests passed a 500-on-every-request bug because **nothing
called that endpoint**.

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

Guard tests that target the mechanism rather than the symptom:

- `tests/test_api_handler_dispatch.py` — no `async def` route handler without
  an `await`; nothing may `await` a plain `def`. AST-based, because a regex
  anchored to `^async def` cannot see a handler nested inside an `if`, and one
  was.
- `tests/test_market_dates_cache_expiry.py` — cache expiry is anchored to the
  23:00 UTC ingestion, not a fixed TTL.
- `tests/test_market_dates_timezone.py` — no bare `DATE(ts)` on market data;
  the dates list and the data fetch must frame time identically; named zone,
  never a fixed offset.

Each pins a defect that is **invisible in normal use**: the endpoint still
returns plausible values, just wrong ones.

## 5. Recommended, not yet done

1. **Cover the API surface.** 80% of routes have no test. A smoke test per
   route asserting status + response shape would have caught the `/levels`
   500 and is cheap to write.
2. **Assert on cost, not just correctness.** For the handful of queries
   against large tables, an integration test that fails when rows-read
   exceeds a bound would have caught the 9,870 ms scan the day it landed.
3. **Give fixtures a timezone.** Every market-data fixture should carry a bar
   at or after 20:00 ET, so any UTC/ET confusion fails a test instead of
   shipping 351 phantom dates.
4. **Rebalance.** 1,052 tests on backtest logic against 253 on the whole API
   is worth revisiting deliberately, not by accident.
