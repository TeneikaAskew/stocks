"""Which image each production job ran on each execution, for a week
replay (default 2026-11-01 to 2026-11-08 UTC). READ-ONLY: gcloud only
lists executions and describes images. Nothing is written, deployed or
posted. Result: results/jobs_history_<start>.json.

Usage (from the root of a stocks clone):
  python3 /tmp/strat-params/harness/strat-params/week_jobs.py 2026-11-01 2026-11-08
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

START = sys.argv[1] if len(sys.argv) > 1 else "2026-11-01"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-11-08"
JOBS = ("premarket-brief", "signal-monitor", "signal-monitor-eod-resolver",
        "fetch-premarket-refresh")
REGION = ["--region", "us-east1"]


def gjson(cmd: list[str]):
    r = subprocess.run(cmd + ["--format=json"], capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": r.stderr[-2000:]}
    return json.loads(r.stdout or "null")


def images(obj) -> list[str]:
    found = []
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "image" and isinstance(v, str):
                    found.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return sorted(set(found))


def main() -> None:
    out = Path(__file__).resolve().parent / "results" / f"jobs_history_{START}.json"
    res = {"start": START, "end": END, "jobs": {}, "images": {}}
    for job in JOBS:
        ex = gjson(["gcloud", "run", "jobs", "executions", "list", "--job", job, *REGION, "--limit", "400"])
        rows = []
        if isinstance(ex, list):
            for e in ex:
                md = e.get("metadata", {})
                ts = md.get("creationTimestamp") or e.get("createTime") or ""
                if START <= ts[:10] <= END:
                    st = e.get("status", {})
                    rows.append({"name": md.get("name") or e.get("name"), "created": ts,
                                 "completed": st.get("completionTime"),
                                 "succeeded": st.get("succeededCount"), "failed": st.get("failedCount"),
                                 "images": images(e.get("spec", e))})
        else:
            rows = ex
        res["jobs"][job] = rows
        print(job, len(rows) if isinstance(rows, list) else rows, file=sys.stderr, flush=True)
    refs = sorted({i for rows in res["jobs"].values() if isinstance(rows, list) for r in rows for i in r["images"]})
    for ref in refs:
        d = gjson(["gcloud", "artifacts", "docker", "images", "describe", ref])
        res["images"][ref] = d if isinstance(d, dict) and "error" in d else {
            "upload": (d or {}).get("image_summary", {}).get("upload_time") if isinstance(d, dict) else None,
            "digest": (d or {}).get("image_summary", {}).get("digest") if isinstance(d, dict) else None,
            "tags": (d or {}).get("image_summary", {}).get("tags") if isinstance(d, dict) else None}
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out, file=sys.stderr)


if __name__ == "__main__":
    main()
