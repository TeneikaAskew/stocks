#!/usr/bin/env python3
"""Print the Cloud Run revision that is actually SERVING TRAFFIC.

Reads `gcloud run services describe <svc> --region=<r> --format=json` on
stdin and writes one revision name on stdout.

Why not `status.latestReadyRevisionName`: the two differ whenever the service
has been rolled back, is split across revisions, or was deployed
`--no-traffic` (a mode `platform/deploy.sh` still supports). In each of those
the latest ready revision is precisely the one nobody validated (Codex,
PR #990).

Fails loud rather than guessing: nothing serving, or traffic split across
several revisions, both exit non-zero instead of picking one.

Lives here rather than inline in a build step because two callers need the
same answer -- the prod promote trigger, which promotes what staging serves,
and `platform/deploy.sh`, which refuses to deploy over a service that moved
under it. Two copies of this rule would drift, and the drift would be silent.
"""
import json
import sys


def serving_revision(described: dict) -> str:
    status = described.get("status") or {}
    serving = [t for t in status.get("traffic", []) if (t.get("percent") or 0) > 0]
    if not serving:
        raise SystemExit("FATAL: no revision is receiving traffic; there is "
                         "nothing validated to read")
    if len(serving) > 1:
        detail = ", ".join(f"{t.get('revisionName', '?')}={t.get('percent')}%"
                           for t in serving)
        raise SystemExit(f"FATAL: traffic is split across revisions ({detail}); "
                         "which one was validated is ambiguous, settle the "
                         "service before deploying or promoting")
    name = serving[0].get("revisionName") or status.get("latestReadyRevisionName")
    if not name:
        raise SystemExit("FATAL: could not resolve the serving revision name "
                         "from the traffic target")
    return name


if __name__ == "__main__":
    print(serving_revision(json.load(sys.stdin)))
