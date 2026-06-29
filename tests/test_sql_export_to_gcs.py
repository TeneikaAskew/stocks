"""Tests for gcp/sql_export_to_gcs.py.

Key invariant: POLL_MAX_SECS must be strictly less than the Cloud Run
task-timeout (10800 s) by at least 300 s of headroom. The 2026-06-28 outage
was caused by POLL_MAX_SECS == task-timeout (both 3600 s), which made Cloud
Run SIGKILL the container before the Python TimeoutError could surface.
"""

import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch

# Stub google-auth before importing our module so it loads cleanly in CI
# environments that lack the full GCP SDK.
for _name in (
    "google",
    "google.auth",
    "google.auth.default",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.oauth2",
    "google.oauth2.service_account",
):
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

# Also stub lib.logging_config
if "lib" not in sys.modules:
    _lib = types.ModuleType("lib")
    sys.modules["lib"] = _lib
if "lib.logging_config" not in sys.modules:
    _lc = types.ModuleType("lib.logging_config")
    _lc.setup_logging = lambda: None
    sys.modules["lib.logging_config"] = _lc

import gcp.sql_export_to_gcs as mod  # noqa: E402

TASK_TIMEOUT_SECS = 10800  # must match deploy.sh --task-timeout for cloud-sql-weekly-export


class TestPollCapInvariant(unittest.TestCase):
    def test_poll_max_secs_less_than_task_timeout(self):
        """POLL_MAX_SECS must never equal or exceed the Cloud Run task-timeout."""
        self.assertLess(
            mod.POLL_MAX_SECS,
            TASK_TIMEOUT_SECS,
            "POLL_MAX_SECS must be < Cloud Run task-timeout so Python raises "
            "TimeoutError before Cloud Run SIGKILLs the container.",
        )

    def test_poll_max_secs_has_sufficient_headroom(self):
        """Require at least 300 s gap so there is time to log and exit cleanly."""
        gap = TASK_TIMEOUT_SECS - mod.POLL_MAX_SECS
        self.assertGreaterEqual(
            gap,
            300,
            f"Gap between task-timeout and POLL_MAX_SECS is only {gap}s; need ≥300s.",
        )


class TestWaitForOp(unittest.TestCase):
    def _make_response(self, status: str, error: dict | None = None):
        resp = MagicMock()
        resp.status_code = 200
        payload = {"status": status}
        if error:
            payload["error"] = error
        resp.json.return_value = payload
        return resp

    @patch("gcp.sql_export_to_gcs._get_token", return_value="tok")
    @patch("gcp.sql_export_to_gcs.time.sleep")
    @patch("gcp.sql_export_to_gcs.requests.get")
    def test_wait_for_op_returns_on_done(self, mock_get, mock_sleep, _tok):
        mock_get.return_value = self._make_response("DONE")
        result = mod.wait_for_op("projects/p/operations/op1")
        self.assertEqual(result["status"], "DONE")
        mock_sleep.assert_called_once_with(mod.POLL_INTERVAL_SECS)

    @patch("gcp.sql_export_to_gcs._get_token", return_value="tok")
    @patch("gcp.sql_export_to_gcs.time.monotonic")
    @patch("gcp.sql_export_to_gcs.time.sleep")
    @patch("gcp.sql_export_to_gcs.requests.get")
    def test_wait_for_op_raises_timeout(self, mock_get, mock_sleep, mock_mono, _tok):
        # First call sets `started=0`; second call returns POLL_MAX_SECS+1 so
        # the elapsed check (mono()-started > POLL_MAX_SECS) triggers.
        mock_mono.side_effect = [0, mod.POLL_MAX_SECS + 1]
        with self.assertRaises(TimeoutError) as ctx:
            mod.wait_for_op("projects/p/operations/op2")
        self.assertIn(str(mod.POLL_MAX_SECS), str(ctx.exception))
        mock_get.assert_not_called()

    @patch("gcp.sql_export_to_gcs._get_token", return_value="tok")
    @patch("gcp.sql_export_to_gcs.time.sleep")
    @patch("gcp.sql_export_to_gcs.requests.get")
    def test_wait_for_op_raises_on_export_error(self, mock_get, mock_sleep, _tok):
        mock_get.return_value = self._make_response(
            "DONE", error={"code": 500, "message": "internal error"}
        )
        with self.assertRaises(RuntimeError) as ctx:
            mod.wait_for_op("projects/p/operations/op3")
        self.assertIn("Export failed", str(ctx.exception))

    @patch("gcp.sql_export_to_gcs._get_token", return_value="tok")
    @patch("gcp.sql_export_to_gcs.time.sleep")
    @patch("gcp.sql_export_to_gcs.requests.get")
    def test_wait_for_op_polls_until_done(self, mock_get, mock_sleep, _tok):
        running = self._make_response("RUNNING")
        done = self._make_response("DONE")
        mock_get.side_effect = [running, running, done]
        result = mod.wait_for_op("projects/p/operations/op4")
        self.assertEqual(result["status"], "DONE")
        self.assertEqual(mock_get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
