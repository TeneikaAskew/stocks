"""What `platform/deploy.sh` configures on each API service.

Eleven rows of the site traceability matrix (`docs/product/03-SITE-TRACEABILITY.md`)
depend on configuration this script hands Cloud Run: the services' `AUTH_MODE` and
service account, the Firebase web config of the public staging service, the
`MOVEMENT_STATEMENT_ENABLED` flag, the `av-api-key` secret and the
`roles/firebaseauth.admin` grant to the runtime service account (stocks#1345).

The routine Cloud Build deploys change the image and merge one environment key, and
leave the rest of the service as this script last set it, so this script is where
those settings live. These tests run it, in a scratch tree, against a stub `gcloud`
that records every call, and assert what it asked Cloud Run for in each mode. A text
match over the script would prove the text; running it proves the mode logic too.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
PROJECT = "adept-mountain-474619-d4"
RUNTIME_SA = f"trading-platform-svc@{PROJECT}.iam.gserviceaccount.com"
DIGEST = "gcr.io/" + PROJECT + "/solyra-api@sha256:" + "a" * 64

_STUB_GCLOUD = r'''#!__PYTHON__
import json, sys
args = sys.argv[1:]
with open(__LOG__, "a") as fh:
    fh.write(json.dumps(args) + "\n")
if args[:3] == ["run", "services", "describe"]:
    if "--format=json" in args:
        sys.stderr.write("ERROR: (gcloud.run.services.describe) NOT_FOUND: service not found\n")
        sys.exit(1)
    print("https://service.example.run.app")
elif args[:3] == ["container", "images", "describe"]:
    print(__DIGEST__)
sys.exit(0)
'''


def _run(tmp_path, **mode):
    """Run a copy of platform/deploy.sh with `mode` as its environment.

    Returns the completed process and the list of recorded gcloud argument lists."""
    tree = tmp_path / "tree"
    (tree / "platform").mkdir(parents=True)
    (tree / "gcp" / "cloudbuild").mkdir(parents=True)
    shutil.copy2(REPO / "platform" / "deploy.sh", tree / "platform" / "deploy.sh")
    for stub in (tree / "gcp" / "deploy.sh",
                 tree / "gcp" / "cloudbuild" / "assert_no_concurrent_staging_deploy.sh"):
        stub.write_text("#!/usr/bin/env bash\nexit 0\n")
        stub.chmod(0o755)
    log = tmp_path / "gcloud-calls.jsonl"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(_STUB_GCLOUD.replace("__PYTHON__", sys.executable)
                      .replace("__LOG__", repr(str(log)))
                      .replace("__DIGEST__", repr(DIGEST)))
    gcloud.chmod(0o755)
    # A clean environment, not the caller's: an inherited AUTH_MODE, PROJECT_ID or
    # RUN_SA would change what the script deploys and the test would follow it.
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path),
           "DB_USER": "postgres", "DB_NAME": "trading", "IMAGE_TAG": "testtag", **mode}
    proc = subprocess.run(["bash", "platform/deploy.sh"], cwd=tree, env=env,
                          capture_output=True, text=True, timeout=60)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return proc, calls


def _deploy(calls):
    """The single `gcloud run deploy` call, parsed into what it configures."""
    deploys = [c for c in calls if c[:2] == ["run", "deploy"]]
    assert len(deploys) == 1, deploys
    args = deploys[0]
    def value(flag):
        assert args.count(flag) == 1, (flag, args)
        return args[args.index(flag) + 1]
    raw_env = value("--set-env-vars")
    assert raw_env.startswith("^|^"), raw_env
    env = dict(pair.split("=", 1) for pair in raw_env[3:].split("|"))
    secrets = dict(pair.split("=", 1) for pair in value("--set-secrets").split(","))
    return {"service": args[2], "service_account": value("--service-account"),
            "env": env, "secrets": secrets, "args": args}


def _ran(calls, *prefix):
    return any(c[:len(prefix)] == list(prefix) for c in calls)


def test_prod_deploy_configures_solyra_api_prod(tmp_path):
    proc, calls = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    d = _deploy(calls)
    assert d["service"] == "solyra-api-prod"
    assert d["service_account"] == RUNTIME_SA
    assert d["env"]["AUTH_MODE"] == "iap"
    assert d["env"]["MOVEMENT_STATEMENT_ENABLED"] == "true"
    assert d["secrets"]["AV_API_KEY"] == "av-api-key:latest"
    assert d["secrets"]["ALPHA_VANTAGE_API_KEY"] == "av-api-key:latest"
    # REQ-SECRET-001: the key travels as a secret reference, never as a plain value.
    assert "AV_API_KEY" not in d["env"] and "ALPHA_VANTAGE_API_KEY" not in d["env"]
    assert "--no-allow-unauthenticated" in d["args"]
    assert "--allow-unauthenticated" not in d["args"]


def test_staging_service_deploy_configures_solyra_api_staging(tmp_path):
    proc, calls = _run(tmp_path, STAGING_SERVICE="1", FIREBASE_API_KEY="test-api-key",
                       FIREBASE_AUTH_DOMAIN="test.firebaseapp.com", FIREBASE_APP_ID="1:2:web:3")
    assert proc.returncode == 0, proc.stderr
    d = _deploy(calls)
    assert d["service"] == "solyra-api-staging"
    assert d["service_account"] == RUNTIME_SA
    assert d["env"]["AUTH_MODE"] == "firebase"
    assert d["env"]["FIREBASE_API_KEY"] == "test-api-key"
    assert d["env"]["FIREBASE_AUTH_DOMAIN"] == "test.firebaseapp.com"
    assert d["env"]["FIREBASE_APP_ID"] == "1:2:web:3"
    assert d["env"]["FIREBASE_PROJECT_ID"] == PROJECT
    assert d["env"]["MOVEMENT_STATEMENT_ENABLED"] == "true"
    assert d["secrets"]["AV_API_KEY"] == "av-api-key:latest"
    assert d["secrets"]["ALPHA_VANTAGE_API_KEY"] == "av-api-key:latest"
    # REQ-SECRET-001 holds on this path too: the Firebase block appends to the
    # environment, and nothing it appends may carry the key as a plain value.
    assert "AV_API_KEY" not in d["env"] and "ALPHA_VANTAGE_API_KEY" not in d["env"]
    assert "--allow-unauthenticated" in d["args"]
    assert "--no-allow-unauthenticated" not in d["args"]


def test_staging_service_deploy_refuses_without_firebase_config(tmp_path):
    proc, calls = _run(tmp_path, STAGING_SERVICE="1",
                       FIREBASE_AUTH_DOMAIN="test.firebaseapp.com", FIREBASE_APP_ID="1:2:web:3")
    assert proc.returncode != 0
    assert "FIREBASE_API_KEY" in proc.stderr
    assert not _ran(calls, "builds", "submit"), calls
    assert not _ran(calls, "run", "deploy"), calls


def test_setup_iam_grants_firebaseauth_admin_and_does_not_deploy(tmp_path):
    proc, calls = _run(tmp_path, SETUP_IAM="1")
    assert proc.returncode == 0, proc.stderr
    grants = [c for c in calls if c[:2] == ["projects", "add-iam-policy-binding"]]
    assert grants and grants[0][2] == PROJECT, calls
    assert f"--member=serviceAccount:{RUNTIME_SA}" in grants[0]
    assert "--role=roles/firebaseauth.admin" in grants[0]
    assert not _ran(calls, "builds", "submit"), calls
    assert not _ran(calls, "run", "deploy"), calls
