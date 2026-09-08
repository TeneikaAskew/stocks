"""Every Cloud Scheduler declaration in gcp/deploy.sh must use ET by name.

Cloud Scheduler defaults to **UTC** when `--time-zone` is omitted, which would
silently move an "02:00 ET" job to the previous evening. `gcp/deploy.sh`
creates every scheduler entry, so the guard has two halves:

  1. Every `--time-zone` it passes is the named, DST-correct `America/New_York`
     — never a fixed offset (`EST` / `EDT`) and never the `US/Eastern`
     compatibility link that is absent from slim images.
  2. Every `create` declaration actually carries a timezone — inline or via a
     shared flag array — so a future zoneless create (which would run in UTC)
     fails the test rather than being invisible. An `update` inherits the
     existing job's zone, so only `create` must set it.

This is the small, bounded remainder of the retired repository-wide source
scanner: a handful of regexes over one file. It resolves the one array pattern
`gcp/deploy.sh` uses to share flags between a create/update pair
(`local _x=( ... --time-zone ... )` then `"${_x[@]}"`), which is the array
trap that made the old per-function shell parser fragile; it does not attempt
general shell evaluation.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO / "gcp" / "deploy.sh"
EASTERN = "America/New_York"


def _strip_shell_comments(text: str) -> str:
    """Drop `#`-to-end-of-line, honouring quotes.

    A commented-out `--time-zone` flag is not executed, so it must not
    contribute a zone to the set under test. `#` inside quotes is data
    (`msg="#tag"`), so the scan tracks quote state rather than cutting at the
    first `#`.
    """
    out = []
    for line in text.splitlines():
        quote = None
        cut = len(line)
        for i, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in ("'", '"'):
                quote = ch
            elif ch == "#":
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def test_every_scheduler_time_zone_is_eastern():
    body = _strip_shell_comments(DEPLOY_SH.read_text())
    # Join line continuations first: `--time-zone \` with the value on the
    # next line is ordinary wrapping, not a zone of `\`.
    joined = re.sub(r"\\\n\s*", " ", body)

    # (1) Every --time-zone value passed to gcloud is the named Eastern zone.
    # Both spellings: `--time-zone VALUE` and `--time-zone=VALUE`, quoted or
    # not. Capture up to the next quote or space.
    zones = set(re.findall(r"--time-zone[=\s]+[\"']?([^\s\"']+)[\"']?", joined))
    assert zones, "no --time-zone flags found -- has deploy.sh moved?"
    non_eastern = sorted(zones - {EASTERN})
    assert not non_eastern, (
        f"non-Eastern scheduler timezones in gcp/deploy.sh: {non_eastern}"
    )

    # (2) Every `create` command carries a timezone -- so a future zoneless
    # create, which Cloud Scheduler would silently run in UTC, fails here.
    # Shared flag arrays (`local _x=( ... --time-zone ... )` expanded as
    # `"${_x[@]}"`) count for the create that expands them; the closing `)` is
    # matched at line start so an inner `$(...)` does not truncate the body.
    tz_arrays = {
        name
        for name, arr_body in re.findall(r"(\w+)=\((.*?)\n\s*\)", body, re.DOTALL)
        if "--time-zone" in arr_body
    }
    # One segment per gcloud invocation (split before each `gcloud `).
    segments = re.split(r"(?=gcloud\s)", joined)
    creates = [
        s for s in segments
        if re.match(r"gcloud\s+scheduler\s+jobs\s+create\b", s)
    ]
    assert creates, "no scheduler create commands found -- has deploy.sh moved?"

    def _has_timezone(seg: str) -> bool:
        if "--time-zone" in seg:
            return True
        return any(f"{name}[@]" in seg for name in tz_arrays)

    def _job_name(seg: str) -> str:
        m = re.search(r'create\s+\w+\s+"([^"]+)"', seg)
        return m.group(1) if m else seg[:60]

    zoneless = sorted(_job_name(s) for s in creates if not _has_timezone(s))
    assert not zoneless, (
        "Cloud Scheduler defaults to UTC when --time-zone is omitted; these "
        "create declarations set no timezone (inline or via a shared flag "
        f"array): {zoneless}"
    )
