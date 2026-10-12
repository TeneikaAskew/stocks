"""Run the producer's exact scoped SQL cases in the CI PostgreSQL job."""
from tests.gcp.test_av_catalyst_ingestion import (
    test_failed_weekly_head_does_not_starve_universe,
    test_saturated_news_subdivisions_eventually_advance_watermark,
)
