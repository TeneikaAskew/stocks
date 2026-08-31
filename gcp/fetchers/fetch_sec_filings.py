#!/usr/bin/env python3
"""
Cloud Run Job: Poll SEC EDGAR for recent filings (8-K, 10-Q, 10-K) → Cloud SQL.

8-K filings are the "something material happened" form: M&A (item 1.01),
bankruptcy (1.03), exec changes (5.02), Reg-FD disclosures (7.01), etc.
This fetcher captures them in real time as a free catalyst stream for
the ranker — covering any ticker SEC tracks, no AV quota cost.

EDGAR endpoints used:
  * https://www.sec.gov/files/company_tickers.json
        — public ticker ↔ CIK map. ~10k entries, refreshed weekly.
  * https://data.sec.gov/submissions/CIK{cik:010d}.json
        — last 1000 filings per company, JSON arrays.

Rate limit: SEC publishes 10 req/sec/IP. The 0.15s delay between calls
keeps us at ~7 RPS — safely under the cap.

A descriptive User-Agent header is required by SEC. Set via env var
SEC_USER_AGENT (defaults to a generic identifier — override in deploy).

Usage:
    python -m gcp.fetchers.fetch_sec_filings
    python -m gcp.fetchers.fetch_sec_filings --tickers AAPL,MSFT,AVGO --forms 8-K,10-Q
"""

import argparse
import logging
import os
import sys
import time as time_module
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

EDGAR_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_FORMS = ("8-K", "10-Q", "10-K")
SEC_RATE_DELAY_S = 0.15  # ~7 RPS, well under the 10 RPS limit
DEFAULT_USER_AGENT = "Trading System Research research@example.com"

# Retry policy for SEC throttling. EDGAR returns 429 when the *egress IP*
# exceeds its budget — on Cloud Run that IP is shared with other tenants, so a
# 429 can arrive on our first request of a run through no fault of our pacing.
# It is a "wait and retry" signal, not a permanent failure.
SEC_MAX_ATTEMPTS = 4
SEC_BACKOFF_BASE_S = 1.0          # 1s, 2s, 4s between attempts
SEC_BACKOFF_MAX_S = 30.0          # cap a hostile Retry-After
SEC_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

# The ticker→CIK map changes rarely (SEC refreshes it ~weekly) but is fetched
# on every run and is a single point of failure for the whole job. Cache it so
# a throttled run can still proceed — LOUDLY, never silently (CLAUDE.md 3.7).
CIK_CACHE_BLOB = "sec/company_tickers.json"
CIK_CACHE_MAX_AGE_H = 168         # 7 days; beyond that, fail rather than guess

# Global ceiling on time this run may spend asleep in backoff. Retrying is
# per-request, so without a shared budget a sustained throttle would multiply:
# ~500 tickers x 3 backoffs x up to 30s of Retry-After is ~45,000s against an
# 1800s task-timeout. The task would be KILLED mid-loop, and because filings
# accumulate in memory until the post-loop write, every fetched row would be
# lost. Bounding total backoff keeps the worst case at roughly
# baseline (~225s) + 300s, so the job always reaches its write path and fails
# with partial data rather than nothing (CLAUDE.md Rule 0).
SEC_RETRY_BUDGET_S = 300.0

_retry_budget_spent = 0.0


def _reset_retry_budget() -> None:
    """Zero the per-run backoff budget. Called once at job start."""
    global _retry_budget_spent
    _retry_budget_spent = 0.0


def _claim_retry_budget(wait: float) -> bool:
    """Reserve ``wait`` seconds of backoff; False when the budget is spent."""
    global _retry_budget_spent
    if _retry_budget_spent + wait > SEC_RETRY_BUDGET_S:
        return False
    _retry_budget_spent += wait
    return True


def _retry_after_seconds(resp, attempt: int) -> float:
    """Seconds to wait before the next attempt.

    Honours SEC's ``Retry-After`` header when present (integer seconds form),
    otherwise exponential backoff. Capped so a hostile or bogus header cannot
    park the job past its task-timeout.
    """
    hdr = None
    if resp is not None:
        try:
            hdr = resp.headers.get("Retry-After")
        except Exception:
            hdr = None
    if hdr:
        try:
            return min(float(int(str(hdr).strip())), SEC_BACKOFF_MAX_S)
        except (TypeError, ValueError):
            pass  # non-integer (HTTP-date) form — fall through to backoff
    return min(SEC_BACKOFF_BASE_S * (2 ** attempt), SEC_BACKOFF_MAX_S)


def _http_get(url: str, user_agent: str, timeout: int = 30) -> dict | None:
    """GET an EDGAR JSON endpoint with the required User-Agent header.

    Retries on throttling (429) and transient server errors with exponential
    backoff, honouring ``Retry-After``. Permanent failures (404, 403, malformed
    JSON) return immediately — retrying them only burns the rate budget.

    Returns ``None`` when every attempt fails. The caller decides what that
    means; this function never fabricates a result (CLAUDE.md 3.7).

    AUDIT-2026-05-13: the None-on-failure sentinel is the EXTERNAL-fetcher
    pattern in docs/audits/FALLBACK_AUDIT_2026-05-13.md §7.3. It should become
    a typed DataResult(UNAVAILABLE, ...) envelope once §8.1 lands; until that
    type exists, every path to None here is logged with URL, status and reason.
    """
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    for attempt in range(SEC_MAX_ATTEMPTS):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            status = resp.status_code
            if status in SEC_RETRY_STATUSES:
                if attempt == SEC_MAX_ATTEMPTS - 1:
                    log.error(
                        "SEC GET %s: HTTP %d after %d attempts — giving up",
                        url, status, SEC_MAX_ATTEMPTS,
                    )
                    return None
                wait = _retry_after_seconds(resp, attempt)
                if not _claim_retry_budget(wait):
                    log.error(
                        "SEC GET %s: HTTP %d and the %.0fs run-wide retry "
                        "budget is exhausted — not retrying",
                        url, status, SEC_RETRY_BUDGET_S,
                    )
                    return None
                log.warning(
                    "SEC GET %s: HTTP %d (attempt %d/%d) — retrying in %.1fs",
                    url, status, attempt + 1, SEC_MAX_ATTEMPTS, wait,
                )
                time_module.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            # Connection/timeout errors are transient; HTTP errors that reached
            # raise_for_status() are not in SEC_RETRY_STATUSES, so they are not.
            transient = not isinstance(e, requests.exceptions.HTTPError)
            if transient and attempt < SEC_MAX_ATTEMPTS - 1:
                wait = _retry_after_seconds(None, attempt)
                if not _claim_retry_budget(wait):
                    log.error(
                        "SEC GET %s: %s and the %.0fs run-wide retry budget is "
                        "exhausted — not retrying", url, e, SEC_RETRY_BUDGET_S,
                    )
                    return None
                log.warning(
                    "SEC GET %s: %s (attempt %d/%d) — retrying in %.1fs",
                    url, e, attempt + 1, SEC_MAX_ATTEMPTS, wait,
                )
                time_module.sleep(wait)
                continue
            log.warning("SEC GET failed for %s: %s", url, e)
            return None
        except Exception as e:
            log.warning("SEC GET failed for %s: %s", url, e)
            return None
    return None


def _cache_bucket() -> str | None:
    """GCS bucket for the CIK-map cache, or None when unconfigured."""
    b = os.environ.get("GCS_BUCKET")
    if b:
        return b
    project = os.environ.get("GCP_PROJECT_ID")
    return f"{project}-trading-data" if project else None


def _write_cik_cache(mapping: dict[str, str]) -> None:
    """Persist the CIK map so a throttled run has something to fall back to."""
    bucket = _cache_bucket()
    if not bucket:
        return
    try:
        import json as _json
        from google.cloud import storage as gcs
        payload = _json.dumps({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "mapping": mapping,
        })
        gcs.Client().bucket(bucket).blob(CIK_CACHE_BLOB).upload_from_string(
            payload, content_type="application/json"
        )
        log.info("Cached CIK map (%d tickers) to gs://%s/%s",
                 len(mapping), bucket, CIK_CACHE_BLOB)
    except Exception as e:
        # Cache write is best-effort: the live fetch already succeeded, so
        # failing here must not fail the run. ERROR rather than WARNING
        # because a failed write silently disarms the fallback this whole
        # change exists to provide — it needs to be noticed BEFORE the next
        # throttle, not discovered during it.
        log.error("Could not write CIK cache to gs://%s/%s (%s: %s) — the "
                  "throttle fallback will be stale or absent next run.",
                  bucket, CIK_CACHE_BLOB, type(e).__name__, e)


def _is_missing_blob(exc: Exception) -> bool:
    """True when the cache object simply isn't there yet, vs. a broken read.

    Imported lazily and with a name fallback so this works whether or not the
    google-cloud libraries are installed in the calling environment.
    """
    try:
        from google.api_core.exceptions import NotFound
        if isinstance(exc, NotFound):
            return True
    except Exception:
        pass  # google-cloud libs absent — fall back to the class name
    return type(exc).__name__ == "NotFound"


def _read_cik_cache() -> tuple[dict[str, str], float | None]:
    """Return (mapping, age_hours) from the cache, or ({}, None) if unusable.

    "Not there yet" and "the read is broken" both yield ({}, None), but they
    need very different operator responses — the first resolves itself on the
    next good run, the second never will — so they are logged differently.
    Collapsing them into one indistinguishable message is the ambiguity
    CLAUDE.md 3.7 forbids (see docs/audits/FALLBACK_AUDIT_2026-05-13.md §7.3).
    """
    bucket = _cache_bucket()
    if not bucket:
        log.info("No cache bucket configured; CIK-map fallback is unavailable.")
        return {}, None
    try:
        import json as _json
        from google.cloud import storage as gcs
        raw = gcs.Client().bucket(bucket).blob(CIK_CACHE_BLOB).download_as_text()
        obj = _json.loads(raw)
        mapping = obj.get("mapping") or {}
        fetched = obj.get("fetched_at")
        if not mapping or not fetched:
            log.error(
                "CIK cache at gs://%s/%s is malformed (mapping=%d entries, "
                "fetched_at=%r) — the throttle fallback is broken, not empty.",
                bucket, CIK_CACHE_BLOB, len(mapping), fetched,
            )
            return {}, None
        age_h = (
            datetime.now(timezone.utc) - datetime.fromisoformat(fetched)
        ).total_seconds() / 3600.0
        return mapping, age_h
    except Exception as e:
        if _is_missing_blob(e):
            log.info(
                "No CIK cache at gs://%s/%s yet — it is written on the next "
                "successful fetch.", bucket, CIK_CACHE_BLOB,
            )
            return {}, None
        log.error(
            "CIK cache read FAILED (%s: %s) — gs://%s/%s is unreadable, so the "
            "throttle fallback will NOT be available. This does not fix itself.",
            type(e).__name__, e, bucket, CIK_CACHE_BLOB,
        )
        return {}, None


def load_ticker_to_cik(user_agent: str) -> dict[str, str]:
    """Pull SEC's public ticker → CIK map.

    Response shape: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ... }
    Returns: {"AAPL": "0000320193", ...} — CIKs zero-padded to 10 digits.

    On fetch failure, falls back to the GCS cache **only** when it is fresher
    than CIK_CACHE_MAX_AGE_H, and says so at ERROR level. This is a declared,
    logged degradation with a measured age — not a silent substitution
    (CLAUDE.md 3.7). With no usable cache it returns {} and the caller aborts.
    """
    data = _http_get(TICKERS_URL, user_agent)
    if not data:
        cached, age_h = _read_cik_cache()
        if cached and age_h is not None and age_h <= CIK_CACHE_MAX_AGE_H:
            log.error(
                "SEC ticker→CIK fetch failed — PROCEEDING ON CACHED MAP: "
                "%d tickers, %.1fh old (limit %dh). Filings for tickers listed "
                "since that snapshot will be missed.",
                len(cached), age_h, CIK_CACHE_MAX_AGE_H,
            )
            return cached
        if cached:
            log.error(
                "SEC ticker→CIK fetch failed and cache is %.1fh old, past the "
                "%dh limit — refusing to use it.", age_h or -1, CIK_CACHE_MAX_AGE_H,
            )
        else:
            log.error("SEC ticker→CIK fetch failed and no usable cache exists.")
        return {}
    mapping: dict[str, str] = {}
    for entry in data.values():
        tk = (entry.get("ticker") or "").upper().strip()
        cik = entry.get("cik_str")
        if tk and cik is not None:
            mapping[tk] = f"{int(cik):010d}"
    log.info("Loaded SEC ticker→CIK map: %d tickers", len(mapping))
    if mapping:
        _write_cik_cache(mapping)
    return mapping


def fetch_submissions(ticker: str, cik: str, user_agent: str) -> list[dict]:
    """Return parsed `recent` submissions for one CIK.

    The `filings.recent` block is a parallel-arrays structure:
        accessionNumber: ['0001234567-25-...', ...]
        filingDate     : ['2026-04-24', ...]
        form           : ['8-K', '10-Q', ...]
        items          : ['1.01,7.01', '', ...]
        primaryDocument: ['avgo-20260424.htm', ...]

    We zip the arrays together into one dict per filing.
    """
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    data = _http_get(url, user_agent)
    if not data:
        return []
    recent = (data.get("filings") or {}).get("recent") or {}
    if not recent:
        return []

    n = len(recent.get("accessionNumber") or [])
    rows = []
    for i in range(n):
        rows.append(
            {
                "ticker": ticker.upper(),
                "cik": cik,
                "accession_number": (recent.get("accessionNumber") or [None])[i],
                "form": (recent.get("form") or [None])[i],
                "filing_date": (recent.get("filingDate") or [None])[i],
                "report_date": (recent.get("reportDate") or [None])[i] or None,
                "items_raw": (recent.get("items") or [""])[i] or "",
                "primary_doc": (recent.get("primaryDocument") or [None])[i],
            }
        )
    return rows


def filter_and_normalize(
    rows: list[dict], forms: set[str], since: date,
) -> pd.DataFrame:
    """Keep only target forms within the date window, normalize types."""
    keep = []
    for r in rows:
        form = r.get("form") or ""
        if form not in forms:
            continue
        fd = r.get("filing_date")
        if not fd:
            continue
        try:
            filing_d = pd.to_datetime(fd).date()
        except Exception:
            continue
        if filing_d < since:
            continue

        # Items is a comma-separated string in the response, e.g. "1.01,7.01".
        items_raw = r.get("items_raw", "") or ""
        items = [s.strip() for s in items_raw.split(",") if s.strip()]

        rd = r.get("report_date")
        try:
            report_d = pd.to_datetime(rd).date() if rd else None
        except Exception:
            report_d = None

        keep.append(
            {
                "ticker": r["ticker"],
                "cik": r["cik"],
                "accession_number": r["accession_number"],
                "form": form,
                "filing_date": filing_d,
                "report_date": report_d,
                "items": items or None,
                "primary_doc": (r.get("primary_doc") or "")[:200] or None,
            }
        )
    return pd.DataFrame(keep)


def _earnings_calendar_tickers(window_days: int) -> list[str]:
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []
    sql = """
        SELECT DISTINCT ticker
        FROM earnings_calendar
        WHERE earnings_date BETWEEN
            CURRENT_DATE - (:w || ' days')::interval AND
            CURRENT_DATE + (:w || ' days')::interval
        ORDER BY ticker
    """
    try:
        df = query_to_dataframe(sql, {"w": window_days})
    except Exception as e:
        log.warning("earnings_calendar lookup failed: %s", e)
        return []
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def main():
    parser = argparse.ArgumentParser(description="Fetch SEC EDGAR filings → Cloud SQL")
    parser.add_argument(
        "--tickers", default=None,
        help="Comma-separated tickers (overrides earnings_calendar resolution).",
    )
    parser.add_argument(
        "--forms", default=",".join(DEFAULT_FORMS),
        help=f"Comma-separated forms to keep (default: {','.join(DEFAULT_FORMS)}).",
    )
    parser.add_argument(
        "--since-days", type=int,
        default=int(os.environ.get("SEC_SINCE_DAYS", "14")),
        help="Only keep filings from the last N days (default: 14).",
    )
    parser.add_argument(
        "--earnings-window-days", type=int,
        default=int(os.environ.get("EARNINGS_WINDOW_DAYS", "7")),
        help="When --tickers is unset, pull filings for tickers reporting "
             "earnings within ±N days (default: 7).",
    )
    parser.add_argument(
        "--max-tickers", type=int,
        default=int(os.environ.get("MAX_TICKERS", "500")),
        help="Safety cap on total ticker count (default: 500).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and print without writing to DB.")
    args = parser.parse_args()

    user_agent = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    if user_agent == DEFAULT_USER_AGENT:
        log.warning(
            "SEC_USER_AGENT not set — using generic identifier. SEC requests "
            "you identify your organization + contact email."
        )

    forms = {f.strip().upper() for f in args.forms.split(",") if f.strip()}
    since = date.today() - timedelta(days=args.since_days)

    # Resolve ticker universe
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        from gcp.fetchers._watchlist import load_watchlist

        ec = _earnings_calendar_tickers(args.earnings_window_days)
        wl = load_watchlist()
        seen: set[str] = set(ec)
        tickers = list(ec) + [t for t in wl if t not in seen]
        log.info("Resolved %d tickers (%d earnings ±%dd ∪ %d watchlist)",
                 len(tickers), len(ec), args.earnings_window_days, len(wl))

    if not tickers:
        log.info("No tickers to process — exiting")
        return

    if len(tickers) > args.max_tickers:
        log.warning("Ticker count %d exceeds cap %d; truncating",
                    len(tickers), args.max_tickers)
        tickers = tickers[:args.max_tickers]

    # Backoff budget is per-run, not per-process.
    _reset_retry_budget()

    # Build CIK map (one shared call)
    ticker_to_cik = load_ticker_to_cik(user_agent)
    if not ticker_to_cik:
        log.error("Failed to load SEC ticker→CIK map; cannot proceed")
        sys.exit(1)

    log.info("SEC EDGAR Fetch Job")
    log.info("  Tickers   : %d", len(tickers))
    log.info("  Forms     : %s", sorted(forms))
    log.info("  Since     : %s (%d days back)", since, args.since_days)
    log.info("  SQL       : %s", "yes" if is_cloud_sql_configured() else "NO")

    all_filings: list[dict] = []
    skipped_no_cik = 0
    errors: list[str] = []

    for i, tk in enumerate(tickers):
        cik = ticker_to_cik.get(tk)
        if not cik:
            skipped_no_cik += 1
            continue
        if i > 0:
            time_module.sleep(SEC_RATE_DELAY_S)
        try:
            rows = fetch_submissions(tk, cik, user_agent)
            all_filings.extend(rows)
        except Exception as e:
            log.error("  ✗ %s (CIK %s): %s", tk, cik, e)
            errors.append(tk)

    log.info("Pulled %d raw filing rows (%d tickers without CIK)",
             len(all_filings), skipped_no_cik)

    if not all_filings:
        log.info("No filings fetched")
        return

    df = filter_and_normalize(all_filings, forms, since)
    if df.empty:
        log.info("No filings matched form/date filters")
        return

    df = df.drop_duplicates(subset=["cik", "accession_number"], keep="last")
    log.info("After filter+dedup: %d filings", len(df))

    if args.dry_run:
        with pd.option_context("display.max_rows", 30, "display.max_colwidth", 30):
            print(df.head(30).to_string(index=False))
        print(f"\n[dry-run] {len(df)} rows — not written to DB")
        return

    if is_cloud_sql_configured():
        n = upsert_dataframe(df, "sec_filings", ["cik", "accession_number"])
        log.info("✓ upserted %d rows to sec_filings", n)
        print(f"Persisted {n} sec_filings rows to Cloud SQL")
    else:
        log.warning("Cloud SQL not configured — skipping persist")

    if errors:
        log.warning("Failed (%d): %s", len(errors), errors[:20])


if __name__ == "__main__":
    main()
