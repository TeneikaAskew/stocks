#!/usr/bin/env python3
"""Report the actionable state of every open GitHub pull request.

The command deliberately uses GitHub's REST API rather than ``gh`` so a
public repository can be audited in a clean checkout without GitHub CLI
authentication.  Set ``GITHUB_TOKEN`` to raise rate limits and inspect a
private repository.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


API_ROOT = "https://api.github.com"


def _get(path: str, token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "stocks-open-pr-review",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{API_ROOT}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def review_open_prs(repo: str, token: str | None = None) -> list[dict[str, object]]:
    """Return open PRs with mergeability and check-run failures attached."""
    pulls = _get(f"/repos/{repo}/pulls?state=open&per_page=100", token)
    assert isinstance(pulls, list)
    report: list[dict[str, object]] = []
    for summary in pulls:
        number = summary["number"]
        detail = _get(f"/repos/{repo}/pulls/{number}", token)
        checks = _get(
            f"/repos/{repo}/commits/{detail['head']['sha']}/check-runs?per_page=100",
            token,
        )
        failed = [
            check["name"]
            for check in checks["check_runs"]
            if check["status"] == "completed"
            and check["conclusion"] not in {"success", "neutral", "skipped"}
        ]
        pending = [
            check["name"]
            for check in checks["check_runs"]
            if check["status"] != "completed"
        ]
        report.append(
            {
                "number": number,
                "title": detail["title"],
                "head": detail["head"]["ref"],
                "mergeable": detail["mergeable"],
                "mergeable_state": detail["mergeable_state"],
                "failed_checks": failed,
                "pending_checks": pending,
                "url": detail["html_url"],
            }
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="TeneikaAskew/stocks", help="GitHub owner/repo")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    try:
        report = review_open_prs(args.repo, os.getenv("GITHUB_TOKEN"))
    except urllib.error.HTTPError as error:
        print(f"GitHub API request failed: HTTP {error.code} {error.reason}")
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    for pr in report:
        failures = ", ".join(pr["failed_checks"]) or "none"
        pending = ", ".join(pr["pending_checks"]) or "none"
        print(
            f"#{pr['number']} {pr['title']}\n"
            f"  mergeable={pr['mergeable']} state={pr['mergeable_state']} "
            f"failed={failures} pending={pending}\n"
            f"  {pr['url']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
