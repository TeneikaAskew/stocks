"""News is inherently backward-looking; the catalyst window is forward.
DB-verified 2026-07-08 (exec db-query-vjfwb): the old shared-window filter
returned 0 rows while 1,681 articles existed in the trailing 48h; topics
carry mixed casing across sources, so matching must be case-insensitive."""
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

_original_cwd = os.getcwd()
os.chdir(str(PLATFORM_DIR))
try:
    from api.routers import catalysts
finally:
    os.chdir(_original_cwd)


def test_news_sql_is_backward_looking_and_case_insensitive():
    sql = catalysts._news_sql()
    assert "NEWS_LOOKBACK_HOURS" not in sql          # interpolated, not literal
    assert ":lookback_hours" in sql or "INTERVAL" in sql
    assert "published_ts >=" in sql                   # backward window
    assert ":d_from" not in sql                       # decoupled from event window
    assert "lower(" in sql.lower()                    # case-insensitive topic match


def test_news_topics_constant_covers_fetcher_topics():
    assert {"technology", "financial_markets", "life_sciences"} <= set(catalysts.NEWS_TOPICS)
