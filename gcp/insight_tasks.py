"""Cloud Tasks enqueue for the insight-pipeline Cloud Run Job.

One implementation, three callers: the UI refresh endpoint
(`platform.api.routers.insights`), the top-N pre-warm job
(`gcp.auto_refresh_top_n`) and the daily scheduled batch
(`gcp.insight_pipeline_job`). Each used to carry its own copy of this
function and the copies had already drifted: only the API one forwarded
`as_of`, so a replay enqueued from either job silently ran against
today's data instead of the cutoff.

Why the env list matters
------------------------
A Cloud Run container override REPLACES the executing container's env
for that execution. The child therefore sees ONLY what is listed here
plus what is baked into the job definition. Two consequences:

* `INSIGHT_TRIGGERED_BY` must be forwarded explicitly. The daily
  Cloud Scheduler job passes it as an override (not baked into the job),
  and `_resolve_run_kind_and_update` reads it to decide `run_kind`. A
  child that does not inherit it records `manual_replay` instead of
  `scheduled`, which corrupts the audit trail in
  `insight_reports_history` without failing anything.
* `INSIGHT_AS_OF` must be forwarded or the child loses the replay
  cutoff entirely and reads live data.

The forwarding rules below mirror `_resolve_run_kind_and_update`'s
precedence exactly, so a fanned-out child resolves the same
`(allow_update, run_kind)` pair the parent would have resolved had it
run the ticker in-process. `tests/gcp/test_insight_tasks.py` asserts
that parity branch by branch.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PROJECT = "adept-mountain-474619-d4"
DEFAULT_REGION = "us-east1"
DEFAULT_QUEUE = "insight-pipeline-queue"


def build_child_env(
    run_id: str,
    ticker: str,
    *,
    as_of_iso: Optional[str] = None,
    triggered_by: Optional[str] = None,
    force_update: bool = False,
) -> list[dict[str, str]]:
    """Build the containerOverrides env list for one child execution.

    Split out from the enqueue so it can be unit-tested without a
    Cloud Tasks client. Order is stable to keep the encoded body
    deterministic and diffable in logs.
    """
    env: list[dict[str, str]] = [
        {"name": "INSIGHT_RUN_ID", "value": run_id},
        {"name": "INSIGHT_TICKER", "value": ticker},
    ]
    # Forwarded unconditionally: as_of is the data cutoff, not just a
    # run_kind input. Dropping it would silently widen the replay.
    if as_of_iso:
        env.append({"name": "INSIGHT_AS_OF", "value": as_of_iso})
    if triggered_by:
        env.append({"name": "INSIGHT_TRIGGERED_BY", "value": triggered_by})
    # `force_update` means update was EXPLICITLY requested (--update or
    # INSIGHT_UPDATE=true), not merely resolved to True. INSIGHT_UPDATE
    # outranks INSIGHT_AS_OF in _resolve_run_kind_and_update, and a
    # replay child already resolves to (True, 'replay_refresh') from the
    # forwarded cutoff alone. Forwarding the RESOLVED allow_update here
    # would therefore relabel every replay as 'manual_update'. Forward
    # the cause, not the effect.
    if force_update:
        env.append({"name": "INSIGHT_UPDATE", "value": "true"})
    return env


def enqueue_insight_task(
    run_id: str,
    ticker: str,
    *,
    as_of_iso: Optional[str] = None,
    triggered_by: Optional[str] = None,
    force_update: bool = False,
) -> bool:
    """Enqueue one Cloud Tasks message that runs `insight-pipeline` in
    on-demand mode for a single ticker.

    Returns True on a successful enqueue, False on any failure. The
    caller decides what to do about a False — every current caller
    falls back to running the ticker in-process and says so in the log,
    so a Cloud Tasks outage degrades throughput rather than dropping a
    report on the floor.
    """
    try:
        from google.cloud import tasks_v2  # type: ignore
        from google.api_core import exceptions as gexc  # type: ignore
    except ImportError:
        logger.error("google-cloud-tasks not installed - cannot enqueue %s", ticker)
        return False

    project = os.environ.get("GCP_PROJECT_ID", DEFAULT_PROJECT)
    region = os.environ.get("GCP_REGION", DEFAULT_REGION)
    queue = os.environ.get("INSIGHT_TASKS_QUEUE", DEFAULT_QUEUE)
    sa_email = os.environ.get(
        "INSIGHT_TASKS_SERVICE_ACCOUNT",
        f"trading-runner@{project}.iam.gserviceaccount.com",
    )
    job_url = (
        f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1/"
        f"namespaces/{project}/jobs/insight-pipeline:run"
    )

    try:
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(project, region, queue)
        body = json.dumps(
            {
                "overrides": {
                    "containerOverrides": [
                        {
                            "env": build_child_env(
                                run_id,
                                ticker,
                                as_of_iso=as_of_iso,
                                triggered_by=triggered_by,
                                force_update=force_update,
                            )
                        }
                    ]
                }
            }
        ).encode()
        task = {
            # A deterministic name makes create_task idempotent, which is
            # what lets an ambiguous failure be resolved rather than
            # guessed. Without it, a timeout AFTER the server accepted the
            # task reads as a failure, the caller runs the same run_id
            # in-process, and the queued child runs it too: two paid
            # pipelines, duplicate history rows, racing status writes.
            # run_id is a per-run UUID, so the name is never reused.
            "name": f"{parent}/tasks/insight-{run_id}",
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": job_url,
                "headers": {"Content-Type": "application/json"},
                "body": body,
                "oauth_token": {"service_account_email": sa_email},
            },
        }
        try:
            client.create_task(parent=parent, task=task)
            return True
        except gexc.AlreadyExists:
            # Someone already enqueued this exact run. Nothing to do, and
            # reporting failure here would trigger a duplicate in-process run.
            logger.warning("task for %s (%s) already enqueued", ticker, run_id)
            return True
        except Exception as first:
            # Ambiguous: the server may have accepted the task before the
            # error reached us. Ask again under the same name -- an
            # AlreadyExists answer proves the first attempt landed.
            logger.warning(
                "Cloud Tasks enqueue for %s failed (%s); re-checking by name",
                ticker, first,
            )
            try:
                client.create_task(parent=parent, task=task)
                return True
            except gexc.AlreadyExists:
                logger.warning(
                    "first enqueue for %s did land despite the error", ticker
                )
                return True
            except Exception as second:
                logger.error(
                    "Cloud Tasks enqueue failed for %s: %s (re-check: %s)",
                    ticker, first, second,
                )
                return False
    except Exception as exc:  # client construction, queue path, body build
        logger.error("Cloud Tasks enqueue failed for %s: %s", ticker, exc)
        return False
