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
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# Ceiling on how many tickers either producer may hand to this queue in one
# run. It lives here, not in a caller, because it bounds a shared resource:
# every enqueued ticker becomes its own Cloud Run execution, and `jobs.run`
# returns an Operation the moment the execution is created, so the queue's
# max-concurrent-dispatches frees its slot immediately and N enqueues become
# N concurrent pipelines against one Vertex quota. That is the 429 pressure
# this module's PR started from.
#
# Both producers read THIS object. `insight_pipeline_job` runs an oversized
# batch in-process instead; `auto_refresh_top_n` has no in-process path and
# clamps its top-N, logging what it dropped.
FANOUT_MAX_TICKERS = 5

DEFAULT_PROJECT = "adept-mountain-474619-d4"
DEFAULT_REGION = "us-east1"
DEFAULT_QUEUE = "insight-pipeline-queue"


class EnqueueOutcome(str, Enum):
    """Three outcomes, because two is a lie.

    A boolean forces every transport failure to be reported as either
    "queued" or "not queued", and the caller acts on that: NOT_ENQUEUED
    means "run it here instead". When the truth is "I do not know", both
    answers are wrong in a different direction, and the wrong one costs a
    duplicate concurrent pipeline on a single run_id.

    * ENQUEUED      - a child will run this. Do nothing else.
    * NOT_ENQUEUED  - definitively nothing was accepted. Safe to run the
                      work another way, and safe to mark the run failed.
    * UNKNOWN       - a child MAY run this. Do not run it again and do not
                      mark it failed; leave it queued and surface it.
    """

    ENQUEUED = "enqueued"
    NOT_ENQUEUED = "not_enqueued"
    UNKNOWN = "unknown"


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

    Returns an `EnqueueOutcome`. Only `NOT_ENQUEUED` licenses the caller
    to run the work another way: `UNKNOWN` means a child may already be
    running it, and acting on that as if it were a failure is how one
    run_id ends up executing twice.
    """
    try:
        from google.cloud import tasks_v2  # type: ignore
        from google.api_core import exceptions as gexc  # type: ignore
    except ImportError:
        # Nothing was sent, so this is definitive.
        logger.error("google-cloud-tasks not installed - cannot enqueue %s", ticker)
        return EnqueueOutcome.NOT_ENQUEUED

    # Errors that are the SERVER saying no. Each one is returned instead of
    # accepting the task, so nothing is queued and falling back is safe.
    # Anything not listed here is treated as ambiguous, which is the
    # conservative direction: a mis-classified definitive error costs one
    # skipped report, a mis-classified ambiguous error costs a duplicate run.
    _DEFINITIVE_REJECTIONS = (
        gexc.PermissionDenied,      # SA lacks cloudtasks.tasks.create
        gexc.Unauthenticated,       # no usable credential
        gexc.InvalidArgument,       # malformed task/name/body
        gexc.NotFound,              # the queue does not exist
        gexc.FailedPrecondition,    # queue disabled or paused
        gexc.ResourceExhausted,     # queue rate limit rejected the request (gRPC)
        gexc.TooManyRequests,       # the same rejection over the REST transport
    )

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
            return EnqueueOutcome.ENQUEUED
        except gexc.AlreadyExists:
            # The deterministic name already exists, so this exact run is
            # queued. Reporting failure here would trigger a duplicate.
            logger.warning("task for %s (%s) already enqueued", ticker, run_id)
            return EnqueueOutcome.ENQUEUED
        except _DEFINITIVE_REJECTIONS as rejected:
            # The server answered, and the answer was "no". Nothing was
            # accepted, so running this ticker in-process cannot duplicate.
            logger.error(
                "Cloud Tasks rejected %s (%s): %s",
                ticker, type(rejected).__name__, rejected,
            )
            return EnqueueOutcome.NOT_ENQUEUED
        except Exception as ambiguous:
            # Transport-shaped failure: timeout, reset, 5xx. The task may
            # or may not have been accepted and NOTHING AVAILABLE HERE CAN
            # TELL US WHICH.
            #
            # A second create_task cannot: it has the identical ambiguous
            # outcome, which is the regress the first version of this fix
            # walked into (Codex, PR #1094). A get_task read cannot either:
            # Cloud Tasks deletes a task once it has been dispatched and
            # the target returned 2xx, and the target here is Cloud Run's
            # :run, which answers immediately with an Operation -- so
            # NotFound means "never accepted" OR "already dispatched", and
            # the two are indistinguishable.
            #
            # So do not guess. UNKNOWN is not a failure to be retried; it
            # is a state the caller must not resolve by running the work
            # again. A missing report is visible and recoverable; two
            # concurrent pipelines on one run_id race the status
            # transitions and double the history rows, which is corruption.
            logger.error(
                "Cloud Tasks enqueue outcome UNKNOWN for %s (run_id=%s): %s. "
                "The task may be queued; NOT running it in-process.",
                ticker, run_id, ambiguous,
            )
            return EnqueueOutcome.UNKNOWN
    except Exception as exc:
        # Raised before any RPC left this process (client construction,
        # queue path, body build), so nothing can have been accepted.
        logger.error("Cloud Tasks enqueue failed for %s: %s", ticker, exc)
        return EnqueueOutcome.NOT_ENQUEUED
