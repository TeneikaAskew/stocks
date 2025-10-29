# Manual Workflow Fix Required

## Issue
The fetch-earnings-options workflow is missing the `actions: read` permission needed to fetch the original run date on re-runs.

## Required Change
Edit `.github/workflows/fetch-earnings-options.yml` at line 40 and add the `actions: read` permission:

```yaml
  fetch-earnings-options:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      actions: read  # ← Add this line
```

## Why This Fix Is Needed
When a workflow re-runs (attempt > 1), it tries to fetch the original run date using the GitHub API:
```bash
curl -s -H "Authorization: token ${{ github.token }}" \
  "https://api.github.com/repos/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

Without `actions: read` permission, this API call fails with a 403 error, causing the workflow to fall back to the current date instead of using the original run date.

## How to Apply
1. Go to https://github.com/TeneikaAskew/stocks/edit/main/.github/workflows/fetch-earnings-options.yml
2. Add `actions: read` under the permissions section (line 40)
3. Commit directly to main or create a PR

## Related Changes
The Python script fix (`load_active_tickers` respecting `target_date`) has already been committed and pushed to branch:
- `claude/debug-fetch-options-rundate-011CUbRvYfMTrzFbb2ixUcfz`

Both fixes are needed for the workflow to work correctly on re-runs.
