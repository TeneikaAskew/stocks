---
feat_id: FEAT-CICD-001
req_ids: [REQ-DEPLOY-001]
issues: []
canvases: []
done_when:
  - "tests/meta/test_hermetic_gcloud.py proves that inside the test suite gcloud, gsutil and bq resolve to the tripwire when no fake is ahead of it, and the tripwire exits non-zero naming the command it refused"
  - "tests/meta/test_hermetic_gcloud.py proves that a fake gcloud made non-executable (the noexec case) falls through to the tripwire, not to an installed gcloud"
  - "tests/meta/test_hermetic_gcloud.py proves that the suite's CLOUDSDK_CONFIG is an empty directory, CLOUDSDK_AUTH_DISABLE_CREDENTIALS is true, and CLOUDSDK_AUTH_ACCESS_TOKEN and CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE are unset"
  - "tests/meta/test_hermetic_gcloud.py proves that tests/conftest.py::_gcloud_secret, the deliberate live-backend path, runs gcloud with the environment captured before the guard"
  - "With an installed gcloud replaced by a logging sentinel and pytest's temp directory on a noexec mount, the six fake-gcloud test files log zero sentinel calls, against 50 before (command and output in the PR)"
  - "make test passes apart from the sandbox-only failures listed in the PR, and the delivery gate passes with the FEAT-CICD-001 record and PR traceability updated"
status: approved
supersedes: null
---

# Hermetic gcloud guard for the test suite

## Problem

Six files under `tests/gcp/` test `deploy.sh` and related scripts by writing a
fake `gcloud` into pytest's temp directory and putting that directory first on
PATH: `test_apply_schema_trigger.py`, `test_deploy_audit_infra_drift.py`,
`test_deploy_image_pinning.py`, `test_mag_persist_production_model.py`,
`test_platform_deploy_service_config.py` and `test_staging_deploy_paths.py`.
Most of them copy the caller's whole environment, credentials included, and
most `gcloud` calls in `deploy.sh` pass no `--project`, so a real `gcloud`
uses its configured default project, which is production.

If the fake cannot execute, bash does not stop: it keeps searching PATH and
runs the installed `gcloud`. Reproduced on 2026-10-18 over the six files, with
a logging sentinel in place of the real `gcloud`:

| pytest temp directory | result | calls reaching the sentinel |
|---|---|---|
| executable | 189 passed | 0 |
| `noexec` mount | 42 failed, 147 passed | 50 |

The 50 include, against the production project or the machine's own config:

- `run jobs create`/`update audit-infra-drift --image img@sha256:1 --service-account sa@proj...` (2 each);
- `run jobs execute magnitude-engine ...` (4), a billable research run;
- `secrets versions access latest --secret=db-trading-user`, which would print
  the database password into test output;
- `projects add-iam-policy-binding adept-mountain-474619-d4 ... roles/firebaseauth.admin`;
- `config set project test-project`, which rewrites the developer's default
  gcloud project;
- `builds submit` of the apply-schema build config (5).

That exact call reached production on 2026-10-12, 22:06 to 22:20 UTC, as
`claude-web@`, from another session's test run:

- two `run jobs create`/`update` pairs on `audit-infra-drift`, refused
  (`iam.serviceaccounts.actAs` denied on `sa@proj`), so the job stayed at
  generation 4;
- five `builds submit` calls, each run and failed (no `proj` registry);
- five apply-schema build submissions, refused by Cloud Build
  (`FAILED_PRECONDITION`) after their sources were uploaded.

The audit log shows no `magnitude-engine` execution and no IAM change in that
window. Secret reads are not checked: Secret Manager data-access logging
records none, which does not show that none happened. Nothing in production
changed. The ten staged source archives were deleted on 2026-10-18. Whether
that session's temp directory was `noexec` is not checked; any way the fake is
skipped ends the same way.

## Non-goals

- No change to `deploy.sh` or any production script, including adding
  `--project` to its calls.
- No change to Python client-library credentials (`GOOGLE_APPLICATION_CREDENTIALS`):
  `requires_data_backend` tests deliberately read real backends on a developer
  machine, and `gcloud` does not authenticate from that variable.
- No edits to the six test files: the guard lives once, in the suite setup.
- `tests/integration/` is outside `make test` and unchanged.

## Approaches considered

1. Each fake-gcloud helper asserts that PATH resolves to its fake. Six edits,
   and the seventh helper someone writes is unguarded.
2. Strip credentials for `gcloud` once, at suite start. Covers every current
   and future test, but a skipped fake fails with an authentication error,
   not a clear message.
3. **Chosen: 2 plus a tripwire.** At suite start, point `gcloud` at an empty
   config directory, drop its token variable, and put a committed tripwire
   directory first on PATH. A skipped fake hits the tripwire, which fails with
   a message naming the call; an installed `gcloud` is never reached, and even
   if it were, it would load no credential at all.

## Design

In `tests/conftest.py`, at import time, before any test builds its subprocess
environment from `os.environ`:

- `CLOUDSDK_CONFIG` = a new empty temporary directory (no account, no project),
  removed at session end.
- `CLOUDSDK_AUTH_ACCESS_TOKEN` and `CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE`
  removed.
- `CLOUDSDK_AUTH_DISABLE_CREDENTIALS=true`. An empty config is not enough on
  its own: a fresh config reports `core/check_gce_metadata = True`, so on a GCE
  runner or in Cloud Shell gcloud would take an account and project from the
  instance metadata server. With credentials disabled, gcloud loads none, from
  any source (Codex on #1535).
- `tests/fixtures/gcloud_tripwire/` prepended to PATH. It holds executable
  `gcloud`, `gsutil` and `bq` scripts that print `hermetic test suite: real
  <cmd> refused: <args>` to stderr and exit 97.
- `CLOUDSDK_CORE_PROJECT` is NOT set: `test_deploy_image_pinning.py` checks
  that `deploy.sh` reads the active config when it is unset.

The tripwire lives in the repository, not in a temp directory, so a `noexec`
temp mount cannot disable it. A test's own fake, prepended ahead of it, still
wins whenever it can execute, so passing tests are unaffected.

One path in the suite reaches GCP on purpose. In `--mode=live` (the default),
`db_conn` connects to Cloud SQL, and when no `DB_*` variables are set,
`_gcloud_secret` reads the two database secrets by running the owner's
`gcloud.cmd` at its absolute Windows path. It bypasses PATH, so the tripwire
never sees it, but it would inherit the empty, credential-less config and
`db_conn` would skip where it used to connect (Codex on #1535). So the guard
first snapshots `os.environ` as `_PRE_GUARD_ENV`, and `_gcloud_secret` passes
`env=_PRE_GUARD_ENV`. That path's behaviour is unchanged: an explicit,
read-only secret read, by absolute path, on the owner's machine.

`tests/meta/test_hermetic_gcloud.py` carries the regression tests in
`done_when` 1 to 4. Item 5 is the reproduction above, rerun on the branch.

Capacity: test-only change. No job, query or build; about 0.1 s added to suite
start. Cost $0.

## Risks

- A test that relied on reaching a real `gcloud` would now fail. None of the
  six files does: with every fake executable they reached the sentinel 0 times.
  Item 6's full-suite run catches any other file.
- The live path above still reaches production. That is its purpose; this
  change only stops the guard from silently disabling it.
- Running a single test file still loads `tests/conftest.py`, so it is covered.
  A run with `--noconftest` is not; that flag is not used by `make test` or CI.
