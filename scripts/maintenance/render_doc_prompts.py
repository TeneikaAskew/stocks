"""Substitute the live fleet counts into the doc-refresh prompts.

Run 22 of `.github/workflows/refresh-architecture-docs.yml` (2026-09-07)
regenerated `05-d-COST_ANALYSIS.md` with "24 Cloud Scheduler jobs" against a
live fleet of 65, and the run went red on that one verifier finding. The
prompt already carried the instruction

    Use the live counts for N jobs / N schedulers; never hardcode a number
    from an older version.

and named `live.json` -> `counts.schedulers` as the source. Asking was not
enough: the model still had to find, read and trust a JSON file whose reads
its own tooling truncates, and the number it produced came from somewhere
else entirely.

This module removes the derivation. Every count a prompt needs is written
into the prompt text as a literal before the model is called, so the model
copies a number instead of computing one. The verifier stays as the gate --
this only stops it firing on a class of drift we can compute ourselves.

Placeholders are `{{NAME}}`. An unknown name is a hard error, so a typo in a
prompt fails this step rather than reaching the model as literal braces.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

PLACEHOLDER = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")


# The three counts `scripts/verify_docs_against_live.py` can report drift on,
# mapped to the key its own snapshot holds them under. That snapshot is taken
# by a different script from a separate set of gcloud calls, so a number handed
# to the model out of doc_inventory's snapshot could be one the verifier then
# rejects -- a doc failing a gate for a number the pipeline itself supplied.
# Cross-checked rather than assumed equal.
VERIFIED = (("LIVE_JOBS", "run_jobs"), ("LIVE_SCHEDULERS", "schedulers"),
            ("LIVE_SERVICES", "services"), ("LIVE_SECRETS", "secrets"))


def counts(live: dict, repo_inventory: dict, verify_live: dict) -> dict[str, str]:
    """The values a prompt may reference, from the three rendered inputs.

    Every lookup is direct: a missing key raises rather than defaulting, so a
    broken snapshot fails here instead of reaching the model as a plausible
    wrong number (Rule 3.7).
    """
    lc = live["counts"]
    rc = repo_inventory["repo"]["counts"]
    raw = {
        "LIVE_JOBS": lc["jobs"],
        "LIVE_SCHEDULERS": lc["schedulers"],
        "LIVE_SERVICES": lc["services"],
        "LIVE_SECRETS": lc["secrets"],
        "LIVE_DB_TABLES": len(live["db_tables"]),
        "DECLARED_JOBS": rc["jobs"],
        "DECLARED_SCHEDULERS": rc["schedulers"],
        "DECLARED_TABLES": rc["tables"],
    }
    for name, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise SystemExit(f"{name} is {value!r}, not an int — the inputs are broken")
        if value <= 0:
            raise SystemExit(f"{name} is {value} — refusing to render a prompt from an empty snapshot")
    for name, key in VERIFIED:
        n = len(verify_live[key])
        if n != raw[name]:
            raise SystemExit(
                f"{name} is {raw[name]} in live.json but the verifier's snapshot has "
                f"{n} {key}. Handing the model either number would fail a gate; "
                "the two snapshots disagree and that is the bug to fix.")
    return {name: str(value) for name, value in raw.items()}


def render(text: str, values: dict[str, str], where: str) -> str:
    unknown = sorted({m.group(1) for m in PLACEHOLDER.finditer(text)} - set(values))
    if unknown:
        raise SystemExit(f"{where}: unknown placeholder(s) {', '.join(unknown)}; "
                         f"known: {', '.join(sorted(values))}")
    out = PLACEHOLDER.sub(lambda m: values[m.group(1)], text)
    if "{{" in out:
        # Not reachable through PLACEHOLDER, so this is a malformed one --
        # `{{live_jobs}}`, `{{ LIVE_JOBS }}`. Silently passing it through would
        # put literal braces in front of the model.
        raise SystemExit(f"{where}: '{{{{' survived rendering — a malformed placeholder")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", required=True, help="refresh-inputs/live.json")
    ap.add_argument("--repo-inventory", required=True, help="refresh-inputs/repo_inventory.json")
    ap.add_argument("--verify-live", required=True, help="refresh-inputs/verify_live.json")
    ap.add_argument("--prompts", default=".github/prompts", help="directory of prompt templates")
    ap.add_argument("--out", required=True, help="directory to write the rendered prompts into")
    args = ap.parse_args(argv)

    live = json.loads(pathlib.Path(args.live).read_text())
    repo_inventory = json.loads(pathlib.Path(args.repo_inventory).read_text())
    verify_live = json.loads(pathlib.Path(args.verify_live).read_text())
    values = counts(live, repo_inventory, verify_live)

    src = pathlib.Path(args.prompts)
    templates = sorted(src.glob("*.md"))
    if not templates:
        raise SystemExit(f"no prompt templates in {src}")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for t in templates:
        text = t.read_text()
        n = len(PLACEHOLDER.findall(text))
        (out / t.name).write_text(render(text, values, str(t)))
        print(f"{t.name}: {n} substitution(s)")
    print("counts: " + ", ".join(f"{k}={v}" for k, v in sorted(values.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
