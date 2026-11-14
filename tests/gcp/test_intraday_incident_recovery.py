"""Incident1560: coverage refusals are review items, never blanket retries."""
import json
import logging
import os
from types import SimpleNamespace
import pytest
from gcp.fetchers import fetch_alphavantage_intraday as f

@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    def deny(*a,**k):raise AssertionError("external boundary")
    monkeypatch.setattr(f.requests,"get",deny)
    monkeypatch.setattr(f.requests,"post",deny)
    for name in ["query_to_dataframe_strict","replace_rows_in_window","upsert_dataframe","bulk_insert_dataframe","execute_sql"]:monkeypatch.setattr(f,name,deny)
    monkeypatch.setattr(f,"get_api_keys",lambda:["fake-only"])
    monkeypatch.setattr(f,"_av_cfg",SimpleNamespace(delay_between_calls=0))
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX","0");monkeypatch.setenv("CLOUD_RUN_TASK_COUNT","1")
    monkeypatch.setenv("CLOUD_RUN_EXECUTION","intraday-bulk-backfill-fixture")

def run(tmp_path,monkeypatch,outcomes,commit):
    path=tmp_path/"items.csv";path.write_text("".join(f"T{i},2026-04\n" for i in range(len(outcomes))))
    it=iter(outcomes)
    def replace(sym,y,m,key,apply):
        value=next(it)
        if isinstance(value,Exception):raise value
        return dict(symbol=sym,month="2026-04",status=value,held_sessions=21,missing_sessions=1 if value==f.REPLACE_INCOMPLETE else 0,deleted=0,inserted=842)
    monkeypatch.setattr(f,"replace_month",replace)
    return f.run_replace_months(str(path),commit,None)

def events(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.getMessage().startswith('{"event":"intraday_replace_result"')]

@pytest.mark.parametrize("status",[f.REPLACE_INCOMPLETE,f.FETCH_INVALID_API,f.FETCH_NO_TIMESERIES,f.FETCH_INFO_MSG,f.REPLACE_NOTHING_HELD])
def test_nontransient_failures_require_review_without_retry(tmp_path,monkeypatch,caplog,status):
    caplog.set_level(logging.INFO)
    assert run(tmp_path,monkeypatch,[status,f.REPLACE_DRY],False)==1
    assert "REVIEW T0,2026-04" in caplog.text
    assert "RETRY T0" not in caplog.text
    assert len(events(caplog))==2
    assert events(caplog)[0]["recovery"]=="review_required"

@pytest.mark.parametrize("status",[f.FETCH_RATE_LIMIT,f.FETCH_REQUEST_ERROR,f.REPLACE_CHANGED])
def test_only_known_transient_or_concurrency_results_are_retry_candidates(tmp_path,monkeypatch,caplog,status):
    caplog.set_level(logging.INFO)
    assert run(tmp_path,monkeypatch,[status],False)==1
    assert "RETRY T0,2026-04" in caplog.text
    assert events(caplog)[0]["recovery"]=="targeted_retry_candidate"

@pytest.mark.parametrize("commit,status,written,planned",[(False,f.REPLACE_DRY,0,842),(True,f.REPLACE_OK,842,0)])
def test_dry_run_planned_rows_are_never_logged_as_written(tmp_path,monkeypatch,caplog,commit,status,written,planned):
    caplog.set_level(logging.INFO)
    assert run(tmp_path,monkeypatch,[status],commit)==0
    e=events(caplog)[0]
    assert e["written_rows"]==written and e["planned_rows"]==planned
    assert e["write_outcome"]==("acknowledged" if commit else "not_applied")
    assert e["execution"]=="intraday-bulk-backfill-fixture"
    assert e["task_index"]==0
    assert len(json.dumps(e).encode())<=2048

@pytest.mark.parametrize("commit",[False,True])
def test_unclassified_exception_is_isolated_uncertain_and_never_blanket_retried(tmp_path,monkeypatch,caplog,commit):
    caplog.set_level(logging.INFO)
    marker="fake-secret-value https://evil.invalid/?apikey=fake-secret-value"
    assert run(tmp_path,monkeypatch,[RuntimeError(marker),f.REPLACE_OK if commit else f.REPLACE_DRY],commit)==1
    assert marker not in caplog.text and "fake-secret-value" not in caplog.text
    assert "RETRY T0" not in caplog.text and "REVIEW T0,2026-04" in caplog.text
    e=events(caplog)
    assert len(e)==2 and e[0]["status"]=="systemic"
    assert e[0]["write_outcome"]==("uncertain" if commit else "not_applied")
    assert e[1]["written_rows"]==(842 if commit else 0)


def test_safe_result_projection_has_a_whole_event_bound(monkeypatch,caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("CLOUD_RUN_EXECUTION","fake-secret-"*1000)
    f._log_replace_result("fake-secret-value",10**100,99,{'status':'unknown-secret','inserted':10**100},commit=False,task_index=10**3000,recovery='review_required')
    e=events(caplog)[0]
    assert len(json.dumps(e).encode())<=2048
    assert e['ticker'] is None and e['execution'] is None
    assert e['month'] is None and e['task_index'] is None
    assert 'fake-secret' not in caplog.text and 'unknown-secret' not in caplog.text
