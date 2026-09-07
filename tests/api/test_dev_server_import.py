"""`api.main` must import the way the dev server actually launches it.

`make api` (Makefile:73) and `scripts/dev_server.sh` (line 51) both `cd platform`
before exec'ing uvicorn, so the repository root is NOT on sys.path when
`api.main` is imported. main.py adds it (`sys.path.insert(0, PROJECT_ROOT)`),
but only partway down the file -- so a `from lib...` import placed above that
line raises `ModuleNotFoundError: No module named 'lib'` and the server never
starts.

The rest of the suite cannot catch this. pytest runs from the repository root,
where `lib` is importable via the cwd, so an eager `lib` import at the top of
main.py passes 4,200 tests and breaks `make api`. That happened on this branch:
`from lib.single_flight import SingleFlight` landed at line 16, eleven lines
above the bootstrap (Codex, PR #991).

So this runs a subprocess in the real launch layout rather than asserting
anything about the source text -- an import-order rule expressed as a regex
would be defeated by the next spelling, and the launch is cheap to reproduce.
"""
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
PLATFORM = REPO / "platform"

pytest.importorskip("fastapi")


def _import_from(cwd: pathlib.Path, module: str) -> subprocess.CompletedProcess:
    """Import `module` in a subprocess with an EMPTY PYTHONPATH.

    Empty, not inherited: pytest exports the repository root into the child's
    PYTHONPATH, which would put `lib` back on sys.path and hide the very thing
    this test exists to catch.
    """
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=str(cwd), env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp"},
        capture_output=True, text=True, timeout=180,
    )


def test_api_main_imports_from_the_platform_directory():
    """The layout `make api` and scripts/dev_server.sh actually use."""
    proc = _import_from(PLATFORM, "api.main")
    assert proc.returncode == 0, (
        "`cd platform && uvicorn api.main:app` cannot start — this is exactly "
        "how `make api` and scripts/dev_server.sh launch the server, and the "
        "rest of the suite runs from the repository root where the failing "
        f"import resolves:\n{proc.stderr[-2000:]}")


def test_the_launch_commands_still_cd_into_platform():
    """If they stop doing that, the test above is asserting the wrong layout."""
    makefile = (REPO / "Makefile").read_text()
    assert "cd platform && exec uvicorn api.main:app" in makefile, (
        "the `api` target no longer cd's into platform — re-check what layout "
        "test_api_main_imports_from_the_platform_directory should assert")
    dev_server = (REPO / "scripts" / "dev_server.sh").read_text()
    assert "cd platform" in dev_server, (
        "scripts/dev_server.sh no longer cd's into platform — same question")
