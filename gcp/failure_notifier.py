"""
GCP Cloud Run Job failure notifier.

Receives Pub/Sub push messages containing Cloud Logging entries for failed
Cloud Run Job executions, then:
  1. Posts a Discord message with the job name, timestamp, error snippet,
     and a clickable link to the Cloud Run execution logs.
  2. Creates (or updates) a GitHub issue labelled `gcp-job-failure,<job_name>`.
     Duplicate failures append a comment to the existing open issue instead of
     creating a new one.

Deployed as a Cloud Run Service (not Job) so Pub/Sub push can invoke it. Env
vars are injected via Secret Manager in gcp/deploy.sh — see deploy_notifier().

Uses http.server (stdlib) + requests and tenacity (both already in
requirements-gcp.txt), so no new dependencies are needed.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("failure_notifier")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 15
MAX_BODY = 1_048_576  # 1 MB — log entries are typically < 10 KB

# Bound both caller latency and background concurrency. A slow ADC discovery or
# streaming response must not hold up the original failure notification.
_FRESHNESS_IO = ThreadPoolExecutor(max_workers=2, thread_name_prefix="freshness-evidence")
_FRESHNESS_TIMEOUT = 5
_FRESHNESS_MAX_BYTES = 256 * 1024
_FRESHNESS_MAX_ENTRIES = 200
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _log_time(value: str):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Logging timestamp has no timezone")
    fraction = re.search(r"\.(\d+)(?:Z|[+-]\d\d:\d\d)$", value)
    # Preserve nanoseconds as well as differing fractional precision.
    nanos = int(fraction.group(1).ljust(9, "0")) if fraction else 0
    return parsed.replace(microsecond=0), nanos


def _bounded_freshness_io(operation):
    future = _FRESHNESS_IO.submit(operation)
    try:
        return future.result(timeout=_FRESHNESS_TIMEOUT)
    except TimeoutError:
        future.cancel()
        raise


def _freshness_token() -> str:
    """Use the managed ADC identity, with bounded discovery and refresh I/O."""
    from google.auth import default
    from google.auth.transport.requests import Request

    transport = Request()
    deadline = time.monotonic() + _FRESHNESS_TIMEOUT

    def bounded_request(*args, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Credential refresh deadline exceeded")
        kwargs["timeout"] = min(_FRESHNESS_TIMEOUT, remaining)
        try:
            response = transport(*args, **kwargs)
        except Exception as exc:
            # Avoid the SDK's retries/backoff extending the refresh deadline.
            raise RuntimeError("Credential transport unavailable") from exc
        if response.status >= 400:
            raise RuntimeError(f"Credential transport HTTP {response.status}")
        return response

    credentials, _ = default(
        scopes=["https://www.googleapis.com/auth/logging.read"], request=bounded_request,
    )
    credentials.refresh(bounded_request)
    if not credentials.token:
        raise RuntimeError("Credential refresh returned no token")
    return credentials.token


def _freshness_evidence(details: dict[str, Any], token: str) -> dict:
    """Read one bounded page for this execution, including its terminal output."""
    filters = ['resource.type="cloud_run_job"']
    for key, value in (
        ("resource.labels.project_id", details["project_id"]),
        ("resource.labels.location", details["location"]),
        ("resource.labels.job_name", details["job_name"]),
        ('labels."run.googleapis.com/execution_name"', details["execution_name"]),
    ):
        filters.append(f"{key}={json.dumps(value)}")
    filters.append(f"timestamp<={json.dumps(details['timestamp'])}")
    # The watchdog's task budget is one hour. A two-hour window allows
    # startup/terminal-log slack and avoids scanning the project's log history.
    cutoff = datetime.fromisoformat(details["timestamp"].replace("Z", "+00:00")) - timedelta(hours=2)
    filters.append(f"timestamp>={json.dumps(cutoff.isoformat())}")
    deadline = time.monotonic() + _FRESHNESS_TIMEOUT
    response = requests.post(
        "https://logging.googleapis.com/v2/entries:list",
        headers={"Authorization": f"Bearer {token}"},
        json={"resourceNames": [f"projects/{details['project_id']}"],
              "filter": " AND ".join(filters), "orderBy": "timestamp desc",
              "pageSize": _FRESHNESS_MAX_ENTRIES},
        timeout=_FRESHNESS_TIMEOUT, stream=True,
    )
    try:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if time.monotonic() > deadline:
                raise TimeoutError("Logging evidence deadline exceeded")
            if len(data) + len(chunk) > _FRESHNESS_MAX_BYTES:
                raise ValueError("Logging evidence exceeds size limit")
            data.extend(chunk)
        return json.loads(data)
    finally:
        response.close()


def _freshness_findings(payload: dict, details: dict[str, Any]) -> str:
    """Classify only a complete, single-task audit followed by intentional exit 1."""
    if not isinstance(payload, dict) or payload.get("nextPageToken"):
        raise ValueError("Incomplete Logging evidence")
    entries = payload.get("entries", [])
    if not isinstance(entries, list) or not entries or len(entries) >= _FRESHNESS_MAX_ENTRIES:
        raise ValueError("Missing or incomplete Logging entries")
    lines = []
    attempts = set()
    for entry in sorted(entries, key=lambda e: _log_time(e.get("timestamp", ""))):
        labels = entry.get("labels") or {}
        resource = entry.get("resource") or {}
        resource_labels = resource.get("labels") or {}
        if resource.get("type") != "cloud_run_job" or any(
            resource_labels.get(key) != details[value]
            for key, value in (("job_name", "job_name"), ("project_id", "project_id"),
                               ("location", "location"))
        ) or labels.get("run.googleapis.com/execution_name") != details["execution_name"]:
            raise ValueError("Logging evidence belongs to another execution")
        if _log_time(entry.get("timestamp", "")) > _log_time(details["timestamp"]):
            raise ValueError("Logging evidence follows the notification")
        if any(key in labels for key in ("run.googleapis.com/task_index", "run.googleapis.com/task_attempt")):
            attempts.add((labels.get("run.googleapis.com/task_index"),
                          labels.get("run.googleapis.com/task_attempt")))
        text = entry.get("textPayload")
        if text:
            lines.extend(_ANSI.sub("", text).splitlines())
        structured = entry.get("jsonPayload") or (entry.get("protoPayload") or {}).get("status") or {}
        if structured:
            structured_text = json.dumps(structured)
            if re.search(r"Traceback|timed out|deadline exceeded|terminated", structured_text, re.IGNORECASE):
                raise ValueError("Structured execution-error evidence present")
            if entry.get("jsonPayload") and entry.get("severity") in ("ERROR", "CRITICAL", "ALERT", "EMERGENCY"):
                raise ValueError("Structured execution-error evidence present")
    if len(attempts) != 1:
        raise ValueError("Ambiguous task or retry evidence")
    stripped = [line.strip() for line in lines]
    summaries = [line for line in stripped if line.startswith("Overall:")]
    exits = [line for line in stripped if line.startswith("Container called exit(")]
    if summaries != ["Overall: STALE"] or exits != ["Container called exit(1)."]:
        raise ValueError("No confirmed stale audit with intentional exit 1")
    if stripped.index("Overall: STALE") > stripped.index("Container called exit(1)."):
        raise ValueError("Exit precedes audit result")
    if any(re.search(r"Traceback \(most recent call last\)|timed out|deadline exceeded|terminated",
                     line, re.IGNORECASE) for line in stripped):
        raise ValueError("Execution-error evidence present")
    findings = []
    for index, line in enumerate(stripped):
        if re.search(r"\s(?:●\s+)?stale$", line):
            findings.append(line)
            next_index = index + 1
            while next_index < len(stripped) and stripped[next_index].startswith(("└─ writer-job:", "└─ details:")):
                findings[-1] += "\n" + stripped[next_index]
                next_index += 1
    if not findings:
        raise ValueError("Stale audit has no attributable findings")
    return "\n".join(findings)[:4000]


def enrich_freshness_failure(details: dict[str, Any]) -> dict[str, Any]:
    """Keep execution failures unless this exact run confirms an audit finding."""
    if details["job_name"] != "freshness-watchdog" or "has failed to complete" not in details["message"]:
        return details
    result = dict(details)
    stage = "Authentication"
    try:
        if not all(details.get(k) for k in ("project_id", "location", "execution_name", "timestamp")):
            raise ValueError("Missing execution identity")
        token = _bounded_freshness_io(_freshness_token)
        stage = "Audit evidence"
        payload = _bounded_freshness_io(lambda: _freshness_evidence(details, token))
        result["audit_findings"] = _freshness_findings(payload, details)
        result["audit_failed"] = True
    except Exception as exc:
        # Do not expose auth response bodies or tokens in alerts or logs.
        cause = type(exc).__name__
        if stage == "Audit evidence" and isinstance(exc, ValueError):
            cause = str(exc)
        elif isinstance(exc, requests.HTTPError) and exc.response is not None:
            cause = f"HTTP {exc.response.status_code}"
        reason = f"{stage} unavailable ({cause})"
        result["audit_classification_unavailable"] = reason
        logger.warning("Freshness audit classification unavailable (execution=%s): %s",
                       details["execution_name"], reason)
    return result

# Innermost-frame markers for SQLAlchemy/pg8000 connection-pool cleanup
# exceptions (pool_pre_ping/pool_recycle finding a dead socket and failing to
# gracefully close it). These are self-healing: the pool logs the exception at
# ERROR severity for visibility, then transparently opens a fresh connection
# on the next checkout. CLAUDE.md Rule 3.7 explicitly allows this as a
# "cleanup path... original error already propagated" — the job's own exit
# code, not this log line, is the source of truth for job success. Confirmed
# against signal-monitor-z4ctn (2026-07-14, issues #737/#738): the execution's
# succeededCount was 1 with no failedCount, and the monitor kept firing
# signals uninterrupted through the rest of the session.
_BENIGN_POOL_CLEANUP_MARKERS = (
    "in _close_connection",
    "in do_terminate",
    "Exception terminating connection",
)


def is_benign_pool_cleanup(message: str) -> bool:
    """True if a log message is SQLAlchemy pool-cleanup noise, not a real failure."""
    return any(marker in message for marker in _BENIGN_POOL_CLEANUP_MARKERS)


# ── Parsing ──────────────────────────────────────────────────────────────────
def parse_pubsub_envelope(body: bytes) -> dict[str, Any]:
    """Decode a Pub/Sub push envelope into the inner log entry dict.

    Pub/Sub push delivers: {"message": {"data": "<base64 json>", ...}, ...}
    The decoded data is a Cloud Logging LogEntry.
    """
    envelope = json.loads(body)
    message = envelope.get("message") or {}
    data_b64 = message.get("data")
    if not data_b64:
        return {}
    decoded = base64.b64decode(data_b64).decode("utf-8", errors="replace")
    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        return {"textPayload": decoded}


def extract_failure_details(log_entry: dict[str, Any]) -> dict[str, Any]:
    """Extract the fields we care about from a Cloud Logging entry."""
    resource_labels = (log_entry.get("resource") or {}).get("labels") or {}
    job_name = resource_labels.get("job_name") or ""
    location = resource_labels.get("location") or os.environ.get("GCP_REGION", "us-east1")

    labels = log_entry.get("labels") or {}
    execution_name = (
        labels.get("run.googleapis.com/execution_name")
        or labels.get("execution_name")
        or ""
    )

    if not job_name and execution_name and "-" in execution_name:
        # Executions.CancelExecution audit-log entries set
        # resource.labels.job_name to "" (present but empty, not absent)
        # even though the execution name is populated. Cloud Run execution
        # names are always "{job_name}-{5-char suffix}", so recover it from
        # there. Without this, these failures group under "unknown-job",
        # which 404s against the Cloud Run Jobs API in
        # _get_latest_execution_status, so reconcile_closures can never
        # close them even after the job recovers (#1177, #1178 stayed open
        # after the same-incident magnitude-engine issue, #1175, auto-closed
        # the same night).
        job_name = execution_name.rsplit("-", 1)[0]

    job_name = job_name or "unknown-job"

    severity = log_entry.get("severity", "ERROR")
    timestamp = log_entry.get("timestamp") or datetime.now(timezone.utc).isoformat()
    insert_id = log_entry.get("insertId", "")

    message = log_entry.get("textPayload")
    if not message:
        json_payload = log_entry.get("jsonPayload") or {}
        if json_payload:
            message = (
                json_payload.get("message")
                or json_payload.get("error")
                or json.dumps(json_payload)[:2000]
            )
        else:
            # Cloud Audit Log entries (e.g. the Jobs.RunJob "Execution ...
            # has failed to complete" record admitted by the sink filter
            # fix below) carry no textPayload/jsonPayload at all — the
            # failure text lives under protoPayload.status.message.
            proto_status = (log_entry.get("protoPayload") or {}).get("status") or {}
            message = proto_status.get("message") or "(no message in log entry)"

    project_id = os.environ.get("GCP_PROJECT_ID", "")
    if execution_name:
        log_url = (
            f"https://console.cloud.google.com/run/jobs/executions/details/"
            f"{location}/{execution_name}/logs?project={project_id}"
        )
    else:
        log_url = (
            f"https://console.cloud.google.com/run/jobs/details/{location}/{job_name}"
            f"/executions?project={project_id}"
        )

    return {
        "job_name": job_name,
        "execution_name": execution_name,
        "severity": severity,
        "timestamp": timestamp,
        "insert_id": insert_id,
        "message": str(message)[:4000],
        "log_url": log_url,
        "project_id": project_id,
        "location": location,
    }


# ── Discord ──────────────────────────────────────────────────────────────────
def _alert_title(details: dict[str, Any]) -> str:
    prefix = "Freshness Audit Failed" if details.get("audit_failed") else "GCP job failed"
    return f"{prefix}: {details['job_name']}"


def _repeat_heading(details: dict[str, Any]) -> str:
    return "Additional freshness audit failure" if details.get("audit_failed") else "Additional failure"


def build_discord_payload(details: dict[str, Any]) -> dict[str, Any]:
    """Format a parsed log entry as a Discord webhook payload (single embed).

    Truncates the error snippet to 800 chars so the embed stays within
    Discord's 6000-char total-embed limit even on huge tracebacks. The
    full message is preserved on the GitHub issue side via
    ``format_issue_body``.
    """
    snippet = details.get("audit_findings") or details["message"]
    if len(snippet) > 800:
        snippet = snippet[:800] + "…"

    payload = {
        "username": "GCP Job Monitor",
        "embeds": [
            {
                "title": _alert_title(details),
                "url": details["log_url"],
                "color": 0xE74C3C,
                "timestamp": details["timestamp"],
                "fields": [
                    {"name": "Job", "value": details["job_name"], "inline": True},
                    {"name": "Severity", "value": details["severity"], "inline": True},
                    {
                        "name": "Execution",
                        "value": details["execution_name"] or "(unknown)",
                        "inline": False,
                    },
                    {
                        "name": "Findings" if details.get("audit_failed") else "Error",
                        "value": f"```\n{snippet}\n```",
                        "inline": False,
                    },
                    {
                        "name": "View logs",
                        "value": f"[Open in Cloud Console]({details['log_url']})",
                        "inline": False,
                    },
                ],
                "footer": {"text": f"project={details['project_id']}"},
            }
        ],
    }
    fields = payload["embeds"][0]["fields"]
    if details.get("audit_failed"):
        fields.insert(-1, {"name": "Execution status", "value": details["message"][:800], "inline": False})
    elif details.get("audit_classification_unavailable"):
        fields.insert(-1, {
            "name": "Audit classification",
            "value": f"Audit classification unavailable: {details['audit_classification_unavailable']}",
            "inline": False,
        })
    return payload


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def send_discord(webhook_url: str, payload: dict[str, Any]) -> None:
    """Post to Discord webhook. Retries up to 3 times with exponential backoff."""
    resp = requests.post(webhook_url, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    logger.info("Discord notification sent (status=%s)", resp.status_code)


# ── GitHub issues ────────────────────────────────────────────────────────────
def _gh_headers(token: str) -> dict[str, str]:
    auth = f"Bearer {token}" if token.startswith("github_pat_") else f"token {token}"
    return {
        "Authorization": auth,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def find_existing_issue(repo: str, labels: list[str], token: str) -> int | None:
    """Return the number of an open issue matching ALL labels, else None."""
    label_q = ",".join(labels)
    url = f"{GITHUB_API}/repos/{repo}/issues?state=open&labels={label_q}&per_page=1"
    try:
        resp = requests.get(url, headers=_gh_headers(token), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        items = resp.json()
        if items:
            return items[0]["number"]
    except requests.RequestException as e:
        logger.warning("find_existing_issue failed: %s", e)
    return None


def find_all_open_issues(repo: str, labels: list[str], token: str) -> list[dict]:
    """Return ALL open issues matching ALL labels (paginated up to 100).

    Returns the raw dict per issue so callers can read both the number
    and the labels list (used by reconcile_closures to group by job_name).
    """
    label_q = ",".join(labels)
    url = f"{GITHUB_API}/repos/{repo}/issues?state=open&labels={label_q}&per_page=100"
    try:
        resp = requests.get(url, headers=_gh_headers(token), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("find_all_open_issues failed: %s", e)
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def close_issue(repo: str, issue_number: int, comment: str, token: str) -> None:
    """Add a closing comment then transition the issue to closed."""
    if comment:
        add_issue_comment(repo, issue_number, comment, token)
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    resp = requests.patch(
        url,
        headers=_gh_headers(token),
        json={"state": "closed"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def create_issue(repo: str, title: str, body: str, labels: list[str], token: str) -> int:
    """POST a new issue and return its number. Retries 3× on transient errors."""
    url = f"{GITHUB_API}/repos/{repo}/issues"
    resp = requests.post(
        url,
        headers=_gh_headers(token),
        json={"title": title, "body": body, "labels": labels},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["number"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def add_issue_comment(repo: str, issue_number: int, body: str, token: str) -> None:
    """POST a comment on an existing issue. Retries 3× on transient errors."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(
        url, headers=_gh_headers(token), json={"body": body}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()


def format_issue_body(details: dict[str, Any]) -> str:
    """Render a parsed log entry as the markdown body of a GitHub issue.

    Unlike ``build_discord_payload``, the full ``message`` is kept here
    — GitHub has a 65 KB body limit and the Pub/Sub payload upstream
    already truncates to 4000 chars in ``parse_pubsub_message``.
    """
    heading = "Freshness Audit Failed" if details.get("audit_failed") else "GCP Cloud Run Job Failed"
    findings = ""
    if details.get("audit_failed"):
        findings = f"### Findings\n```\n{details['audit_findings']}\n```\n\n"
    elif details.get("audit_classification_unavailable"):
        findings = f"**Audit classification unavailable:** {details['audit_classification_unavailable']}\n\n"
    error_heading = "Execution status" if details.get("audit_failed") else "Error"
    return (
        f"## {heading}\n\n"
        f"**Job:** `{details['job_name']}`\n"
        f"**Execution:** `{details['execution_name'] or '(unknown)'}`\n"
        f"**Severity:** {details['severity']}\n"
        f"**Time:** {details['timestamp']}\n"
        f"**Project:** `{details['project_id']}`\n"
        f"**Region:** `{details['location']}`\n\n"
        f"{findings}"
        f"### {error_heading}\n```\n{details['message']}\n```\n\n"
        f"### Links\n- [View execution logs in Cloud Console]({details['log_url']})\n\n"
        f"---\n"
        f"*Automatically created by `gcp/failure_notifier.py` from a Cloud Logging "
        f"Pub/Sub sink. Repeat failures append comments to this issue instead of "
        f"opening a new one.*\n"
    )


def create_or_update_github_issue(
    repo: str, token: str, details: dict[str, Any]
) -> tuple[int, bool]:
    """Create a new issue or comment on the existing one. Returns (number, created).

    Race-aware: when N notifier instances handle related Pub/Sub
    messages in parallel (multi-line traceback → multiple ERROR log
    entries → multiple Pub/Sub deliveries), they can all see "no open
    issue" in their `find_existing_issue` query before any of them
    creates one — producing N duplicate issues. After create, we
    re-query: if duplicates exist, we keep the lowest-numbered (the
    canonical) and close all higher-numbered ones with a comment
    pointing to the canonical. Pre-2026-05-15 this race was hitting
    fetch-market-data hard (6 issues opened in <1 minute on 5/14).
    """
    job_name = details["job_name"]
    labels = ["gcp-job-failure", job_name, "automated"]
    label_match = ["gcp-job-failure", job_name]
    body = format_issue_body(details)

    # Jitter: spread concurrent handlers across a 0-2s window so that the
    # second (and later) instances are more likely to find the issue already
    # created by the first when they call find_existing_issue below.
    time.sleep(random.uniform(0, 2))

    existing = find_existing_issue(repo, label_match, token)
    if existing:
        if job_name == "freshness-watchdog":
            # The label remains stable, so previously created issues get the
            # accurate title too; a subsequent execution error resets the title.
            resp = requests.patch(
                f"{GITHUB_API}/repos/{repo}/issues/{existing}",
                headers=_gh_headers(token), json={"title": _alert_title(details)},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        add_issue_comment(repo, existing, f"### {_repeat_heading(details)}\n\n{body}", token)
        logger.info("Appended comment to existing issue #%s", existing)
        return existing, False

    title = _alert_title(details)
    number = create_issue(repo, title, body, labels, token)

    # Race-condition dedupe: re-query and detect peers created in parallel.
    # Sleep 5s before re-querying so GitHub has time to index all concurrent
    # creates — without this delay the list endpoint can return only this
    # instance's own issue, making each instance believe it is the canonical.
    time.sleep(5)
    open_matches = find_all_open_issues(repo, label_match, token)
    open_numbers = sorted(int(i["number"]) for i in open_matches)
    if len(open_numbers) > 1:
        canonical = open_numbers[0]
        if number != canonical:
            try:
                close_issue(
                    repo,
                    number,
                    f"Auto-closing race-created duplicate of #{canonical} "
                    f"(both opened within seconds for the same `{job_name}` "
                    f"failure burst). Content moved to the canonical issue.",
                    token,
                )
                add_issue_comment(
                    repo,
                    canonical,
                    f"### {_repeat_heading(details)} (from race-created #{number}, now closed)\n\n{body}",
                    token,
                )
                logger.info(
                    "Race dedupe: closed #%s, content routed to canonical #%s",
                    number, canonical,
                )
                return canonical, False
            except requests.RequestException as e:
                # If the dedupe close fails (rare), keep both issues open
                # and log; the next reconcile pass will catch any stragglers.
                logger.warning(
                    "Race dedupe failed (kept both #%s and #%s): %s",
                    canonical, number, e,
                )

    logger.info("Created issue #%s", number)
    return number, True


# ── Reconcile: close issues for jobs that have since recovered ───────────────
def _get_latest_execution_status(
    job_name: str, project_id: str, region: str
) -> dict | None:
    """Query Cloud Run for the latest execution of a job.

    Returns dict with {name, completed, succeeded, completion_time}, or
    None if the job doesn't exist, auth fails, or there are no executions.
    Uses Application Default Credentials — the Cloud Run Service running
    failure-notifier already has roles/run.viewer in deploy_notifier().
    """
    if not project_id or not region or not job_name:
        return None
    try:
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import Request as GoogleRequest
        creds, _ = google_auth_default()
        creds.refresh(GoogleRequest())
        token = creds.token
    except Exception as e:
        logger.warning("ADC token fetch failed for reconcile: %s", e)
        return None

    url = (
        f"https://{region}-run.googleapis.com/v2/projects/{project_id}/"
        f"locations/{region}/jobs/{job_name}/executions?pageSize=1"
    )
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            logger.info("Reconcile: job %s does not exist (404)", job_name)
            return None
        resp.raise_for_status()
        execs = resp.json().get("executions", [])
        if not execs:
            return None
        latest = execs[0]
        succeeded = bool(latest.get("succeededCount", 0)) and not int(
            latest.get("failedCount", 0) or 0
        )
        return {
            "name": (latest.get("name") or "").split("/")[-1],
            "completed": "completionTime" in latest,
            "succeeded": succeeded,
            "completion_time": latest.get("completionTime", ""),
        }
    except requests.RequestException as e:
        logger.warning(
            "Cloud Run executions query failed for %s: %s", job_name, e,
        )
        return None


def reconcile_closures(
    repo: str, token: str, project_id: str, region: str,
) -> dict[str, int]:
    """Close open gcp-job-failure issues whose job's latest execution succeeded.

    Hourly cron-driven. Lists open issues with `gcp-job-failure` label,
    extracts the job_name from each issue's labels, queries Cloud Run for
    the latest execution, and closes the issue if the latest execution
    succeeded. This is the safety net that drains stale issues left over
    when a job recovers between failures (the common case — most fetcher
    failures are transient SSL / rate-limit / network blips).

    Returns a summary dict so the /reconcile endpoint can log + report.
    """
    summary = {
        "issues_inspected": 0,
        "jobs_inspected": 0,
        "closed": 0,
        "still_failing": 0,
        "unknown": 0,
    }
    open_issues = find_all_open_issues(repo, ["gcp-job-failure"], token)
    summary["issues_inspected"] = len(open_issues)

    by_job: dict[str, list[int]] = {}
    for issue in open_issues:
        labels = [l["name"] for l in issue.get("labels", [])]
        # job_name is the second label per create_or_update_github_issue;
        # find by exclusion of generic labels.
        job_name = next(
            (l for l in labels if l not in ("gcp-job-failure", "automated")),
            None,
        )
        if not job_name:
            continue
        by_job.setdefault(job_name, []).append(int(issue["number"]))

    summary["jobs_inspected"] = len(by_job)

    for job_name, issue_numbers in by_job.items():
        status = _get_latest_execution_status(job_name, project_id, region)
        if status is None:
            summary["unknown"] += 1
            continue
        if not (status["completed"] and status["succeeded"]):
            summary["still_failing"] += 1
            continue
        comment = (
            f"### Auto-closing — job recovered\n\n"
            f"Latest execution `{status['name']}` of `{job_name}` "
            f"succeeded at {status['completion_time']}. Closing this "
            f"issue automatically. If `{job_name}` fails again, a new "
            f"issue will be created.\n\n"
            f"_Closed by `gcp.failure_notifier.reconcile_closures` "
            f"hourly poll._"
        )
        for num in issue_numbers:
            try:
                close_issue(repo, num, comment, token)
                summary["closed"] += 1
                logger.info(
                    "Reconcile: closed #%s (job %s recovered)", num, job_name,
                )
            except requests.RequestException as e:
                logger.warning(
                    "Reconcile: close issue #%s failed: %s", num, e,
                )
    return summary


# ── Handler ──────────────────────────────────────────────────────────────────
def handle_notification(body: bytes) -> tuple[int, str]:
    """Process one Pub/Sub push. Returns (http_status, message)."""
    try:
        log_entry = parse_pubsub_envelope(body)
    except (ValueError, json.JSONDecodeError) as e:
        logger.error("Failed to parse envelope: %s", e)
        return 400, "invalid envelope"

    if not log_entry:
        logger.info("Empty log entry; acking.")
        return 204, ""

    details = extract_failure_details(log_entry)

    # Belt-and-suspenders self-loop guard. Primary protection is the sink
    # filter (resource.type="cloud_run_job" excludes this service's logs since
    # it runs as a Cloud Run Service). This catches the edge case where a Job
    # named "failure-notifier" is accidentally created.
    if details["job_name"] == "failure-notifier":
        logger.info("Ignoring self-notification.")
        return 204, ""

    if is_benign_pool_cleanup(details["message"]):
        logger.info(
            "Suppressing benign pool-cleanup log line (job=%s, execution=%s)",
            details["job_name"], details["execution_name"],
        )
        return 204, ""

    details = enrich_freshness_failure(details)

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    gh_token = os.environ.get("GITHUB_PAT")
    gh_repo = os.environ.get("GITHUB_REPO")

    errors: list[str] = []

    if webhook:
        try:
            send_discord(webhook, build_discord_payload(details))
        except requests.RequestException as e:
            errors.append(f"discord: {e}")
            logger.error("Discord post failed: %s", e)
    else:
        logger.warning("DISCORD_WEBHOOK_URL not set; skipping Discord.")

    if gh_token and gh_repo:
        try:
            create_or_update_github_issue(gh_repo, gh_token, details)
        except requests.RequestException as e:
            errors.append(f"github: {e}")
            logger.error("GitHub issue creation failed: %s", e)
    else:
        logger.warning("GITHUB_PAT/GITHUB_REPO not set; skipping issue.")

    if errors:
        return 500, "; ".join(errors)
    return 204, ""


def handle_reconcile() -> tuple[int, str]:
    """Run the close-on-success reconciler. Returns (http_status, json_body)."""
    gh_token = os.environ.get("GITHUB_PAT")
    gh_repo = os.environ.get("GITHUB_REPO")
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    region = os.environ.get("GCP_REGION", "us-east1")
    if not gh_token or not gh_repo:
        return 503, json.dumps({"error": "GITHUB_PAT or GITHUB_REPO not set"})
    summary = reconcile_closures(gh_repo, gh_token, project_id, region)
    logger.info("Reconcile summary: %s", summary)
    return 200, json.dumps(summary)


class Handler(BaseHTTPRequestHandler):
    """HTTP routes:

    * ``POST /``           — Pub/Sub push delivery (single log entry → Discord + GitHub issue)
    * ``POST /reconcile``  — Cloud Scheduler trigger; closes issues whose
                              latest job execution has since succeeded
    * ``GET  /``           — health check (200 OK)
    """

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") == "/reconcile":
            status, body = handle_reconcile()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if body:
                self.wfile.write(body.encode())
            return
        length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        raw = self.rfile.read(length) if length else b""
        status, message = handle_notification(raw)
        self.send_response(status)
        if message:
            self.send_header("Content-Type", "text/plain")
        self.end_headers()
        if message:
            self.wfile.write(message.encode())

    def do_GET(self):  # noqa: N802
        # Health check
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, fmt, *args):  # noqa: A003
        logger.info("%s - %s", self.address_string(), fmt % args)


def serve(port: int | None = None) -> None:
    """Start the HTTP server. Cloud Run injects ``PORT``; default 8080 for local dev."""
    port = port or int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info("failure-notifier listening on :%s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    serve()
