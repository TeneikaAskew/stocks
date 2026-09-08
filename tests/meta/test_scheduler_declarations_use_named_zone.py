"""Every Cloud Scheduler declaration in gcp/deploy.sh must use ET by name.

Cloud Scheduler defaults to **UTC** when `--time-zone` is omitted, which would
silently move an "02:00 ET" job to the previous evening. `gcp/deploy.sh`
creates every scheduler entry, so every `--time-zone` it passes must be the
named, DST-correct `America/New_York` — never a fixed offset (`EST` / `EDT`)
and never the `US/Eastern` compatibility link that is absent from slim images.

This is the small, bounded remainder of the retired repository-wide source
scanner: a single regex over one file. It asserts the strong half — no
non-Eastern zone is passed to gcloud — and deliberately does not try to prove
that no declaration omits the flag, which needs a shell parser and was a
standing source of false positives.
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
    # Both spellings: `--time-zone VALUE` and `--time-zone=VALUE`, quoted or
    # not. Capture up to the next quote or space.
    zones = set(re.findall(r"--time-zone[=\s]+[\"']?([^\s\"']+)[\"']?", joined))
    assert zones, "no --time-zone flags found -- has deploy.sh moved?"
    non_eastern = sorted(zones - {EASTERN})
    assert not non_eastern, (
        f"non-Eastern scheduler timezones in gcp/deploy.sh: {non_eastern}"
    )
