#!/usr/bin/env python3
"""
Handle GitHub Actions workflow failures by creating/updating issues and PRs.

This script is called by the reusable workflow handle-workflow-failure.yml
when any workflow fails. It captures failure details, extracts relevant logs,
and creates or updates issues and draft PRs for tracking fixes.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors."""
    pass


class WorkflowFailureHandler:
    """Handles workflow failures by creating/updating issues and PRs."""

    def __init__(self, token: str, repository: str, pr_token: Optional[str] = None):
        """
        Initialize the handler.

        Args:
            token: GitHub API token (for reading actions data)
            repository: Repository in format "owner/repo"
            pr_token: Optional PAT for creating PRs (uses token if not provided)
        """
        self.token = token
        self.pr_token = pr_token or token
        self.repository = repository
        self.owner, self.repo = repository.split('/')
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        # Headers for PR operations (uses PAT if provided)
        # Fine-grained tokens use "Bearer", classic tokens use "token"
        if self.pr_token.startswith("github_pat_"):
            pr_auth = f"Bearer {self.pr_token}"
        else:
            pr_auth = f"token {self.pr_token}"

        self.pr_headers = {
            "Authorization": pr_auth,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, use_pr_token: bool = False) -> Dict:
        """
        Make a GitHub API request.

        Args:
            method: HTTP method (GET, POST, PATCH)
            endpoint: API endpoint (without base URL)
            data: Optional request body
            use_pr_token: If True, use PR token for this request

        Returns:
            Response JSON

        Raises:
            GitHubAPIError: If request fails
        """
        url = f"{self.api_base}{endpoint}"
        headers = self.pr_headers if use_pr_token else self.headers

        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if response.status_code == 204:
                return {}

            response.raise_for_status()

            try:
                return response.json()
            except ValueError:
                return {}

        except requests.exceptions.HTTPError as e:
            error_detail = ""
            if e.response is not None:
                try:
                    error_json = e.response.json()
                    error_detail = f" Response body: {json.dumps(error_json)}"
                except ValueError:
                    error_detail = f" Response body: {e.response.text}"
            raise GitHubAPIError(f"GitHub API request failed: {e}.{error_detail}")
        except requests.exceptions.RequestException as e:
            raise GitHubAPIError(f"GitHub API request failed: {e}")

    def get_workflow_run_details(self, run_id: int) -> Dict:
        """Get workflow run details."""
        return self._make_request("GET", f"/repos/{self.owner}/{self.repo}/actions/runs/{run_id}")

    def get_workflow_jobs(self, run_id: int) -> List[Dict]:
        """Get all jobs for a workflow run."""
        response = self._make_request("GET", f"/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/jobs")
        return response.get('jobs', [])

    def get_job_logs(self, job_id: int) -> str:
        """
        Get logs for a specific job.

        Args:
            job_id: The job ID

        Returns:
            Job logs as string
        """
        url = f"{self.api_base}/repos/{self.owner}/{self.repo}/actions/jobs/{job_id}/logs"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException:
            return "Unable to fetch job logs"

    def extract_error_from_logs(self, logs: str, max_lines: int = 50) -> str:
        """
        Extract relevant error information from logs.

        Args:
            logs: Full log text
            max_lines: Maximum number of lines to extract

        Returns:
            Extracted error snippet
        """
        if not logs or logs == "Unable to fetch job logs":
            return logs

        lines = logs.split('\n')

        # Look for error indicators
        error_keywords = ['error', 'failed', 'exception', 'traceback', 'fatal']
        error_lines = []

        for i, line in enumerate(lines):
            if any(keyword in line.lower() for keyword in error_keywords):
                # Include context around error (5 lines before and after)
                start = max(0, i - 5)
                end = min(len(lines), i + 6)
                error_lines.extend(lines[start:end])

                if len(error_lines) >= max_lines:
                    break

        # If no specific errors found, return last N lines
        if not error_lines:
            error_lines = lines[-max_lines:]

        return '\n'.join(error_lines[:max_lines])

    def find_existing_issue(self, labels: List[str]) -> Optional[int]:
        """
        Find an existing open issue with matching labels.

        Args:
            labels: List of labels to match

        Returns:
            Issue number if found, None otherwise
        """
        # Convert labels to comma-separated string for API
        label_query = ','.join(labels)
        endpoint = f"/repos/{self.owner}/{self.repo}/issues?state=open&labels={label_query}&per_page=1"

        try:
            response = self._make_request("GET", endpoint)
            if response and len(response) > 0:
                return response[0]['number']
        except GitHubAPIError:
            pass

        return None

    def create_issue(self, title: str, body: str, labels: List[str]) -> int:
        """
        Create a new issue.

        Args:
            title: Issue title
            body: Issue body
            labels: List of labels

        Returns:
            Issue number
        """
        data = {
            "title": title,
            "body": body,
            "labels": labels
        }

        response = self._make_request("POST", f"/repos/{self.owner}/{self.repo}/issues", data)
        return response['number']

    def add_issue_comment(self, issue_number: int, body: str) -> None:
        """Add a comment to an existing issue."""
        data = {"body": body}
        self._make_request("POST", f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments", data)

    def create_branch(self, branch_name: str, sha: str) -> Tuple[bool, str]:
        """
        Create a new branch.

        Args:
            branch_name: Name of the branch to create
            sha: Commit SHA to branch from
        Returns:
            Tuple of (whether a new branch was created, resulting branch SHA)
        """
        data = {
            "ref": f"refs/heads/{branch_name}",
            "sha": sha
        }

        try:
            response = self._make_request("POST", f"/repos/{self.owner}/{self.repo}/git/refs", data, use_pr_token=True)
            return True, response.get('object', {}).get('sha', sha)
        except GitHubAPIError as e:
            # Branch might already exist
            if "Reference already exists" not in str(e):
                raise

            ref = self._make_request(
                "GET",
                f"/repos/{self.owner}/{self.repo}/git/refs/heads/{branch_name}",
                use_pr_token=True
            )
            return False, ref.get('object', {}).get('sha', sha)

    def create_placeholder_commit(self, branch_name: str, parent_sha: str) -> str:
        """
        Create an empty placeholder commit so the branch differs from base.

        Args:
            branch_name: Branch to update
            parent_sha: SHA of parent commit

        Returns:
            The SHA of the new commit
        """
        parent_commit = self._make_request(
            "GET",
            f"/repos/{self.owner}/{self.repo}/git/commits/{parent_sha}",
            use_pr_token=True
        )

        tree_sha = parent_commit.get('tree', {}).get('sha')
        if not tree_sha:
            raise GitHubAPIError("Unable to determine tree SHA for parent commit")

        commit_message = f"chore: track workflow failure for {branch_name}"

        new_commit = self._make_request(
            "POST",
            f"/repos/{self.owner}/{self.repo}/git/commits",
            {
                "message": commit_message,
                "tree": tree_sha,
                "parents": [parent_sha]
            },
            use_pr_token=True
        )

        new_sha = new_commit.get('sha')
        if not new_sha:
            raise GitHubAPIError("Failed to create placeholder commit")

        self._make_request(
            "PATCH",
            f"/repos/{self.owner}/{self.repo}/git/refs/heads/{branch_name}",
            {"sha": new_sha},
            use_pr_token=True
        )

        return new_sha

    def create_pull_request(self, title: str, body: str, head: str, base: str, draft: bool = True) -> int:
        """
        Create a pull request.

        Args:
            title: PR title
            body: PR body
            head: Head branch
            base: Base branch
            draft: Whether to create as draft PR

        Returns:
            PR number
        """
        data = {
            "title": title,
            "body": body,
            "head": f"{self.owner}:{head}",
            "base": base,
            "draft": draft
        }

        response = self._make_request("POST", f"/repos/{self.owner}/{self.repo}/pulls", data, use_pr_token=True)
        return response['number']

    def format_issue_body(
        self,
        workflow_name: str,
        run_url: str,
        run_number: int,
        event_name: str,
        branch: str,
        commit_sha: str,
        timestamp: str,
        failed_steps: List[str],
        error_logs: str,
        pr_number: Optional[int] = None
    ) -> str:
        """Format the issue body with all failure details."""

        failed_steps_text = '\n'.join([f"- {step}" for step in failed_steps]) if failed_steps else "- No specific step information available"

        pr_section = ""
        if pr_number:
            pr_section = f"\n### Linked Pull Request\nA draft PR has been created to track the fix: #{pr_number}\n"

        body = f"""## Workflow Failed

**Workflow:** {workflow_name}
**Run:** [#{run_number}]({run_url})
**Triggered by:** {event_name}
**Branch:** {branch}
**Commit:** {commit_sha}
**Time:** {timestamp}

### Failed Steps
{failed_steps_text}

### Error Logs (Last 50 lines)
```
{error_logs}
```
{pr_section}
### Action Required
Please investigate and fix the issue. This workflow runs automatically.

---
*This issue was automatically created by GitHub Actions*
"""
        return body

    def format_pr_body(
        self,
        workflow_name: str,
        issue_number: int,
        run_url: str,
        run_number: int,
        timestamp: str,
        error_summary: str,
        workflow_file: str
    ) -> str:
        """Format the PR body with fix tracking information."""

        body = f"""## Fix: {workflow_name} Failure

This PR is automatically created to track the fix for workflow failure.

### Related Issue
Closes #{issue_number}

### Failure Details
- **Workflow Run:** [#{run_number}]({run_url})
- **Failed At:** {timestamp}

### Error Summary
```
{error_summary}
```

### Next Steps
- [ ] Review workflow logs: [View Logs]({run_url})
- [ ] Identify root cause
- [ ] Implement fix in this PR
- [ ] Test fix locally
- [ ] Verify workflow passes

### Files to Check
Based on the workflow, these files may need attention:
- `.github/workflows/{workflow_file}`
- Related scripts and configuration files

---
*This PR was automatically created by GitHub Actions*
"""
        return body

    def handle_failure(
        self,
        workflow_name: str,
        failure_title: str,
        issue_labels: List[str],
        workflow_file: str,
        run_id: int,
        run_number: int,
        run_url: str,
        event_name: str,
        branch: str,
        commit_sha: str,
        create_pr: bool = True
    ) -> Tuple[int, Optional[int]]:
        """
        Handle a workflow failure by creating/updating issue and optionally creating PR.

        Args:
            workflow_name: Human-readable workflow name
            failure_title: Issue title
            issue_labels: List of labels for the issue
            workflow_file: Workflow filename
            run_id: Workflow run ID
            run_number: Workflow run number
            run_url: URL to workflow run
            event_name: Event that triggered the workflow
            branch: Branch name
            commit_sha: Commit SHA
            create_pr: Whether to create a PR

        Returns:
            Tuple of (issue_number, pr_number)
        """
        print(f"Handling failure for workflow: {workflow_name}")
        print(f"Run ID: {run_id}, Run Number: {run_number}")

        # Get workflow run details and jobs
        print("Fetching workflow run details...")
        jobs = self.get_workflow_jobs(run_id)

        # Find failed jobs and extract logs
        failed_steps = []
        error_logs = ""

        for job in jobs:
            if job.get('conclusion') == 'failure':
                print(f"Found failed job: {job.get('name')}")
                job_id = job.get('id')

                # Get job steps
                for step in job.get('steps', []):
                    if step.get('conclusion') == 'failure':
                        step_name = step.get('name')
                        failed_steps.append(f"Step: {step_name} (outcome: failure)")

                # Get logs for the first failed job
                if not error_logs:
                    print(f"Fetching logs for job {job_id}...")
                    logs = self.get_job_logs(job_id)
                    error_logs = self.extract_error_from_logs(logs)

        if not error_logs:
            error_logs = "Unable to extract error logs. Check the workflow run for details."

        # Get timestamp
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

        # Check for existing issue
        print(f"Checking for existing issue with labels: {issue_labels}")
        existing_issue = self.find_existing_issue(issue_labels)

        if existing_issue:
            print(f"Found existing issue #{existing_issue}, adding comment...")
            # Create update body
            update_body = self.format_issue_body(
                workflow_name, run_url, run_number, event_name,
                branch, commit_sha, timestamp, failed_steps, error_logs
            )
            self.add_issue_comment(existing_issue, f"### Additional Failure\n{update_body}")
            issue_number = existing_issue
        else:
            print("No existing issue found, creating new issue...")
            # Create new issue
            issue_body = self.format_issue_body(
                workflow_name, run_url, run_number, event_name,
                branch, commit_sha, timestamp, failed_steps, error_logs
            )
            issue_number = self.create_issue(failure_title, issue_body, issue_labels)
            print(f"Created issue #{issue_number}")

        pr_number = None
        if create_pr:
            # Create branch and PR
            branch_name = f"fix/workflow-{workflow_file.replace('.yml', '')}-{run_number}"
            print(f"Creating branch: {branch_name}")

            try:
                branch_created, branch_head_sha = self.create_branch(branch_name, commit_sha)

                if branch_created:
                    print("Creating placeholder commit so the PR can be opened...")
                    branch_head_sha = self.create_placeholder_commit(branch_name, branch_head_sha)

                # Create PR
                pr_title = f"Fix: {failure_title.replace('❌', '').strip()}"
                error_summary = error_logs[:500] + "..." if len(error_logs) > 500 else error_logs

                pr_body = self.format_pr_body(
                    workflow_name, issue_number, run_url, run_number,
                    timestamp, error_summary, workflow_file
                )

                print("Creating draft pull request...")
                pr_number = self.create_pull_request(pr_title, pr_body, branch_name, "main", draft=True)
                print(f"Created PR #{pr_number}")

                # Update issue with PR link if this is a new issue
                if not existing_issue:
                    pr_link = f"\n\n### Linked Pull Request\nA draft PR has been created to track the fix: #{pr_number}"
                    current_issue = self._make_request("GET", f"/repos/{self.owner}/{self.repo}/issues/{issue_number}")
                    updated_body = current_issue['body'] + pr_link
                    self._make_request("PATCH", f"/repos/{self.owner}/{self.repo}/issues/{issue_number}", {"body": updated_body})

            except GitHubAPIError as e:
                print(f"Warning: Failed to create PR: {e}")
                print("Issue was created/updated successfully")

        print(f"✓ Failure handling complete: Issue #{issue_number}" + (f", PR #{pr_number}" if pr_number else ""))
        return issue_number, pr_number


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Handle workflow failures")
    parser.add_argument('--workflow-name', required=True, help='Human-readable workflow name')
    parser.add_argument('--failure-title', required=True, help='Issue title')
    parser.add_argument('--issue-labels', required=True, help='Comma-separated issue labels')
    parser.add_argument('--workflow-file', required=True, help='Workflow filename')
    parser.add_argument('--run-id', required=True, type=int, help='Workflow run ID')
    parser.add_argument('--run-number', required=True, type=int, help='Workflow run number')
    parser.add_argument('--run-url', required=True, help='Workflow run URL')
    parser.add_argument('--event-name', required=True, help='Event that triggered workflow')
    parser.add_argument('--branch', required=True, help='Branch name')
    parser.add_argument('--commit-sha', required=True, help='Commit SHA')
    parser.add_argument('--no-pr', action='store_true', help='Do not create a PR')

    args = parser.parse_args()

    # Get GitHub token and repository from environment
    token = os.environ.get('GITHUB_TOKEN')
    pr_token = os.environ.get('PR_TOKEN')
    repository = os.environ.get('GITHUB_REPOSITORY')

    if not token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)

    if not repository:
        print("Error: GITHUB_REPOSITORY environment variable not set")
        sys.exit(1)

    # Parse labels
    labels = [label.strip() for label in args.issue_labels.split(',')]

    # Create handler and process failure
    try:
        handler = WorkflowFailureHandler(token, repository, pr_token)
        issue_number, pr_number = handler.handle_failure(
            workflow_name=args.workflow_name,
            failure_title=args.failure_title,
            issue_labels=labels,
            workflow_file=args.workflow_file,
            run_id=args.run_id,
            run_number=args.run_number,
            run_url=args.run_url,
            event_name=args.event_name,
            branch=args.branch,
            commit_sha=args.commit_sha,
            create_pr=not args.no_pr
        )

        print(f"\n✓ Success!")
        print(f"  Issue: #{issue_number}")
        if pr_number:
            print(f"  PR: #{pr_number}")

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
