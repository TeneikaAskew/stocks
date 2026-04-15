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

Runs on Python stdlib only (http.server + requests) so the GCP Docker image
does not need FastAPI/uvicorn added to requirements-gcp.txt.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import requests

logger = logging.getLogger("failure_notifier")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 15


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
    job_name = resource_labels.get("job_name") or "unknown-job"
    location = resource_labels.get("location") or os.environ.get("GCP_REGION", "us-east1")

    labels = log_entry.get("labels") or {}
    execution_name = (
        labels.get("run.googleapis.com/execution_name")
        or labels.get("execution_name")
        or ""
    )

    severity = log_entry.get("severity", "ERROR")
    timestamp = log_entry.get("timestamp") or datetime.now(timezone.utc).isoformat()
    insert_id = log_entry.get("insertId", "")

    message = log_entry.get("textPayload")
    if not message:
        json_payload = log_entry.get("jsonPayload") or {}
        message = (
            json_payload.get("message")
            or json_payload.get("error")
            or json.dumps(json_payload)[:2000]
            if json_payload
            else "(no message in log entry)"
        )

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
def build_discord_payload(details: dict[str, Any]) -> dict[str, Any]:
    snippet = details["message"]
    if len(snippet) > 800:
        snippet = snippet[:800] + "…"

    return {
        "username": "GCP Job Monitor",
        "embeds": [
            {
                "title": f"GCP job failed: {details['job_name']}",
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
                        "name": "Error",
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


def send_discord(webhook_url: str, payload: dict[str, Any]) -> None:
    """Post to Discord webhook. Mirrors gcp/premarket_brief.py:send_to_discord."""
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


def create_issue(repo: str, title: str, body: str, labels: list[str], token: str) -> int:
    url = f"{GITHUB_API}/repos/{repo}/issues"
    resp = requests.post(
        url,
        headers=_gh_headers(token),
        json={"title": title, "body": body, "labels": labels},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["number"]


def add_issue_comment(repo: str, issue_number: int, body: str, token: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(
        url, headers=_gh_headers(token), json={"body": body}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()


def format_issue_body(details: dict[str, Any]) -> str:
    return (
        f"## GCP Cloud Run Job Failed\n\n"
        f"**Job:** `{details['job_name']}`\n"
        f"**Execution:** `{details['execution_name'] or '(unknown)'}`\n"
        f"**Severity:** {details['severity']}\n"
        f"**Time:** {details['timestamp']}\n"
        f"**Project:** `{details['project_id']}`\n"
        f"**Region:** `{details['location']}`\n\n"
        f"### Error\n```\n{details['message']}\n```\n\n"
        f"### Links\n- [View execution logs in Cloud Console]({details['log_url']})\n\n"
        f"---\n"
        f"*Automatically created by `gcp/failure_notifier.py` from a Cloud Logging "
        f"Pub/Sub sink. Repeat failures append comments to this issue instead of "
        f"opening a new one.*\n"
    )


def create_or_update_github_issue(
    repo: str, token: str, details: dict[str, Any]
) -> tuple[int, bool]:
    """Create a new issue or comment on the existing one. Returns (number, created)."""
    job_name = details["job_name"]
    labels = ["gcp-job-failure", job_name, "automated"]
    body = format_issue_body(details)

    existing = find_existing_issue(repo, ["gcp-job-failure", job_name], token)
    if existing:
        add_issue_comment(repo, existing, f"### Additional failure\n\n{body}", token)
        logger.info("Appended comment to existing issue #%s", existing)
        return existing, False

    title = f"GCP job failed: {job_name}"
    number = create_issue(repo, title, body, labels, token)
    logger.info("Created issue #%s", number)
    return number, True


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

    # Safeguard against self-notification loops
    if details["job_name"] == "failure-notifier":
        logger.info("Ignoring self-notification.")
        return 204, ""

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


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        status, message = handle_notification(raw)
        self.send_response(status)
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
    port = port or int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info("failure-notifier listening on :%s", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    serve()
