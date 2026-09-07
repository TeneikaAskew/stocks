#!/usr/bin/env python3
"""Cloud Run Job: infra-drift detector with Discord alerting.

Daily scheduled check that compares deployed GCP state against the
repo's expected state for the failure modes that have caused the most
recent production incidents:

* **Image-pinning drift** — every Cloud Run Job has an image field. The
  `:latest` tag gets resolved to a specific digest at `gcloud run jobs
  update` time, NOT at execute time. So a job can keep running an
  outdated digest indefinitely while `:latest` advances. This was the
  root cause of `fetch-earnings-history` running pre-PR-#580 code for
  ~12 hours after the fix merged (incident 2026-06-01 F1).

* **Scheduler orphans** — Cloud Scheduler entries can point at Cloud Run
  Jobs that have been renamed or deprecated. A scheduler firing a
  non-existent job is a permanent quiet failure (e.g. F7 — p7b-next-
  candle-classifier had a stale failure issue from when its scheduler
  was still active).

The script aggregates findings and posts a compact summary to
`DISCORD_WEBHOOK_URL`. Exits 0 in all cases — the alerter is the
output, not the exit code; we don't want CR's auto-retry machinery
spamming when there IS drift, just the once-a-day Discord post.

Scheduled daily by `infra-drift-detector-daily` Cloud Scheduler entry.
Add new checks here as new incident families arise.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

PROJECT = os.environ.get("GCP_PROJECT", "adept-mountain-474619-d4")
REGION = os.environ.get("GCP_REGION", "us-east1")
IMAGE_TAG = "us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system:latest"


@dataclass
class Finding:
    severity: str       # 'HIGH' | 'MEDIUM' | 'LOW'
    check: str          # 'image-drift' | 'scheduler-orphan' | ...
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


def latest_image_digest() -> str:
    """Resolve the `trading-system:latest` tag to its current digest.

    Hits the Artifact Registry control-plane API via the Python SDK
    (gcloud CLI is not in the trading-system Docker image).

    Returns the bare sha256:... portion (no registry prefix)."""
    from google.cloud import artifactregistry_v1
    client = artifactregistry_v1.ArtifactRegistryClient()
    # parent: projects/<project>/locations/<region>/repositories/<repo>/packages/<package>
    parent = (f"projects/{PROJECT}/locations/{REGION}/"
              f"repositories/trading/packages/trading-system")
    # List tags; find the one named 'latest' and follow its .version.
    for tag in client.list_tags(parent=parent):
        if tag.name.rsplit("/", 1)[-1] == "latest":
            # tag.version is the FULL resource path; the last segment is the digest.
            digest = tag.version.rsplit("/", 1)[-1]
            if not digest.startswith("sha256:"):
                raise RuntimeError(f"unexpected digest format: {digest!r}")
            return digest
    raise RuntimeError(f"no 'latest' tag found at {parent}")


def resolve_tag_digest(tag: str) -> str:
    """Resolve any `trading-system:<tag>` to its current digest via
    Artifact Registry. Raises when the tag does not exist — the caller
    records that as an error rather than skipping the job (#835)."""
    from google.cloud import artifactregistry_v1
    client = artifactregistry_v1.ArtifactRegistryClient()
    parent = (f"projects/{PROJECT}/locations/{REGION}/"
              f"repositories/trading/packages/trading-system")
    for t in client.list_tags(parent=parent):
        if t.name.rsplit("/", 1)[-1] == tag:
            digest = t.version.rsplit("/", 1)[-1]
            if not digest.startswith("sha256:"):
                raise RuntimeError(f"unexpected digest format: {digest!r}")
            return digest
    raise RuntimeError(f"no tag {tag!r} at {parent}")


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


def latest_execution_image(job_name: str) -> str:
    """Return the resolved image (typically a digest reference) for the
    most-recent execution of `job_name`. Empty string if the job has
    never executed."""
    from google.cloud import run_v2
    client = run_v2.ExecutionsClient()
    parent = f"projects/{PROJECT}/locations/{REGION}/jobs/{job_name}"
    # Pull just the first page; we only need the most-recent execution.
    # page_size=1 makes the iterator stop after one element naturally.
    # NOTE: do NOT add a `finally: return ""` to "stop early" — `return`
    # in a `finally` block in Python silently overrides the surrounding
    # try-block's return value, which would make this function always
    # blank. Codex caught exactly that bug on PR #601.
    request = run_v2.ListExecutionsRequest(parent=parent, page_size=1)
    for exe in client.list_executions(request=request):
        try:
            return exe.template.containers[0].image
        except (AttributeError, IndexError):
            return ""
    return ""


def check_image_drift(report: Report) -> None:
    """For each CR Job, compare its pinned digest to current :latest.

    A job that holds the `:latest` TAG (not a digest) is itself fine —
    the displayed image string is just the tag. What we need is the
    DIGEST Cloud Run resolved at update time. The Cloud Run REST API
    exposes that via the metadata.annotations on the executed revision,
    but the `gcloud run jobs describe` shape varies. As a stable
    proxy: check the latest EXECUTION's resolved image digest.
    """
    try:
        latest = latest_image_digest()
    except Exception as e:
        report.errors.append(f"latest_image_digest: {e}")
        return

    try:
        jobs = list_run_jobs()
    except Exception as e:
        report.errors.append(f"list_run_jobs: {e}")
        return

    for j in jobs:
        if "trading-system" not in j["image"]:
            # Image doesn't share the trading-system base — skip.
            continue
        try:
            exec_image = latest_execution_image(j["name"])
        except Exception as e:
            report.errors.append(f"executions list {j['name']}: {e!s}"[:160])
            continue
        if not exec_image:
            continue  # job has never executed
        # exec_image is either `...@sha256:...` or a tag. A tag used to be
        # skipped ("can't compare directly"), which is exactly how
        # fetch-fred-rates ran on `:spx-removal-fred-20260516` for 3.5
        # months unnoticed (#835). Resolve it through Artifact Registry;
        # an unresolvable tag is an error, not a skip.
        m = re.search(r"@(sha256:[0-9a-f]+)", exec_image)
        via = ""
        if m:
            pinned = m.group(1)
        else:
            tag = _image_tag(exec_image) or "latest"
            try:
                pinned = resolve_tag_digest(tag)
            except Exception as e:
                report.errors.append(
                    f"{j['name']}: cannot resolve execution image tag "
                    f"{tag!r}: {e!s}"[:200])
                continue
            via = f" (tag `{tag}`)"
        if pinned != latest:
            report.add(
                severity="MEDIUM",
                check="image-drift",
                target=j["name"],
                detail=(f"pinned `{pinned[:19]}…`{via} ≠ latest `{latest[:19]}…` — "
                        "run `gcloud run jobs update --image=:latest` to re-pin"),
            )


def check_configured_image_tags(report: Report) -> None:
    """Flag any trading-system job whose SPEC pins a tag other than
    `latest`. deploy.sh deploys `${IMAGE}` (implicit :latest); a hand
    `gcloud run jobs update --image=...:sometag` leaves the spec on that
    tag until someone notices (#835: fetch-fred-rates on a May tag). This
    catches it from the spec alone, before or regardless of execution."""
    try:
        jobs = list_run_jobs()
    except Exception as e:
        report.errors.append(f"list_run_jobs: {e}")
        return
    for j in jobs:
        if "trading-system" not in j["image"]:
            continue
        tag = _image_tag(j["image"])
        if tag is None or tag == "latest":
            continue
        report.add(
            severity="MEDIUM",
            check="image-tag-pinned",
            target=j["name"],
            detail=(f"job spec pins `trading-system:{tag}`; deploy.sh deploys "
                    "`:latest` — run `./gcp/deploy.sh <target>` (or "
                    "`gcloud run jobs update --image=...:latest`) to converge"),
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

    check_image_drift(report)
    check_configured_image_tags(report)
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
