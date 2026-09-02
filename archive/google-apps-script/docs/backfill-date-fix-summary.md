# Backfill Date Range Fix Summary

## Issue
When the backfill function was run on weekends or with after-hours run dates, the adjusted market run date could end up being after the end date, causing Yahoo Finance API errors: "Invalid input - start date cannot be after end date".

## Root Cause
1. The end date was calculated before adjusting the run date to market hours
2. When a run date was on a weekend (e.g., Saturday Aug 23), it would be adjusted to the next trading day (Monday Aug 25)
3. If today was still the weekend (e.g., Saturday Aug 24), the end date would be Aug 24
4. This created an invalid range where start date (Aug 25) > end date (Aug 24)

## Fix Applied
Reordered the date calculations in all backfill functions:

1. **First** adjust the run date to market hours using `EW_adjustToMarketHours()`
2. **Then** calculate the end date
3. **Finally** check if end date < adjusted run date, and if so, set end date = adjusted run date at market close (4:00 PM)

## Files Modified
- `/workspace/google-apps-script/src/09_HistoricalBackfill.js`
  - Fixed in `EW_processBackfillPosition()` (line 180-191)
  - Fixed in `EW_backfillSinglePosition()` (line 1130-1141) 
  - Fixed in `EW_testHistoricalBackfill()` (line 1767-1778)

## Example Scenario
- Run date: 2025-08-23 (Saturday) 
- Today: 2025-08-24 (Saturday)
- Before fix:
  - End date = Aug 24
  - Adjusted run date = Aug 25 (Monday 9:30 AM)
  - Result: Error - start > end
- After fix:
  - Adjusted run date = Aug 25 (Monday 9:30 AM)
  - End date = Aug 24, but adjusted to Aug 25 (Monday 4:00 PM)
  - Result: Valid range from Aug 25 9:30 AM to Aug 25 4:00 PM

## Testing
The fix ensures that:
1. Weekend run dates are properly moved to the next trading day
2. The end date is always >= the adjusted start date
3. Yahoo Finance API receives valid date ranges
4. Market hours are respected (9:30 AM - 4:00 PM ET)