"""The Cloud SQL Connector's aiohttp session is closed at process exit.

Added 2026-09-15. `get_engine()` builds `Connector(refresh_strategy="lazy")`,
which owns an aiohttp ClientSession it uses to fetch the ephemeral client
cert from the SQL Admin API. Nothing ever closed it, so every Cloud Run Job
ended with:

    ERROR asyncio - Unclosed client session
    client_session: <aiohttp.client.ClientSession object at 0x...>

Observed on auto-refresh-top-n runs dated 09-10, 09-11, 09-14 and 09-15, so
it long predates the fan-out work. The leak itself is harmless — the process
is exiting and the socket is reclaimed — but it is logged at ERROR severity,
and a recurring ERROR that never means anything is how operators learn to
scroll past ERROR.
"""
from __future__ import annotations

import pytest

from gcp import database


class _FakeConnector:
    def __init__(self, raises: bool = False) -> None:
        self.closed = 0
        self._raises = raises

    def close(self) -> None:
        self.closed += 1
        if self._raises:
            raise RuntimeError("SQL Admin transport already torn down")


@pytest.fixture(autouse=True)
def _restore_connector():
    """Never leave a fake installed — the hook is module-global."""
    original = database._connector
    yield
    database._connector = original


def test_the_exit_hook_closes_the_connector():
    """Red before the fix: no hook existed to call."""
    fake = _FakeConnector()
    database._connector = fake

    database._close_cloud_sql_connector()

    assert fake.closed == 1, "the connector's aiohttp session was never closed"


def test_the_hook_clears_the_handle_so_it_cannot_double_close():
    """atexit plus an explicit call must not close twice."""
    fake = _FakeConnector()
    database._connector = fake

    database._close_cloud_sql_connector()
    database._close_cloud_sql_connector()

    assert fake.closed == 1, "connector closed more than once"
    assert database._connector is None


def test_no_connector_is_not_an_error():
    """A job that never touched Cloud SQL still exits cleanly."""
    database._connector = None
    database._close_cloud_sql_connector()  # must not raise


def test_a_failing_close_does_not_escape():
    """Cleanup must not change the exit code of a job that succeeded.

    This is the one place in this module where swallowing is correct
    (CLAUDE.md Rule 3.7's cleanup exemption): whatever the job was actually
    doing has already finished and reported, and a teardown error here would
    turn a green run red for nothing.
    """
    fake = _FakeConnector(raises=True)
    database._connector = fake

    database._close_cloud_sql_connector()  # must not raise

    assert fake.closed == 1
    assert database._connector is None, "handle must clear even when close fails"


def test_the_hook_is_registered_with_atexit():
    """The fix is worthless if nothing ever invokes it.

    Asserted against the source rather than the atexit registry: measured in
    this environment, `atexit.unregister(f)` does NOT decrement
    `atexit._ncallbacks()` (register -> 1, unregister -> still 1 with an
    isolated probe), so a registry-based assertion would pass whether or not
    the decorator were present. A static check on the decorator is weaker in
    principle but actually discriminates, which the runtime one did not.
    """
    import inspect

    from gcp import database as module

    source = inspect.getsource(module)
    assert "@atexit.register\ndef _close_cloud_sql_connector" in source, (
        "_close_cloud_sql_connector is no longer decorated with "
        "@atexit.register, so nothing closes the Cloud SQL Connector at exit "
        "and `ERROR asyncio - Unclosed client session` returns."
    )
