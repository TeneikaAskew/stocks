#!/bin/bash
# Phase 2 smoke test — Cloud Shell
#
# Runs each new/updated catalyst fetcher once, then queries Cloud SQL to
# confirm rows landed in each new table. Intended to be run immediately
# after phase2_deploy.sh while the schedulers haven't fired yet, so you
# can see the data appear from a single triggered run.
#
# Usage:
#   bash scripts/cloud_shell/phase2_smoke_test.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-adept-mountain-474619-d4}"
REGION="${REGION:-us-east1}"

gcloud config set project "$PROJECT_ID" --quiet

# ─────────────────────────────────────────────────────────────────────────
# 1. Trigger each new job (and the rebuilt fetch-news-sentiment)
#
# `gcloud run jobs execute --wait` blocks until the execution finishes so we
# get a sequential success/failure log. Failures print the execution URL
# you can click for full Cloud Logging output.
# ─────────────────────────────────────────────────────────────────────────

JOBS=(
    "fetch-news-sentiment"
    "fetch-news-sentiment-topics"
    "fetch-earnings-history"
    "fetch-sec-filings"
    "fetch-insider-transactions"
    "fetch-top-movers"
)

echo "═══════════════════════════════════════════════════════════════════════"
echo " Phase 2 smoke test — triggering ${#JOBS[@]} jobs"
echo "═══════════════════════════════════════════════════════════════════════"

for job in "${JOBS[@]}"; do
    echo
    echo "▶ Executing $job..."
    if gcloud run jobs execute "$job" --region "$REGION" --wait --quiet; then
        echo "  ✓ $job completed"
    else
        echo "  ✗ $job FAILED — see Cloud Logging for $job latest execution"
    fi
done

# ─────────────────────────────────────────────────────────────────────────
# 2. Verify rows landed in Cloud SQL via a small set of count queries.
# ─────────────────────────────────────────────────────────────────────────

echo
echo "═══════════════════════════════════════════════════════════════════════"
echo " Cloud SQL row counts (post-smoke-test)"
echo "═══════════════════════════════════════════════════════════════════════"

DB_USER=$(gcloud secrets versions access latest --secret=db-trading-user)
DB_PASS=$(gcloud secrets versions access latest --secret=db-trading-pass)
CONNECTION_NAME=$(gcloud secrets versions access latest --secret=cloud-sql-connection-name)
DB_NAME="trading"

if ! command -v cloud-sql-proxy &>/dev/null; then
    curl -sLo /tmp/cloud-sql-proxy \
        https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.linux.amd64
    chmod +x /tmp/cloud-sql-proxy
    PROXY_BIN=/tmp/cloud-sql-proxy
else
    PROXY_BIN=$(command -v cloud-sql-proxy)
fi

PROXY_PORT=15432
$PROXY_BIN --port $PROXY_PORT "$CONNECTION_NAME" >/tmp/cloud-sql-proxy.log 2>&1 &
PROXY_PID=$!
trap 'kill $PROXY_PID 2>/dev/null || true' EXIT

for i in {1..15}; do
    PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p $PROXY_PORT -U "$DB_USER" \
        -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1 && break
    sleep 1
done

PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p $PROXY_PORT -U "$DB_USER" -d "$DB_NAME" <<'SQL'
\echo
\echo '── news_sentiment (rebuilt fetcher) ──'
SELECT COUNT(*)                                                AS total_rows,
       COUNT(DISTINCT ticker)                                  AS unique_tickers,
       COUNT(*) FILTER (WHERE topics IS NOT NULL AND array_length(topics,1) > 0) AS rows_with_topics,
       COUNT(*) FILTER (WHERE overall_sentiment_label IS NOT NULL)              AS rows_with_overall_label,
       MAX(published_ts)                                       AS latest_article
FROM news_sentiment;

\echo
\echo '── news_sentiment topic distribution (top 10 today) ──'
SELECT unnest(topics) AS topic, COUNT(*) AS articles
FROM news_sentiment
WHERE published_ts >= NOW() - INTERVAL '24 hours'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;

\echo
\echo '── earnings_history (AV EARNINGS endpoint) ──'
SELECT COUNT(*)                                AS total_rows,
       COUNT(DISTINCT ticker)                  AS unique_tickers,
       MIN(reported_date)                      AS earliest,
       MAX(reported_date)                      AS latest
FROM earnings_history;

\echo
\echo '── sec_filings ──'
SELECT form, COUNT(*) AS rows, MAX(filing_date) AS most_recent
FROM sec_filings
GROUP BY form
ORDER BY rows DESC;

\echo
\echo '── 8-K filings with item codes (last 14 days) ──'
SELECT ticker, filing_date, items, primary_doc
FROM sec_filings
WHERE form = '8-K'
  AND filing_date >= CURRENT_DATE - 14
  AND items IS NOT NULL
ORDER BY filing_date DESC
LIMIT 20;

\echo
\echo '── insider_transactions ──'
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT ticker) AS unique_tickers,
       MAX(transaction_date) AS latest
FROM insider_transactions;

\echo
\echo '── top_movers_daily ──'
SELECT snapshot_date, category, COUNT(*) AS rows
FROM top_movers_daily
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

\echo
\echo '── market_data_daily earnings-window coverage ──'
SELECT COUNT(DISTINCT ticker) AS unique_tickers_today,
       COUNT(*) FILTER (WHERE date = CURRENT_DATE) AS rows_today
FROM market_data_daily
WHERE date >= CURRENT_DATE - 5;
SQL

kill $PROXY_PID 2>/dev/null || true
trap - EXIT

echo
echo "═══════════════════════════════════════════════════════════════════════"
echo " Smoke test complete."
echo
echo " What 'good' looks like:"
echo "   • news_sentiment   : rows_with_topics > 0  (was 0 before Phase 2a)"
echo "   • earnings_history : COUNT > 0              (table didn't exist before)"
echo "   • sec_filings      : at least one 8-K row   (8-Ks fire frequently)"
echo "   • insider_transactions : COUNT > 0          (table didn't exist before)"
echo "   • top_movers_daily : ~60 rows today         (3 categories × ~20 each)"
echo "   • market_data_daily: unique_tickers_today > 4  (was just SPY/IWM/QQQ/SPX)"
echo "═══════════════════════════════════════════════════════════════════════"
