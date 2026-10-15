from datetime import datetime, timezone

import pandas as pd
import pytest

from lib import earnings_history as reader


def test_asof_excludes_future_revisions_and_reports_legacy_gap(monkeypatch):
    calls = []
    def query(sql, params, **kw):
        calls.append((sql, params))
        assert "known_at <= :as_of" in sql
        assert "earnings_history_revisions" in sql
        assert "FROM earnings_history " not in sql
        return pd.DataFrame()
    monkeypatch.setattr(reader, "query_to_dataframe_strict", query)
    result = reader.read_earnings_asof("AAPL", datetime(2026, 10, 8, tzinfo=timezone.utc))
    assert result["status"] == "unavailable"
    assert result["reason"] == "pre_observation_coverage_gap"
    assert len(calls) == 1
    with pytest.raises(ValueError, match="aware"):
        reader.read_earnings_asof("AAPL", datetime(2026, 10, 8))


def test_cutoff_uses_eastern_exchange_date_end():
    assert reader.exchange_date_cutoff("2026-10-09").isoformat() == "2026-10-10T03:59:59.999999+00:00"
    assert reader.exchange_date_cutoff("2026-12-09").isoformat() == "2026-12-10T04:59:59.999999+00:00"
