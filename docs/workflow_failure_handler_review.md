# Workflow Failure Handler Review (2025-02-17)

## Overview
A review of `scripts/handle_workflow_failure.py` confirms the latest integration adds:
- detailed markdown summaries for issues and pull requests,
- automatic branch creation with placeholder commits when a new draft PR is needed, and
- improved GitHub API error handling for token/permission mismatches.

Compilation succeeds with `python -m compileall scripts/handle_workflow_failure.py`, indicating there are no syntax errors in the committed version.

## Observed Behaviour
- **Issue Comments:** When a labelled issue already exists, the handler posts an additional comment that includes full workflow metadata and job snippets.
- **Draft Pull Requests:** New branches are created from the failing commit SHA and receive a placeholder commit so GitHub can open a draft PR even if no code fix is ready yet.
- **Error Extraction:** The handler stores the first log snippet that contains typical error keywords (`error`, `failed`, `exception`, `traceback`, `fatal`) and defaults to the last 50 lines when no keyword match is found.

## Follow-up Tasks
1. **Improve Re-run Updates**  
   When a draft PR already exists for the workflow failure branch, the script skips creating an additional placeholder commit. Add logic to push a fresh marker commit (or update the PR description) so maintainers can easily see repeated failures.
2. **Enhance Log Extraction Controls**  
   Allow configuration of `max_lines` and the error keyword list via environment variables or CLI arguments. This makes the handler usable across workflows with different logging patterns.
3. **Add Automated Tests**  
   Introduce unit tests for the markdown formatting helpers (`build_failure_summary`, `format_issue_body`, `format_pr_body`) to prevent regressions in the generated triage content.
4. **Support Richer Issue Linking**  
   Update the issue body to include the job step URLs (when available) so responders can jump directly to the failing command without opening the full log first.

Documenting these tasks will guide the next iteration of workflow-failure automation improvements.
