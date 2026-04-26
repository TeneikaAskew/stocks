#!/usr/bin/env bash
# Backfill historical_signals for one or more tickers, month-by-month.
#
# Why monthly: MarketAnalyzer.add_technical_indicators loads the entire
# range into a single DataFrame. A month is ~30k bars (ticker × 6.5h × 60
# × ~22 trading days) which keeps peak memory bounded. ON CONFLICT DO
# NOTHING means resuming a partial backfill is safe.
#
# Usage:
#   ./scripts/backfill_historical_signals.sh IWM 2015-01 2026-04
#   ./scripts/backfill_historical_signals.sh "IWM QQQ SPY" 2015-01 2026-04
set -euo pipefail

cd "$(dirname "$0")/.."

TICKERS="${1:-IWM QQQ SPY}"
START_YM="${2:-2015-01}"   # YYYY-MM inclusive
END_YM="${3:-2026-04}"     # YYYY-MM inclusive

# Load env (Cloud SQL connection name + creds)
set -a; source .env; set +a

next_month() {
  date -u -d "$1-01 +1 month" +%Y-%m
}

for SYMBOL in $TICKERS; do
  echo "=== ${SYMBOL} : ${START_YM} → ${END_YM} ==="
  YM="$START_YM"
  while [[ "$YM" < "$END_YM" || "$YM" == "$END_YM" ]]; do
    NEXT=$(next_month "$YM")
    START_DATE="${YM}-01"
    END_DATE="${NEXT}-01"
    echo "  ${SYMBOL} ${START_DATE} → ${END_DATE} (exclusive)"
    python3 scripts/run_historical_signals.py \
      --symbol "$SYMBOL" \
      --start-date "$START_DATE" \
      --end-date "$END_DATE" \
      2>&1 | grep -E 'INFO.*(loaded|voter|window trim|done:|inserted=|Error)' || true
    YM="$NEXT"
  done
done
echo "=== backfill complete ==="
