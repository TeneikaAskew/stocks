"""Provenance stamping on the canonical rows the live-only readers serve.

Both writers resolve an as-of override from an env var, and both stamp
`run_kind` on the row `/api/dashboard` and `/api/insights` filter to
`run_kind = 'live'`. Two ways that goes wrong, both found by Codex on
#1098 round 4:

  * A blank or whitespace-only override is NOT an override — the parser
    already treats it that way and the run is genuinely live — but a
    truthiness test on the raw env var says it is, and stamps the live
    row `replay`. Every live-only reader then hides the day's real work.

  * A `/replay ... today refresh:true` writes a `replay` row for today.
    If the existence check the scheduled brief uses ignores `run_kind`,
    that row blocks the live write and the ticker ends the day with no
    row any live-only reader will serve.
"""

from __future__ import annotations

from datetime import date

import pytest

from gcp import insight_pipeline_job, premarket_brief


class TestAsOfOverrideNormalisation:
    """A blank override resolves to today; provenance must agree."""

    @pytest.mark.parametrize("raw", ["", "   ", "\t", "\n "])
    def test_blank_brief_as_of_is_not_an_override(self, monkeypatch, raw):
        monkeypatch.setenv("BRIEF_AS_OF", raw)
        assert premarket_brief._as_of_override() is None
        # The date resolver already agreed; the point is that everything
        # else now asks the same question.
        assert premarket_brief._resolve_analysis_date() == date.today()

    def test_real_brief_as_of_is_returned_stripped(self, monkeypatch):
        monkeypatch.setenv("BRIEF_AS_OF", "  2026-05-08 ")
        assert premarket_brief._as_of_override() == "2026-05-08"
        assert premarket_brief._resolve_analysis_date() == date(2026, 5, 8)

    def test_unset_brief_as_of_is_not_an_override(self, monkeypatch):
        monkeypatch.delenv("BRIEF_AS_OF", raising=False)
        assert premarket_brief._as_of_override() is None

    def test_blank_brief_as_of_does_not_force_replay_refresh(self, monkeypatch):
        monkeypatch.setenv("BRIEF_AS_OF", "   ")
        monkeypatch.delenv("BRIEF_UPDATE", raising=False)
        monkeypatch.setenv("BRIEF_TRIGGERED_BY", "cloud-scheduler-premarket")
        allow_update, run_kind = premarket_brief._resolve_run_kind_and_update(False)
        assert (allow_update, run_kind) == (False, "scheduled")

    def test_real_brief_as_of_still_forces_replay_refresh(self, monkeypatch):
        monkeypatch.setenv("BRIEF_AS_OF", "2026-05-08")
        monkeypatch.delenv("BRIEF_UPDATE", raising=False)
        allow_update, run_kind = premarket_brief._resolve_run_kind_and_update(False)
        assert (allow_update, run_kind) == (True, "replay_refresh")

    @pytest.mark.parametrize("raw", ["", "   ", "\t"])
    def test_blank_insight_as_of_stamps_live(self, monkeypatch, raw):
        monkeypatch.setenv("INSIGHT_AS_OF", raw)
        # parse_as_of already returns None, so the pipeline runs live.
        assert insight_pipeline_job.parse_as_of(raw) is None
        assert insight_pipeline_job._canonical_run_kind() == "live"

    def test_real_insight_as_of_stamps_replay(self, monkeypatch):
        monkeypatch.setenv("INSIGHT_AS_OF", "2026-05-08")
        assert insight_pipeline_job._canonical_run_kind() == "replay"

    def test_unset_insight_as_of_stamps_live(self, monkeypatch):
        monkeypatch.delenv("INSIGHT_AS_OF", raising=False)
        assert insight_pipeline_job._canonical_run_kind() == "live"


def _brief(tickers=("SPY",)):
    return {
        "analysis_date": date(2026, 9, 14),
        "tickers": {t: {"price": 1.0, "status": "OK"} for t in tickers},
    }


class _Recorder:
    """Stands in for gcp.database for the canonical-write path."""

    def __init__(self, exists: bool):
        self._exists = exists
        self.exists_calls: list[dict] = []
        self.upserted: list[dict] = []

    def is_cloud_sql_configured(self):
        return True

    def bulk_insert_dataframe(self, df, table):
        return len(df)

    def row_exists(self, table, where):
        self.exists_calls.append(dict(where))
        return self._exists

    def upsert_dataframe(self, df, table, keys):
        self.upserted.extend(df.to_dict("records"))
        return len(df)


@pytest.fixture
def _db(monkeypatch):
    def _install(exists: bool) -> _Recorder:
        rec = _Recorder(exists)
        import gcp.database as db
        for name in ("is_cloud_sql_configured", "bulk_insert_dataframe",
                     "row_exists", "upsert_dataframe"):
            monkeypatch.setattr(db, name, getattr(rec, name))
        return rec
    return _install


class TestLiveWriteIsNotBlockedByAReplayRow:
    def test_live_run_only_treats_a_live_row_as_existing(self, monkeypatch, _db):
        monkeypatch.delenv("BRIEF_AS_OF", raising=False)
        rec = _db(exists=False)
        premarket_brief.persist_to_cloud_sql(_brief(), allow_update=False)
        assert rec.exists_calls, "the INSERT-only path must consult row_exists"
        for where in rec.exists_calls:
            assert where.get("run_kind") == "live", (
                "a live scheduled run must not be blocked by a replay row "
                "for the same key: every live-only reader filters it out"
            )

    def test_live_run_writes_when_only_a_non_live_row_exists(self, monkeypatch, _db):
        """row_exists is filtered to live, so it reports False and the
        upsert then replaces the replay row."""
        monkeypatch.delenv("BRIEF_AS_OF", raising=False)
        rec = _db(exists=False)
        n = premarket_brief.persist_to_cloud_sql(_brief(), allow_update=False)
        assert n == 1
        assert [r["run_kind"] for r in rec.upserted] == ["live"]

    def test_live_run_still_skips_when_a_live_row_exists(self, monkeypatch, _db):
        monkeypatch.delenv("BRIEF_AS_OF", raising=False)
        rec = _db(exists=True)
        n = premarket_brief.persist_to_cloud_sql(_brief(), allow_update=False)
        assert n == 0
        assert rec.upserted == []

    def test_replay_run_stamps_replay_on_the_canonical_row(self, monkeypatch, _db):
        monkeypatch.setenv("BRIEF_AS_OF", "2026-09-14")
        rec = _db(exists=False)
        premarket_brief.persist_to_cloud_sql(_brief(), allow_update=True)
        assert [r["run_kind"] for r in rec.upserted] == ["replay"]

    def test_blank_as_of_stamps_live_on_the_canonical_row(self, monkeypatch, _db):
        monkeypatch.setenv("BRIEF_AS_OF", "   ")
        rec = _db(exists=False)
        premarket_brief.persist_to_cloud_sql(_brief(), allow_update=False)
        assert [r["run_kind"] for r in rec.upserted] == ["live"]
