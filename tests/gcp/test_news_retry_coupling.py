"""FEAT-DEPLOY-001: the three NEWS jobs deploy with zero whole-job retries.

Spec: docs/superpowers/specs/2026-10-29-feat-deploy-001-news-retry-coupling.md
(approved; landed on main in d806bfd1, spec blob 216424cb).

The typed-news producer (FEAT-DATA-001) exits nonzero on source or
persistence uncertainty after it has persisted successful siblings. A Cloud
Run whole-job retry would replay the entire job, siblings included. At the
pinned baseline (main 53bc13ff, deploy.sh blob 45cb4f9b) every NEWS create
passes `--max-retries 1` and every update omits the flag, and an update that
omits a flag leaves the job's existing value in place.

These tests extract the ACTUAL `deploy_fetch_news_sentiment`,
`deploy_fetch_news_sentiment_earnings` and `deploy_fetch_news_sentiment_topics`
definitions from gcp/deploy.sh and execute them under bash with a
shell-local `gcloud` stub on PATH. The stub records argv and exits 0, or
exits 1 for `run jobs create` in the existing-job scenario so the real
create-failure/update fallback runs. Nothing reaches a real SDK, cloud,
provider, SQL server or image build.

Pinned observations: all-create-success emits five calls (three creates and
the earnings/topics env-only updates); all-existing emits eight (three failed
creates, three updates, two env-only updates). All thirteen must address
exactly the three allowed jobs and carry max-retries 0, and every other
argument must equal the same call executed from the pinned baseline bodies.
Those bodies are embedded verbatim below because CI checks out a single
commit and cannot read 53bc13ff; `test_embedded_baseline_matches_pinned_commit`
re-derives them from git wherever the commit object is present. The baseline
bodies run through the same retry controls, which must reject them.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO / "gcp/deploy.sh"

NEWS_FUNCTIONS = (
    "deploy_fetch_news_sentiment",
    "deploy_fetch_news_sentiment_earnings",
    "deploy_fetch_news_sentiment_topics",
)
JOB_OF = {
    "deploy_fetch_news_sentiment": "fetch-news-sentiment",
    "deploy_fetch_news_sentiment_earnings": "fetch-news-sentiment-earnings",
    "deploy_fetch_news_sentiment_topics": "fetch-news-sentiment-topics",
}
ALLOWED_JOBS = frozenset(JOB_OF.values())

BASELINE_COMMIT = "53bc13ff1ea96c46cc09e30d535409ad0ad4633f"
BASELINE_DEPLOY_BLOB = "45cb4f9bc8a346c083c29dcfe656fbce15670434"
BASELINE_LINES = (3119, 3205)  # 1-based, inclusive, in BASELINE_DEPLOY_BLOB
BASELINE_SHA256 = "f13677b529ef238589af2a8e4238df3c508a2f3e598704331395ceb652737baf"
BASELINE_FUNCTIONS = r'''deploy_fetch_news_sentiment() {
    echo "Deploying fetch-news-sentiment (ticker mode) job..."
    # AV_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    # Tickers come from alert_config.json `watchlist` at runtime via
    # gcp/fetchers/_watchlist.load_watchlist(). No hardcoded NEWS_TICKERS
    # env var — change the watchlist by editing alert_config.json + redeploy
    # the image. --args="" defensively strips any leftover positional CLI
    # args from prior manual gcloud edits that would break argparse.
    gcloud run jobs create fetch-news-sentiment \
        --image "${IMAGE_REF:?build_image has not run in this invocation}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ENV_STRING}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-news-sentiment \
        --image "${IMAGE_REF:?build_image has not run in this invocation}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --args "" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ENV_STRING}" \
        --quiet
}

deploy_fetch_news_sentiment_earnings() {
    echo "Deploying fetch-news-sentiment-earnings (upcoming-reporter mode) job..."
    # Same Docker image as the ticker-mode job; differs only in env:
    # EARNINGS_WINDOW_DAYS=7 makes the fetcher resolve its ticker
    # universe to (earnings_calendar ±7d) ∪ watchlist. Runs once a day
    # before the brief so tomorrow's reporters always have a 48h news
    # cold-start cushion landed in news_sentiment before the embed
    # consumes it. AV cost: ~30 cold-start reporters × 1 call = 30
    # calls/day — well under the 150 RPM plan ceiling.
    gcloud run jobs create fetch-news-sentiment-earnings \
        --image "${IMAGE_REF:?build_image has not run in this invocation}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ENV_STRING}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-news-sentiment-earnings \
        --image "${IMAGE_REF:?build_image has not run in this invocation}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --args "" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ENV_STRING}" \
        --quiet

    # EARNINGS_WINDOW_DAYS=7 → fetcher's main() unions earnings_calendar
    # (±7d) with the watchlist. NEWS_SINCE_LAST=1 → incremental per-ticker
    # floor so cold-start reporters pull 48h and steady-state reporters
    # only pull deltas. MAX_TICKERS=300 caps the resolved set.
    gcloud run jobs update fetch-news-sentiment-earnings \
        --region "${REGION}" \
        --update-env-vars "^@^EARNINGS_WINDOW_DAYS=7@NEWS_SINCE_LAST=1@MAX_TICKERS=300" \
        --quiet
}

deploy_fetch_news_sentiment_topics() {
    echo "Deploying fetch-news-sentiment-topics (topic mode) job..."
    # AV_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    # NEWS_TOPICS env var (set below) is the source of truth; --args=""
    # defensively strips any leftover CLI args from prior manual edits.
    gcloud run jobs create fetch-news-sentiment-topics \
        --image "${IMAGE_REF:?build_image has not run in this invocation}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ENV_STRING}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-news-sentiment-topics \
        --image "${IMAGE_REF:?build_image has not run in this invocation}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --args "" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ENV_STRING}" \
        --quiet

    # 5 catalyst-rich topics — AV's hard cap per call.
    gcloud run jobs update fetch-news-sentiment-topics \
        --region "${REGION}" \
        --update-env-vars "^@^NEWS_TOPICS=mergers_and_acquisitions,technology,financial_markets,earnings,life_sciences" \
        --quiet
}
'''

# Values the stub environment gives the globals deploy.sh resolves before any
# deploy function runs. Shapes follow _build_secret_flag and _env_string; the
# secret flag is unquoted at every call site, so it word-splits into two.
STUB_GLOBALS = {
    "IMAGE_REF": "us-east1-docker.pkg.dev/stub-project/trading/trading-system@sha256:" + "a" * 64,
    "REGION": "us-east1",
    "SA_EMAIL": "trading-runner@stub-project.iam.gserviceaccount.com",
    "DB_SECRET_FLAG": "--set-secrets=DB_PASS=stub-db-pass:latest --update-labels=stub=1",
    "ENV_STRING": "CLOUD_SQL_CONNECTION_NAME=stub:us-east1:db,DB_USER=stub,DB_NAME=trading",
}

# Stub: one file per call, argv NUL-separated, so arguments with spaces,
# commas and `^@^` delimiters survive exactly. It uses only shell builtins and
# never execs anything, so no real gcloud on the host can be reached.
GCLOUD_STUB = r'''#!/bin/bash
n=0
while [ -e "${GCLOUD_STUB_LOG}/$(printf '%04d' "$n")" ]; do n=$((n + 1)); done
printf '%s\0' "$@" > "${GCLOUD_STUB_LOG}/$(printf '%04d' "$n")"
if [ "${GCLOUD_STUB_MODE}" = existing ] && [ "$1" = run ] && [ "$2" = jobs ] && [ "$3" = create ]; then
    echo "ERROR: (gcloud.run.jobs.create) Resource already exists" >&2
    exit 1
fi
exit 0
'''

# The call shapes the spec pins: (verb, job, kind) in emission order.
CREATE_SUCCESS_SHAPE = [
    ("create", "fetch-news-sentiment", "create"),
    ("create", "fetch-news-sentiment-earnings", "create"),
    ("update", "fetch-news-sentiment-earnings", "env-only"),
    ("create", "fetch-news-sentiment-topics", "create"),
    ("update", "fetch-news-sentiment-topics", "env-only"),
]
EXISTING_SHAPE = [
    ("create", "fetch-news-sentiment", "create"),
    ("update", "fetch-news-sentiment", "full"),
    ("create", "fetch-news-sentiment-earnings", "create"),
    ("update", "fetch-news-sentiment-earnings", "full"),
    ("update", "fetch-news-sentiment-earnings", "env-only"),
    ("create", "fetch-news-sentiment-topics", "create"),
    ("update", "fetch-news-sentiment-topics", "full"),
    ("update", "fetch-news-sentiment-topics", "env-only"),
]
SCENARIOS = {"create-success": CREATE_SUCCESS_SHAPE, "existing": EXISTING_SHAPE}


def _definition(text: str, name: str) -> str:
    """The whole `name() { ... }` definition, closed by the first column-0 `}`
    (how every function in deploy.sh is closed). Exactly one must exist."""
    matches = re.findall(r"^" + re.escape(name) + r"\(\)\s*\{\n.*?^\}\n", text, re.M | re.S)
    assert len(matches) == 1, f"{name}: expected exactly one definition, found {len(matches)}"
    return matches[0]


def _current_definitions() -> str:
    text = DEPLOY_SH.read_text()
    return "".join(_definition(text, n) for n in NEWS_FUNCTIONS)


def _baseline_definitions() -> str:
    return "".join(_definition(BASELINE_FUNCTIONS, n) for n in NEWS_FUNCTIONS)


def _execute(tmp_path: Path, definitions: str, mode: str,
             functions: tuple[str, ...] = NEWS_FUNCTIONS) -> list[list[str]]:
    """Run the definitions under bash with the stub first on PATH, call each
    of `functions` in order, and return each recorded gcloud argv (without
    the program name)."""
    work = tmp_path / mode
    bindir, log = work / "bin", work / "log"
    bindir.mkdir(parents=True)
    log.mkdir()
    stub = bindir / "gcloud"
    stub.write_text(GCLOUD_STUB)
    stub.chmod(0o755)
    script = work / "run.sh"
    script.write_text(
        "set -u\n"
        + "".join(f"{k}={_sh_quote(v)}\n" for k, v in STUB_GLOBALS.items())
        + definitions
        + "".join(f"{n}\n" for n in functions)
    )
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "GCLOUD_STUB_LOG": str(log),
        "GCLOUD_STUB_MODE": mode,
        "HOME": str(work),
        "LC_ALL": "C",
    }
    proc = subprocess.run(["bash", "--noprofile", "--norc", str(script)],
                          env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    calls = []
    for f in sorted(log.iterdir()):
        raw = f.read_bytes()
        assert raw.endswith(b"\0"), f"{f.name}: truncated record"
        calls.append(raw[:-1].decode().split("\0"))
    return calls


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _retry_values(argv: list[str]) -> list[str]:
    """Every max-retries value in argv, in either `--flag v` or `--flag=v` form."""
    out = []
    for i, a in enumerate(argv):
        if a == "--max-retries":
            out.append(argv[i + 1] if i + 1 < len(argv) else "<missing>")
        elif a.startswith("--max-retries="):
            out.append(a.split("=", 1)[1])
    return out


def _without_retries(argv: list[str]) -> list[str]:
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a == "--max-retries":
            skip = True
            continue
        if a.startswith("--max-retries="):
            continue
        out.append(a)
    return out


def _kind(argv: list[str]) -> str:
    if argv[2] == "create":
        return "create"
    return "full" if "--image" in argv else "env-only"


def _shape(calls: list[list[str]]) -> list[tuple[str, str, str]]:
    return [(c[2], c[3], _kind(c)) for c in calls]


def _retry_violations(calls: list[list[str]]) -> list[str]:
    """The retry control: one entry per call that is not exactly one
    max-retries 0. Empty means the control passes."""
    bad = []
    for i, c in enumerate(calls):
        vals = _retry_values(c)
        if vals != ["0"]:
            bad.append(f"call {i} {c[2]} {c[3]}: max-retries {vals or 'absent'}")
    return bad


# ── provenance of the embedded baseline ───────────────────────────────────


def test_embedded_baseline_is_byte_pinned():
    assert hashlib.sha256(BASELINE_FUNCTIONS.encode()).hexdigest() == BASELINE_SHA256
    assert BASELINE_FUNCTIONS.count("\n") == BASELINE_LINES[1] - BASELINE_LINES[0] + 1


def test_embedded_baseline_matches_pinned_commit():
    """Where the pinned commit is present (a full clone or a fetch of it),
    the embedded text is exactly those lines of that commit's deploy.sh."""
    probe = subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{BASELINE_COMMIT}^{{commit}}"],
                           capture_output=True)
    if probe.returncode != 0:
        pytest.skip(f"{BASELINE_COMMIT[:8]} is not in this checkout; the byte pin above still holds")
    blob = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{BASELINE_COMMIT}:gcp/deploy.sh"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert blob == BASELINE_DEPLOY_BLOB
    text = subprocess.run(["git", "-C", str(REPO), "show", f"{BASELINE_COMMIT}:gcp/deploy.sh"],
                          capture_output=True, text=True, check=True).stdout
    lo, hi = BASELINE_LINES
    assert "".join(text.splitlines(keepends=True)[lo - 1:hi]) == BASELINE_FUNCTIONS


# ── the baseline is the defect: the same controls must reject it ──────────


@pytest.mark.parametrize("mode", sorted(SCENARIOS))
def test_baseline_fails_retry_controls(tmp_path, mode):
    calls = _execute(tmp_path, _baseline_definitions(), mode)
    assert _shape(calls) == SCENARIOS[mode]
    violations = _retry_violations(calls)
    # Every baseline call violates: creates carry 1, updates carry nothing.
    assert len(violations) == len(calls), violations
    for c in calls:
        assert _retry_values(c) == (["1"] if c[2] == "create" else [])


# ── the current deploy.sh ─────────────────────────────────────────────────


@pytest.mark.parametrize("mode", sorted(SCENARIOS))
def test_news_calls_are_the_pinned_shape(tmp_path, mode):
    calls = _execute(tmp_path, _current_definitions(), mode)
    assert _shape(calls) == SCENARIOS[mode]
    assert len(calls) == {"create-success": 5, "existing": 8}[mode]
    for c in calls:
        assert c[:2] == ["run", "jobs"]
        assert c[3] in ALLOWED_JOBS


@pytest.mark.parametrize("mode", sorted(SCENARIOS))
def test_every_news_create_and_update_has_zero_retries(tmp_path, mode):
    calls = _execute(tmp_path, _current_definitions(), mode)
    assert _retry_violations(calls) == []


@pytest.mark.parametrize("mode", sorted(SCENARIOS))
def test_all_other_arguments_match_pinned_baseline(tmp_path, mode):
    """Image reference, command, args, service identity, region, resources,
    environment and secret references are unchanged call for call."""
    current = _execute(tmp_path / "current", _current_definitions(), mode)
    baseline = _execute(tmp_path / "baseline", _baseline_definitions(), mode)
    assert len(current) == len(baseline)
    for i, (cur, base) in enumerate(zip(current, baseline)):
        assert _without_retries(cur) == _without_retries(base), f"call {i}"


def test_thirteen_observations_in_total(tmp_path):
    calls = [c for mode in sorted(SCENARIOS)
             for c in _execute(tmp_path, _current_definitions(), mode)]
    assert len(calls) == 13
    assert {c[3] for c in calls} == ALLOWED_JOBS
    assert _retry_violations(calls) == []


def test_each_function_addresses_only_its_own_job(tmp_path):
    text = DEPLOY_SH.read_text()
    for name, job in JOB_OF.items():
        for mode in sorted(SCENARIOS):
            calls = _execute(tmp_path / name, _definition(text, name), mode, (name,))
            assert calls, f"{name} {mode}: no gcloud call"
            assert {c[3] for c in calls} == {job}
