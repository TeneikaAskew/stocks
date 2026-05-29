"""Tests for gcp/db_query_job.py.

Validates the Cloud Run env-var → run_query dispatch logic, particularly
the GCS result URI resolution that the dispatching sandbox depends on
to locate artifacts.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    """Clear every env var the resolver inspects so each test sees a clean slate."""
    for k in (
        'SQL', 'SQL_FILE', 'COMMIT', 'STATEMENT_TIMEOUT_SECONDS',
        'RESULT_GCS_URI', 'GCS_BUCKET', 'GCP_PROJECT',
        'CLOUD_RUN_EXECUTION', 'CLOUD_RUN_JOB_EXECUTION', 'K_REVISION',
    ):
        monkeypatch.delenv(k, raising=False)
    yield


class TestResolveResultUri:
    def test_explicit_uri_takes_precedence(self, monkeypatch):
        monkeypatch.setenv('RESULT_GCS_URI', 'gs://custom-bucket/audit/run-1/')
        monkeypatch.setenv('CLOUD_RUN_EXECUTION', 'db-query-abcde')  # ignored
        # Re-import to pick up clean module state under fresh env.
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        # Trailing slash should be stripped.
        assert db_query_job._resolve_result_uri() == 'gs://custom-bucket/audit/run-1'

    def test_defaults_to_project_bucket_with_execution_id(self, monkeypatch):
        monkeypatch.setenv('GCP_PROJECT', 'my-project')
        monkeypatch.setenv('CLOUD_RUN_EXECUTION', 'db-query-xyz')
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        assert db_query_job._resolve_result_uri() == \
            'gs://my-project-trading-data/query-results/db-query-xyz'

    def test_falls_back_to_local_pid_when_no_execution_name(self, monkeypatch):
        monkeypatch.setenv('GCS_BUCKET', 'mybucket')
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        uri = db_query_job._resolve_result_uri()
        # No CLOUD_RUN_EXECUTION → suffix is "local-<pid>"
        assert uri.startswith('gs://mybucket/query-results/local-')

    def test_explicit_uri_no_trailing_slash_unchanged(self, monkeypatch):
        monkeypatch.setenv('RESULT_GCS_URI', 'gs://b/p')
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        assert db_query_job._resolve_result_uri() == 'gs://b/p'


class TestMainDispatch:
    def test_rejects_both_sql_and_sql_file(self, monkeypatch, capsys):
        monkeypatch.setenv('SQL', 'SELECT 1')
        monkeypatch.setenv('SQL_FILE', 'gcp/queries/x.sql')
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        rc = db_query_job.main()
        assert rc == 2
        err = capsys.readouterr().err
        assert 'exactly one of SQL / SQL_FILE' in err

    def test_rejects_neither_sql_nor_sql_file(self, monkeypatch, capsys):
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        rc = db_query_job.main()
        assert rc == 2
        err = capsys.readouterr().err
        assert 'exactly one of SQL / SQL_FILE' in err

    def test_invokes_run_query_with_inline_sql(self, monkeypatch):
        monkeypatch.setenv('SQL', 'SELECT 1')
        monkeypatch.setenv('RESULT_GCS_URI', 'gs://b/p')
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        with patch.object(db_query_job.subprocess, 'run') as run_mock:
            run_mock.return_value.returncode = 0
            rc = db_query_job.main()
        assert rc == 0
        cmd = run_mock.call_args[0][0]
        assert '--sql' in cmd
        assert 'SELECT 1' in cmd
        assert '--upload-to-gcs' in cmd
        assert 'gs://b/p' in cmd
        assert '--commit' not in cmd  # default

    def test_invokes_run_query_with_sql_file_and_commit(self, monkeypatch):
        monkeypatch.setenv('SQL_FILE', 'gcp/queries/audit_ticker_coverage.sql')
        monkeypatch.setenv('COMMIT', 'true')
        monkeypatch.setenv('STATEMENT_TIMEOUT_SECONDS', '600')
        monkeypatch.setenv('RESULT_GCS_URI', 'gs://b/p')
        import importlib
        from gcp import db_query_job
        importlib.reload(db_query_job)
        with patch.object(db_query_job.subprocess, 'run') as run_mock:
            run_mock.return_value.returncode = 0
            rc = db_query_job.main()
        assert rc == 0
        cmd = run_mock.call_args[0][0]
        assert '--sql-file' in cmd
        assert 'gcp/queries/audit_ticker_coverage.sql' in cmd
        assert '--commit' in cmd
        assert '--statement-timeout-seconds' in cmd
        assert '600' in cmd
