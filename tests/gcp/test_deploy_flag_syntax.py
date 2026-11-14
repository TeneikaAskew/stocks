"""gcloud flag syntax of every deploy function in gcp/deploy.sh (FEAT-DEPLOY-001).

On 2026-11-10 `./gcp/deploy.sh fetchers` stopped partway: gcloud refused
three calls before reaching the API, and a sweep found a fourth. Nothing in
tests/gcp/ checked that the script's gcloud calls parse, so each shipped
silently. Spec: docs/superpowers/specs/2026-11-11-feat-deploy-001-deploy-flag-syntax-revised.md.

The sweep defines every top-level function of deploy.sh in bash, puts a
recording `gcloud` stub first on PATH and runs each `deploy_*` function
(except `deploy_schedulers`) in two passes: one where `run jobs describe`
succeeds and one where it fails with gcloud's NOT_FOUND text, so a function
that returns early when its job exists (deploy_apply_schema_migrations) also
emits its create call. The stub makes `run jobs create` fail, so the update
branch runs too. Every recorded `gcloud run deploy` and
`gcloud run jobs|services create|update` argv is then checked against the
rules gcloud 570 applies before any request:

- at most one of --clear-env-vars, --env-vars-file, --set-env-vars and the
  pair --update-env-vars/--remove-env-vars; the same split for the secret
  flags (--clear-secrets, --set-secrets, --update-secrets/--remove-secrets);
- every --set-env-vars, --update-env-vars, --set-secrets and --update-secrets
  value, after an optional ^X^ delimiter prefix, splits into KEY=VALUE items;
- no --args given as a separate argument that starts with a hyphen and holds
  no space (gcloud's argparse reads that as a new flag; with a space it is a
  value, which is how deploy_av_options_backfill/_realtime pass theirs).

No network, no gcloud, no Python import of production code.
"""
from __future__ import annotations

import difflib
import os
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO / "gcp/deploy.sh"

ENV_STRING = ("CLOUD_SQL_CONNECTION_NAME=fake-proj-000:us-east1:trading-db,DB_USER=trader,"
              "DB_NAME=trading,GCS_BUCKET=fake-proj-000-trading-data,RECOMMEND_LONG_ONLY=true")
DB_SECRET_FLAG = "--set-secrets=DB_PASS=db-trading-pass:latest,AV_API_KEY=av-api-key:latest"
SECRETS = {"cloud-sql-connection-name": "fake-proj-000:us-east1:trading-db", "db-trading-user": "trader"}
# Prints and returns 1; it deploys nothing by design.
NO_DEPLOY_CALL = {"deploy_p7b_classifier_DEPRECATED"}

_FN_START = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{")
_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")

_GCLOUD_STUB = r"""#!/bin/bash
{ printf '%s\0' "$@"; printf '\036\n'; } >> "${GCLOUD_LOG}"
case "$1 $2 $3" in
  "run jobs create") echo "ERROR: (gcloud.run.jobs.create) already exists" >&2; exit 1 ;;
  "run jobs describe")
    if [ -n "${STUB_NOT_FOUND:-}" ]; then
      echo "ERROR: (gcloud.run.jobs.describe) Cannot find job [$4]." >&2; exit 1
    fi
    echo "$4"; exit 0 ;;
esac
exit 0
"""


def _functions(text: str) -> list[tuple[str, str]]:
    """Top-level `name() {` ... `}` blocks, skipping heredoc bodies (a heredoc
    line starting with `}` would otherwise end a function early)."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        m = _FN_START.match(lines[i])
        if not m:
            i += 1
            continue
        j, heredoc = i + 1, None
        while True:
            line = lines[j]
            if heredoc is not None:
                if line.strip() == heredoc:
                    heredoc = None
            elif line.startswith("}"):
                break
            elif "<<<" not in line and (h := _HEREDOC.search(line)):
                heredoc = h.group(1)
            j += 1
        out.append((m.group(1), "\n".join(lines[i:j + 1])))
        i = j + 1
    return out


def _is_deploy_call(argv: list[str]) -> bool:
    return argv[:2] == ["run", "deploy"] or (
        len(argv) > 3 and argv[0] == "run" and argv[1] in ("jobs", "services")
        and argv[2] in ("create", "update"))


@lru_cache(maxsize=None)
def sweep(text: str, not_found: bool) -> dict:
    """Run every deploy_* function of `text` once against the stub. Returns
    {"defined": [...], "calls": {fn: [argv, ...]}} with deploy calls only."""
    fns = _functions(text)
    deploys = [n for n, _ in fns if n.startswith("deploy_") and n != "deploy_schedulers"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bindir = tmp / "bin"
        bindir.mkdir()
        (bindir / "gcloud").write_text(_GCLOUD_STUB)
        for tool in ("python3", "python", "docker", "curl", "gsutil", "bq", "sleep", "git"):
            (bindir / tool).write_text("#!/bin/bash\nexit 0\n")
        for f in bindir.iterdir():
            f.chmod(0o755)
        log = tmp / "gcloud.log"
        log.write_bytes(b"")
        secret_cases = "\n".join(f"    {k}) printf '%s' '{v}' ;;" for k, v in SECRETS.items())
        body = [
            "set +e",
            "PROJECT_ID=fake-proj-000; REGION=us-east1; IMAGE=us-east1-docker.pkg.dev/fake-proj-000/trading/trading-system",
            "SA_EMAIL=trading-runner@fake-proj-000.iam.gserviceaccount.com",
            "IMAGE_REF=${IMAGE}@sha256:0000; RESEARCH_IMAGE_REF=${IMAGE}@sha256:1111",
            f"DB_SECRET_FLAG='{DB_SECRET_FLAG}'",
            f"ENV_STRING='{ENV_STRING}'",
            "NOTIFIER_SERVICE=failure-notifier; NOTIFIER_TOPIC=gcp-job-failures",
            "NOTIFIER_SUB=gcp-job-failures-push; NOTIFIER_SINK=gcp-job-failures-sink",
            *(src for _, src in fns),
            f"_secret() {{\n  case \"$1\" in\n{secret_cases}\n    *) printf '%s' \"value-$1\" ;;\n  esac\n}}",
            "declare -F | awk '{print $3}' > \"${DEFINED_OUT}\"",
        ]
        for n in deploys:
            body.append(f"printf '##FN {n}\\036\\n' >> \"${{GCLOUD_LOG}}\"")
            body.append(f"( {n} ) >/dev/null 2>&1 </dev/null")
        script = tmp / "sweep.sh"
        script.write_text("\n".join(body) + "\n")
        defined_out = tmp / "defined.txt"
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp), "GCLOUD_LOG": str(log),
               "DEFINED_OUT": str(defined_out), "LC_ALL": "C.UTF-8"}
        if not_found:
            env["STUB_NOT_FOUND"] = "1"
        subprocess.run(["bash", str(script)], env=env, cwd=tmp, timeout=300, check=False,
                       stdin=subprocess.DEVNULL, capture_output=True)
        calls: dict[str, list[list[str]]] = {n: [] for n in deploys}
        current = None
        for rec in log.read_bytes().split(b"\036\n"):
            if not rec:
                continue
            if rec.startswith(b"##FN "):
                current = rec[5:].decode()
                continue
            argv = [a.decode() for a in rec.split(b"\0")[:-1]]
            if current and _is_deploy_call(argv):
                calls[current].append(argv)
        defined = defined_out.read_text().split() if defined_out.exists() else []
    return {"names": [n for n, _ in fns], "defined": defined, "calls": calls}


def both_passes(text: str) -> dict[str, list[list[str]]]:
    a, b = sweep(text, False)["calls"], sweep(text, True)["calls"]
    return {n: a[n] + [c for c in b[n] if c not in a[n]] for n in a}


def _flag_values(argv: list[str], flag: str) -> list[str]:
    out = []
    for k, a in enumerate(argv):
        if a == flag and k + 1 < len(argv):
            out.append(argv[k + 1])
        elif a.startswith(flag + "="):
            out.append(a[len(flag) + 1:])
    return out


def _has(argv: list[str], flag: str) -> bool:
    return any(a == flag or a.startswith(flag + "=") for a in argv)


def parse_dict_arg(value: str) -> dict[str, str] | None:
    """gcloud's dict arg: optional ^X^ delimiter prefix, then KEY=VALUE items.
    None when an item has no `=` (gcloud: "Bad syntax for dict arg")."""
    delim = ","
    if m := re.match(r"\^(.+?)\^", value):
        delim, value = m.group(1), value[m.end():]
    out = {}
    for item in value.split(delim):
        if "=" not in item:
            return None
        k, v = item.split("=", 1)
        out[k] = v
    return out


def violations(argv: list[str]) -> list[str]:
    errs = []
    for kind, groups in (
        ("env", [["--clear-env-vars"], ["--env-vars-file"], ["--set-env-vars"],
                 ["--update-env-vars", "--remove-env-vars"]]),
        ("secrets", [["--clear-secrets"], ["--set-secrets"], ["--update-secrets", "--remove-secrets"]]),
    ):
        used = ["/".join(f for f in g if _has(argv, f)) for g in groups if any(_has(argv, f) for f in g)]
        if len(used) > 1:
            errs.append(f"mutually exclusive {kind} flags {used}")
    for flag in ("--set-env-vars", "--update-env-vars", "--set-secrets", "--update-secrets"):
        for v in _flag_values(argv, flag):
            if parse_dict_arg(v) is None:
                errs.append(f"{flag} value {v!r} has an item without KEY=VALUE")
    for k, a in enumerate(argv):
        if a == "--args" and k + 1 < len(argv) and argv[k + 1].startswith("-") and " " not in argv[k + 1]:
            errs.append(f"--args {argv[k + 1]!r} given separately is read as a new flag; use --args=VALUE")
    return errs


def all_violations(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fn, calls in both_passes(text).items():
        for argv in calls:
            for e in violations(argv):
                out.setdefault(fn, []).append(f"{' '.join(argv[:4])}: {e}")
    return out


TEXT = DEPLOY_SH.read_text()


# ── the sweep itself ─────────────────────────────────────────────────────────

def test_sweep_defines_every_top_level_function():
    """A function the extraction drops would be swept as missing, silently."""
    want = set(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{", TEXT, re.M))
    got = set(sweep(TEXT, False)["defined"])
    assert want <= got, f"not defined in the sweep: {sorted(want - got)}"


def test_every_deploy_function_records_a_deploy_call():
    calls = both_passes(TEXT)
    silent = sorted(n for n, c in calls.items() if not c and n not in NO_DEPLOY_CALL)
    assert not silent, f"swept but recorded no deploy call, so nothing of theirs was checked: {silent}"
    assert len(calls) >= 70, len(calls)


def test_not_found_pass_records_the_apply_schema_create_call():
    assert not sweep(TEXT, False)["calls"]["deploy_apply_schema_migrations"]
    created = sweep(TEXT, True)["calls"]["deploy_apply_schema_migrations"]
    assert [c[:4] for c in created] == [["run", "jobs", "create", "apply-schema-migrations"]], created


def test_every_deploy_call_passes_the_gcloud_flag_rules():
    bad = all_violations(TEXT)
    assert not bad, "gcloud would refuse these before any request:\n" + "\n".join(
        f"{fn}: {e}" for fn, errs in sorted(bad.items()) for e in errs)


def test_rules_accept_hyphen_args_with_a_space_and_refuse_without():
    assert not violations(["run", "jobs", "update", "j", "--args", "--tickers,SPY IWM QQQ"])
    assert violations(["run", "jobs", "update", "j", "--args", "--ticker,SPX"])
    assert not violations(["run", "jobs", "update", "j", "--args=--ticker,SPX"])
    assert not violations(["run", "jobs", "update", "j", "--args", ""])


# ── the four fixed calls ─────────────────────────────────────────────────────

_AUDIT_BASE = {
    "CLOUD_SQL_CONNECTION_NAME": SECRETS["cloud-sql-connection-name"],
    "DB_USER": SECRETS["db-trading-user"],
    "DB_NAME": "trading",
    "PROJECT_ID": "fake-proj-000",
    "AUDIT_TRACKING_ISSUE": "",
}
AUDIT_ENV = {
    "deploy_audit_walkforward": {
        **_AUDIT_BASE,
        "AUDIT_SCRIPT_MODULE": "scripts.analysis.per_factor_walkforward",
        "AUDIT_SCRIPT_ARGS": "--folds 4",
        "AUDIT_WINDOW_DAYS": "30",
        "AUDIT_ALLOWED_EXIT_CODES": "0,3",
        "AUDIT_COMMENT_TITLE": "\U0001f501 Weekly walk-forward audit",
    },
    "deploy_audit_brief_bias": {
        **_AUDIT_BASE,
        "AUDIT_SCRIPT_MODULE": "scripts.analysis.verify_brief_bias",
        "AUDIT_SCRIPT_ARGS": "--since 2026-05-12 --tickers SPY,IWM,QQQ",
        "AUDIT_WINDOW_DAYS": "0",
        "AUDIT_ALLOWED_EXIT_CODES": "0",
        "AUDIT_COMMENT_TITLE": "\U0001f50d Weekly brief bias verification",
    },
}


def test_audit_jobs_env_parses_to_the_intended_set():
    calls = sweep(TEXT, False)["calls"]
    for fn, want in AUDIT_ENV.items():
        verbs = [c[2] for c in calls[fn]]
        assert verbs == ["create", "update"], (fn, verbs)
        for argv in calls[fn]:
            values = _flag_values(argv, "--set-env-vars")
            assert len(values) == 1, (fn, argv)
            assert parse_dict_arg(values[0]) == want, (fn, argv[2], values[0])


# Recorded from the merge base (origin/main 7322f23) with the stub values above, then
# with only this change's edits applied: the news update loses `--remove-env-vars
# NEWS_TICKERS`, the SPX greeks calls take `--args=--ticker,SPX`. Everything else stays.
_IMG = "us-east1-docker.pkg.dev/fake-proj-000/trading/trading-system@sha256:0000"
_SA = "trading-runner@fake-proj-000.iam.gserviceaccount.com"
MERGE_BASE_CALLS: dict[str, list[list[str]]] = {
    'deploy_fetch_news_sentiment': [
        ['run', 'jobs', 'create', 'fetch-news-sentiment', '--image', _IMG, '--region', 'us-east1', '--memory', '512Mi', '--cpu', '1', '--max-retries', '1', '--service-account', _SA, '--command', 'python,-m,gcp.fetchers.fetch_news_sentiment', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
        ['run', 'jobs', 'update', 'fetch-news-sentiment', '--image', _IMG, '--region', 'us-east1', '--command', 'python,-m,gcp.fetchers.fetch_news_sentiment', '--args', '', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
    ],
    'deploy_fetch_news_sentiment_earnings': [
        ['run', 'jobs', 'create', 'fetch-news-sentiment-earnings', '--image', _IMG, '--region', 'us-east1', '--memory', '512Mi', '--cpu', '1', '--max-retries', '1', '--service-account', _SA, '--command', 'python,-m,gcp.fetchers.fetch_news_sentiment', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
        ['run', 'jobs', 'update', 'fetch-news-sentiment-earnings', '--image', _IMG, '--region', 'us-east1', '--command', 'python,-m,gcp.fetchers.fetch_news_sentiment', '--args', '', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
        ['run', 'jobs', 'update', 'fetch-news-sentiment-earnings', '--region', 'us-east1', '--update-env-vars', '^@^EARNINGS_WINDOW_DAYS=7@NEWS_SINCE_LAST=1@MAX_TICKERS=300', '--quiet'],
    ],
    'deploy_fetch_news_sentiment_topics': [
        ['run', 'jobs', 'create', 'fetch-news-sentiment-topics', '--image', _IMG, '--region', 'us-east1', '--memory', '512Mi', '--cpu', '1', '--max-retries', '1', '--service-account', _SA, '--command', 'python,-m,gcp.fetchers.fetch_news_sentiment', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
        ['run', 'jobs', 'update', 'fetch-news-sentiment-topics', '--image', _IMG, '--region', 'us-east1', '--command', 'python,-m,gcp.fetchers.fetch_news_sentiment', '--args', '', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
        ['run', 'jobs', 'update', 'fetch-news-sentiment-topics', '--region', 'us-east1', '--update-env-vars', '^@^NEWS_TOPICS=mergers_and_acquisitions,technology,financial_markets,earnings,life_sciences', '--quiet'],
    ],
    'deploy_compute_spx_greeks_backfill': [
        ['run', 'jobs', 'create', 'compute-spx-greeks-backfill', '--image', _IMG, '--region', 'us-east1', '--memory', '2Gi', '--cpu', '1', '--max-retries', '0', '--task-timeout', '43200', '--service-account', _SA, '--command', 'python,-m,scripts.maintenance.compute_spx_greeks', '--args=--ticker,SPX', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
        ['run', 'jobs', 'update', 'compute-spx-greeks-backfill', '--image', _IMG, '--region', 'us-east1', '--command', 'python,-m,scripts.maintenance.compute_spx_greeks', '--args=--ticker,SPX', DB_SECRET_FLAG, '--set-env-vars', ENV_STRING, '--quiet'],
    ],
}


def test_news_update_sets_env_once_and_removes_nothing():
    calls = sweep(TEXT, False)["calls"]["deploy_fetch_news_sentiment"]
    update = [c for c in calls if c[2] == "update"]
    assert len(update) == 1, calls
    assert _flag_values(update[0], "--set-env-vars") == [ENV_STRING]
    assert not _has(update[0], "--remove-env-vars"), update[0]


def test_news_and_spx_calls_otherwise_equal_the_merge_base():
    calls = sweep(TEXT, False)["calls"]
    for fn, want in MERGE_BASE_CALLS.items():
        assert calls[fn] == want, fn


def test_spx_greeks_args_use_the_attached_form():
    calls = sweep(TEXT, False)["calls"]["deploy_compute_spx_greeks_backfill"]
    assert [c[2] for c in calls] == ["create", "update"], calls
    for argv in calls:
        assert "--args=--ticker,SPX" in argv and "--args" not in argv, argv


# ── fetchers deploys only ────────────────────────────────────────────────────

def _dispatch_arm(label: str) -> str:
    code = "\n".join(l for l in TEXT.splitlines() if not l.lstrip().startswith("#"))
    dispatch = code[code.index('case "${1:-help}" in'):]
    body = dispatch[:dispatch.index("\nesac")]
    for m in re.finditer(r"^\s{4}([a-z0-9|_\-\"]+)\)(.*?);;", body, re.S | re.M):
        if label in [x.strip().strip('"') for x in m.group(1).split("|")]:
            return m.group(2)
    raise AssertionError(f"{label}) dispatcher arm missing")


def test_fetchers_arm_runs_no_backfill_and_names_the_separate_step():
    arm = _dispatch_arm("fetchers")
    assert "backfill_watchlist" not in arm, arm
    assert not re.search(r"\bpython3?\b", arm), arm
    assert re.search(r"_run build_image deploy_fetchers\s*$", arm.splitlines()[0]), arm
    assert "./gcp/deploy.sh backfill" in arm, arm
    assert "backfill_watchlist" in _dispatch_arm("all") and "backfill_watchlist" in _dispatch_arm("backfill")


def test_help_says_backfill_runs_automatically_only_after_all():
    with tempfile.TemporaryDirectory() as tmp:
        bindir = Path(tmp)
        (bindir / "gcloud").write_text("#!/bin/bash\nexit 0\n")
        (bindir / "gcloud").chmod(0o755)
        out = subprocess.run(["bash", str(DEPLOY_SH), "help"], capture_output=True, text=True, timeout=60,
                             env={"PATH": f"{bindir}:/usr/bin:/bin", "HOME": tmp, "PROJECT_ID": "fake-proj-000"},
                             stdin=subprocess.DEVNULL)
    help_text = re.sub(r"\s+", " ", out.stdout)
    assert "backfill Idempotently backfill" in help_text, out.stdout[-2000:]
    section = help_text[help_text.index("backfill Idempotently backfill"):][:300]
    assert "after `all` only" in section, section
    assert "after `fetchers` and `all`" not in help_text
    assert "fetchers Deploy all data-fetching Cloud Run jobs (deploy only; no data backfill)" in help_text




# ── differential: against the merge base named by DEPLOY_BASELINE_REV ───────
#   DEPLOY_BASELINE_REV=$(git merge-base origin/main HEAD) \
#       pytest tests/gcp/test_deploy_flag_syntax.py -q

CHANGED_FNS = {"deploy_fetch_news_sentiment", "deploy_audit_walkforward",
               "deploy_audit_brief_bias", "deploy_compute_spx_greeks_backfill"}
BROKEN_ON_BASE = CHANGED_FNS | {"deploy_fetchers"}   # deploy_fetchers runs the four


@pytest.fixture(scope="module")
def baseline() -> str:
    rev = os.environ.get("DEPLOY_BASELINE_REV")
    if not rev:
        pytest.skip("differential evidence for this pull request: set DEPLOY_BASELINE_REV=<merge base>")
    r = subprocess.run(["git", "show", f"{rev}:gcp/deploy.sh"], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_merge_base_fails_the_rules_and_names_the_four_functions(baseline):
    assert set(all_violations(baseline)) == BROKEN_ON_BASE, all_violations(baseline)


def _outside_functions(text: str) -> list[str]:
    out = text
    for _, body in _functions(text):
        out = out.replace(body, "<fn>", 1)
    return out.splitlines()


def test_deploy_sh_changes_only_inside_the_named_places(baseline):
    base_fns, head_fns = dict(_functions(baseline)), dict(_functions(TEXT))
    assert set(base_fns) == set(head_fns)
    assert {n for n in head_fns if head_fns[n] != base_fns[n]} == CHANGED_FNS
    changed = [l[1:] for l in difflib.unified_diff(_outside_functions(baseline), _outside_functions(TEXT), n=0, lineterm="")
               if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    allowed = (
        re.compile(r"^\s{4}fetchers\) _run build_image deploy_fetchers( backfill_watchlist ;;)?$"),
        re.compile(r'^\s{8}echo "Watchlist data backfill is separate: \./gcp/deploy\.sh backfill \(writes to Cloud SQL\)\." ;;$'),
        re.compile(r'^\s{8}echo "  fetchers   Deploy all data-fetching Cloud Run jobs'),
        # the two continuation lines of the `backfill` help entry
        re.compile(r'^\s{8}echo "\s{13}(Pass --tickers AVGO,NVDA to override\. |Runs automatically after |after \\`fetchers\\` and \\`all\\`\.")'),
    )
    stray = [l for l in changed if not any(p.match(l) for p in allowed)]
    assert not stray, stray


def test_backfill_all_and_credential_dispatch_are_byte_identical(baseline):
    base_fns, head_fns = dict(_functions(baseline)), dict(_functions(TEXT))
    assert head_fns["backfill_watchlist"] == base_fns["backfill_watchlist"]
    creds = lambda t: [l for l in t.splitlines() if "_NEEDS_DEPLOY_CREDS" in l]
    assert creds(TEXT) == creds(baseline) and creds(TEXT)
    for label in ("backfill", "all"):
        assert _arm_of(TEXT, label) == _arm_of(baseline, label), label


def _arm_of(text: str, label: str) -> str:
    dispatch = text[text.index('case "${1:-help}" in'):]
    body = dispatch[:dispatch.index("\nesac")]
    for m in re.finditer(r"^\s{4}([a-z0-9|_\-\"]+)\)(.*?);;", body, re.S | re.M):
        if label in [x.strip().strip('"') for x in m.group(1).split("|")]:
            return m.group(0)
    raise AssertionError(f"{label}) dispatcher arm missing")
