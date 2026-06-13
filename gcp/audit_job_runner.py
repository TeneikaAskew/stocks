"""Cloud Run Job: generic audit-script wrapper with GCS report + GitHub issue comment.

Replaces the GHA workflows that wrap `scripts.analysis.*` modules:
  - per-factor-walkforward.yml (weekly)
  - verify-brief-bias.yml (weekly)

Pattern:
  1. Compute defaults for date-window env vars (if unset).
  2. Subprocess into the target script (`python -m <module> <args>`).
  3. Treat the script's exit code per AUDIT_ALLOWED_EXIT_CODES (which lets
     "no data" exit codes like 3 pass without firing the failure alarm).
  4. Upload the report to GCS at a per-execution prefix.
  5. If AUDIT_TRACKING_ISSUE is set, post a phone-friendly comment to that
     GitHub issue using the gh-stocks-repo-pat secret (read at runtime from
     Secret Manager, never logged).

The failure-notifier Cloud Run Service catches CR Job non-zero exits via
its log sink and routes them to Discord, so no explicit alerting is needed
here — exit non-zero on a real failure and the alert path lights up.

Env vars (all optional except marked):

  AUDIT_SCRIPT_MODULE       required — e.g. 'scripts.analysis.per_factor_walkforward'
  AUDIT_SCRIPT_ARGS         space-separated extra args, e.g. '--folds 4'
  AUDIT_WINDOW_DAYS         compute --start = today-N, --end = today; default 30
                            (set to 0 to disable auto-window — caller must pass
                            window via AUDIT_SCRIPT_ARGS)
  AUDIT_REPORT_FLAG         the flag name used by the script for output path;
                            default '--output'. Set empty to skip report-flag.
  AUDIT_ALLOWED_EXIT_CODES  comma-separated; default '0' (success only).
                            E.g. '0,3' tolerates 'no data yet' exits.
  AUDIT_TRACKING_ISSUE      GitHub issue number for the summary comment.
                            Empty = skip comment.
  AUDIT_COMMENT_TITLE       Markdown H2 for the comment, e.g.
                            '🔁 Weekly walk-forward audit'.
  GCS_BUCKET                where to upload the report; default
                            ${PROJECT_ID}-trading-data
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def _gh_pat() -> str | None:
    """Pull the gh-stocks-repo-pat secret at runtime (never via env var, so
    it doesn't appear in `gcloud run jobs describe` output)."""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project = os.environ.get("PROJECT_ID", "adept-mountain-474619-d4")
        name = f"projects/{project}/secrets/gh-stocks-repo-pat/versions/latest"
        return client.access_secret_version(name=name).payload.data.decode()
    except Exception as e:
        log.warning("gh PAT fetch failed (%s) — skipping issue comment", e)
        return None


def _post_issue_comment(issue_num: str, body_md: str, repo: str = "TeneikaAskew/stocks") -> bool:
    pat = _gh_pat()
    if not pat:
        return False
    import json
    import urllib.request
    # GitHub issue comment limit is 65 KB; cap at 60 KB for safety.
    body_md = body_md[:60_000]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{issue_num}/comments",
        data=json.dumps({"body": body_md}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            log.info("comment posted to issue #%s (status=%s)", issue_num, r.status)
            return True
    except Exception as e:
        log.error("issue comment failed: %s", e)
        return False


def _gcs_upload(local_path: Path, bucket: str, blob_path: str) -> str:
    from google.cloud import storage as gcs
    gcs.Client().bucket(bucket).blob(blob_path).upload_from_filename(
        str(local_path), content_type="text/markdown",
    )
    uri = f"gs://{bucket}/{blob_path}"
    log.info("uploaded report -> %s", uri)
    return uri


def main() -> int:
    module = os.environ.get("AUDIT_SCRIPT_MODULE")
    if not module:
        log.error("AUDIT_SCRIPT_MODULE env var is required")
        return 2

    extra_args = (os.environ.get("AUDIT_SCRIPT_ARGS") or "").split()
    window_days = int(os.environ.get("AUDIT_WINDOW_DAYS", "30"))
    report_flag = os.environ.get("AUDIT_REPORT_FLAG", "--output")
    allowed = {int(c) for c in (os.environ.get("AUDIT_ALLOWED_EXIT_CODES") or "0").split(",") if c}
    issue_num = os.environ.get("AUDIT_TRACKING_ISSUE", "").strip()
    comment_title = os.environ.get("AUDIT_COMMENT_TITLE", f"📊 {module}")
    exec_id = os.environ.get("CLOUD_RUN_EXECUTION", f"audit-{int(datetime.now().timestamp())}")
    bucket = os.environ.get(
        "GCS_BUCKET",
        f"{os.environ.get('PROJECT_ID', 'adept-mountain-474619-d4')}-trading-data",
    )

    # Build argv
    argv = [sys.executable, "-m", module]
    if window_days > 0:
        end = date.today()
        start = end - timedelta(days=window_days)
        # Use --since for verify-brief-bias-style scripts, --start/--end for
        # walk-forward-style. Caller's AUDIT_SCRIPT_ARGS can override either.
        if "--since" not in extra_args and "--start" not in extra_args:
            # Heuristic: if the script uses --since (single arg), pass that;
            # otherwise default to --start/--end. Both scripts in this repo
            # use the --start/--end convention; verify-brief-bias is the
            # outlier and takes --since. Caller sets AUDIT_SCRIPT_ARGS to
            # use --since directly if needed.
            argv += ["--start", start.isoformat(), "--end", end.isoformat()]
    argv += extra_args

    out_path = Path(tempfile.mkdtemp(prefix="audit-")) / f"report-{exec_id}.md"
    if report_flag:
        argv += [report_flag, str(out_path)]

    log.info("running: %s", " ".join(argv))
    result = subprocess.run(argv, check=False)
    rc = result.returncode
    log.info("script exit=%s (allowed=%s)", rc, sorted(allowed))

    # Upload report (if produced) regardless of exit code
    uri = None
    if out_path.exists() and out_path.stat().st_size > 0:
        blob = f"audit-reports/{exec_id}/{out_path.name}"
        try:
            uri = _gcs_upload(out_path, bucket, blob)
        except Exception as e:
            log.error("GCS upload failed: %s", e)

    # Post issue comment if requested + report exists
    if issue_num and out_path.exists():
        body = (
            f"## {comment_title}\n\n"
            f"Run ID: `{exec_id}`\n"
        )
        if uri:
            body += f"Full report: `{uri}` (Cloud Storage)\n\n"
        body += "---\n\n"
        body += out_path.read_text(encoding="utf-8")
        _post_issue_comment(issue_num, body)

    return 0 if rc in allowed else (rc or 1)


if __name__ == "__main__":
    sys.exit(main())
