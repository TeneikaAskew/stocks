#!/usr/bin/env python3
"""Cloud Run Job: infra-drift detector with Discord alerting.

Daily scheduled check that compares deployed GCP state against the
repo's expected state for the failure modes that have caused the most
recent production incidents:

* **Floating images** — a job whose spec names an image TAG runs
  whatever that tag holds at its next execution: Cloud Run resolves the
  tag at each execution, not at `gcloud run jobs update` time (measured
  2026-09-25, #1171). So every build of the tag reaches the job, whatever
  target was deployed. `gcp/deploy.sh` deploys every job by digest and
  refuses to build while a job names the tag the build moves;
  `./gcp/deploy.sh pin-floating` converts one. A job pinned by digest runs
  exactly that digest, and moves when its own target is deployed.

* **Scheduler orphans** — Cloud Scheduler entries can point at Cloud Run
  Jobs that have been renamed or deprecated. A scheduler firing a
  non-existent job is a permanent quiet failure (e.g. F7 — p7b-next-
  candle-classifier had a stale failure issue from when its scheduler
  was still active).

The script aggregates findings and posts a compact summary to
`DISCORD_WEBHOOK_URL`. Exits 0 in all cases — the alerter is the
output, not the exit code; we don't want CR's auto-retry machinery
spamming when there IS drift, just the once-a-day Discord post.

Scheduled daily by the `audit-infra-drift-daily` Cloud Scheduler entry
(`30 12 * * *`, `America/New_York` — verified live 2026-09-06).
Add new checks here as new incident families arise.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

PROJECT = os.environ.get("GCP_PROJECT", "adept-mountain-474619-d4")
REGION = os.environ.get("GCP_REGION", "us-east1")


@dataclass
class Finding:
    severity: str       # 'HIGH' | 'MEDIUM' | 'LOW'
    check: str          # 'image-floating' | 'scheduler-orphan' | ...
    target: str         # the job/scheduler/resource name
    detail: str         # human-readable diagnosis


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, *args, **kw) -> None:
        self.findings.append(Finding(*args, **kw))

    def summary(self) -> str:
        if not self.findings and not self.errors:
            return "✅ infra-drift-detector: no findings"
        by_sev: dict[str, list[Finding]] = {}
        for f in self.findings:
            by_sev.setdefault(f.severity, []).append(f)
        lines = [f"⚠️ infra-drift-detector: {len(self.findings)} finding(s)"]
        for sev in ("HIGH", "MEDIUM", "LOW"):
            for f in by_sev.get(sev, []):
                lines.append(f"**[{sev}] {f.check}** · `{f.target}`\n  {f.detail}")
        if self.errors:
            lines.append(f"\n_check-execution errors: {len(self.errors)}_")
            for e in self.errors[:5]:
                lines.append(f"  · {e}")
        return "\n".join(lines)


def _image_tag(image: str) -> str | None:
    """`...:tag` → 'tag'; digest refs and untagged images → None."""
    if "@" in image:
        return None
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return None
    return last.rsplit(":", 1)[-1]


def list_run_jobs() -> list[dict]:
    """Return [{name, image}] for every Cloud Run Job in REGION via the
    google-cloud-run Python SDK."""
    from google.cloud import run_v2
    client = run_v2.JobsClient()
    parent = f"projects/{PROJECT}/locations/{REGION}"
    rows: list[dict] = []
    for job in client.list_jobs(parent=parent):
        name = job.name.rsplit("/", 1)[-1]
        # job.template.template.containers[0].image is the configured image.
        image = ""
        try:
            image = job.template.template.containers[0].image
        except (AttributeError, IndexError):
            pass
        rows.append({"name": name, "image": image})
    return rows


def list_schedulers() -> list[dict]:
    """Return [{name, target_job, uri}] for every Cloud Scheduler entry
    in REGION via the google-cloud-scheduler Python SDK."""
    from google.cloud import scheduler_v1
    client = scheduler_v1.CloudSchedulerClient()
    parent = f"projects/{PROJECT}/locations/{REGION}"
    rows: list[dict] = []
    for s in client.list_jobs(parent=parent):
        name = s.name.rsplit("/", 1)[-1]
        # CR-Job-firing schedulers target run.googleapis.com/v2/.../jobs/<job-name>:run
        uri = ""
        if s.http_target:
            uri = s.http_target.uri or ""
        m = re.search(r"/jobs/([^:/]+)", uri)
        target_job = m.group(1) if m else ""
        # ENABLED / PAUSED / DISABLED / UPDATE_FAILED — read by
        # check_scheduler_state (#833). The enum's .name is the stable
        # string across SDK versions; fall back to str() if it is not one.
        state = getattr(s.state, "name", None) or str(s.state)
        rows.append({"name": name, "target_job": target_job, "uri": uri,
                     "state": state})
    return rows


def check_floating_images(report: Report) -> None:
    """Flag every trading-system job whose SPEC names an image tag.

    Such a job runs whatever the tag holds at its next execution, so every
    build of the tag reaches it (#1171). A job pinned by digest runs exactly
    that digest and is not drift, even when a newer build exists: it moves
    when its own target is deployed.

    This replaces the comparison of each job's last execution with its tag's
    current digest. That assumed a tag resolves once, at update time, so it
    stayed silent on a floating job whose last run matched the tag, and it
    told the operator to re-pin a pinned job to a tag, which floats it
    again; a research job pinned by digest was compared with `:latest` and
    sent to the main image, which lacks the research stack.
    """
    try:
        jobs = list_run_jobs()
    except Exception as e:
        report.errors.append(f"list_run_jobs: {e}")
        return
    for j in jobs:
        if not j["image"]:
            report.errors.append(f"{j['name']}: no image in the job spec, so it "
                                 "cannot be ruled out as floating")
            continue
        if "trading-system" not in j["image"] or "@sha256:" in j["image"]:
            continue
        tag = _image_tag(j["image"]) or "latest"
        report.add(
            severity="MEDIUM",
            check="image-floating",
            target=j["name"],
            detail=(f"job spec names `trading-system:{tag}`, which Cloud Run resolves "
                    "at each execution, so every build of that tag reaches this job; "
                    "run `./gcp/deploy.sh pin-floating` (#1171)"),
        )


def check_scheduler_orphans(report: Report) -> None:
    """Any scheduler whose `target_job` doesn't exist as a CR Job."""
    try:
        schedulers = list_schedulers()
        jobs = {j["name"] for j in list_run_jobs()}
    except Exception as e:
        report.errors.append(f"scheduler/jobs list: {e}")
        return
    for s in schedulers:
        if not s["target_job"]:
            continue  # not a CR-Job-firing scheduler
        if s["target_job"] not in jobs:
            report.add(
                severity="HIGH",
                check="scheduler-orphan",
                target=s["name"],
                detail=f"scheduler fires `{s['target_job']}` but no such CR Job exists",
            )


def check_scheduler_state(report: Report) -> None:
    """Any scheduler not ENABLED is drift: deploy.sh's `_schedule` creates
    every entry ENABLED and records no pause, so a live PAUSED entry is
    either an unrecorded decision or an accident (#833:
    signal-quality-report-hourly sat PAUSED from 2026-05-05 with nothing
    in the repo saying why). Resume it, or retire it in deploy.sh."""
    try:
        schedulers = list_schedulers()
    except Exception as e:
        report.errors.append(f"scheduler list: {e}")
        return
    for s in schedulers:
        state = s.get("state")
        if state is None:
            # Never assume ENABLED: an older listing shape without state
            # would otherwise pass every paused scheduler silently.
            report.errors.append(f"{s['name']}: scheduler listing carried no state")
            continue
        if state != "ENABLED":
            report.add(
                severity="MEDIUM",
                check="scheduler-paused",
                target=s["name"],
                detail=(f"scheduler is {state} live; deploy.sh's _schedule would "
                        "recreate it ENABLED — resume it, or retire it in deploy.sh "
                        "with the reason recorded"),
            )


def post_to_discord(message: str) -> bool:
    """Post `message` to DISCORD_WEBHOOK_URL. Returns True on 2xx.

    Truncates to Discord's 2000-char limit. Logs and returns False on
    any non-2xx (don't raise — the alert is observability, not a
    correctness gate)."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        log.warning("DISCORD_WEBHOOK_URL not set — printing instead\n%s", message)
        return True
    body = message[:1900] + ("\n…(truncated)" if len(message) > 1900 else "")
    try:
        r = requests.post(webhook, json={"content": body}, timeout=15)
        if not r.ok:
            log.error("Discord post failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except requests.RequestException as e:
        log.error("Discord post raised: %s", e)
        return False


def main() -> int:
    report = Report()
    log.info("infra-drift-detector starting (project=%s region=%s)", PROJECT, REGION)

    check_floating_images(report)
    check_scheduler_orphans(report)
    check_scheduler_state(report)

    summary = report.summary()
    log.info("=== summary ===\n%s", summary)
    post_to_discord(summary)

    # Exit 0 always: the alerter is the output. Failure-notifier would
    # double-spam if we exited 1 on findings, since those findings are
    # the expected daily noise level.
    return 0


if __name__ == "__main__":
    sys.exit(main())
