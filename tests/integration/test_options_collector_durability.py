"""Run the approved scheduled-entry durability control against CI's real Postgres."""
import importlib.util
import os
from pathlib import Path
import pytest

_path = Path(__file__).resolve().parents[1] / 'gcp/test_av_options_collector_entry.py'
_spec = importlib.util.spec_from_file_location('options_collector_entry_acceptance', _path)
_entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_entry)


@pytest.fixture
def collector_integration_engine(request):
    if os.environ.get('OPTIONS_TEST_PG_SOCKET'):
        yield from _entry.options_postgres_engine.__wrapped__()
        return
    # Validate the existing CI target before its fixture can initialize any engine.
    assert os.environ.get('DB_HOST') in {'localhost', '127.0.0.1', '::1'}
    assert os.environ.get('DB_NAME') == 'trading'
    engine = request.getfixturevalue('db_engine')
    assert engine.url.host in {'localhost', '127.0.0.1', '::1'}
    assert engine.url.database == 'trading'
    yield engine


def test_scheduled_entry_preserves_sibling_commit_on_later_failure(monkeypatch, collector_integration_engine):
    _entry.test_scheduled_entry_preserves_sibling_commit_on_later_failure(monkeypatch, collector_integration_engine)
