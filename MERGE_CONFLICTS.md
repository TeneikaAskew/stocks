# Merge Conflict Explanation

When rebasing the feature branch onto the base commit (`7b2bdfbbdcb81c1afdd806d509245c5c584e20b0`), Git reports a conflict in `google-apps-script/src/16_WebApp.js` within the `formatTradeRecordsForWeb` helper.

## What Changed in the Feature Branch

The feature branch refactors `formatTradeRecordsForWeb` to normalize favorable and unfavorable arrays, derive peak profit, and compute a fallback drawdown value. In the refactor, the fallback drawdown is set with:

```javascript
const maxDrawdown = typeof trade.maxUnfavorableValue === 'number'
  ? trade.maxUnfavorableValue
  : Math.max(...unfavorable.filter(value => value !== null), 0);
```

This logic ensures every trade object emitted for the dashboard has a `maxDrawdown` field even when the raw data omits an explicit `maxUnfavorableValue`.

## What Changed in the Base Branch

After the feature branch diverged, the base branch received a bug fix that preserved negative drawdown percentages by taking the minimum (most negative) value from the `minUnfavorable` array instead of clamping to zero. That change updated the same block of code to use `Math.min(..., 0)` so losses would remain negative.

## Why Git Flags a Conflict

Both branches modify the same fallback clause in `formatTradeRecordsForWeb`: the feature branch reorganizes the helper and retains the `Math.max(..., 0)` fallback, while the base branch switches the fallback to `Math.min`. Because the surrounding lines differ across branches, Git cannot automatically decide which fallback to keep and raises a conflict for that hunk.

## Suggested Resolution

During the merge, keep the feature-branch restructuring of `formatTradeRecordsForWeb`, but adopt the base-branch logic for preserving negative drawdowns. The resulting code should look like:

```javascript
const maxDrawdown = typeof trade.maxUnfavorableValue === 'number'
  ? trade.maxUnfavorableValue
  : Math.min(...unfavorable.filter(value => value !== null), 0);
```

This preserves the refactor while ensuring the downstream profit-factor and risk metrics remain accurate.
