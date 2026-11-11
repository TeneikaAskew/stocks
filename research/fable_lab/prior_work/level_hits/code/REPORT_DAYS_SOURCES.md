# report_days.csv sources (fetched 2026-11-11)
- CPI and jobs report (Employment Situation) dates: BLS annual schedule pages https://www.bls.gov/schedule/2025 and
  https://www.bls.gov/schedule/2026/home.htm, plus the shutdown revisions page
  https://www.bls.gov/bls/2025-lapse-revised-release-dates.htm (October 2025 CPI and jobs report were cancelled).
- PCE (Personal Income and Outlays): BEA schedule https://www.bea.gov/news/schedule/full-2025 and
  https://www.bea.gov/index.php/news/schedule/full (2026).
- FOMC decision days: the table in the repo, gcp/research/direction_program/phase2_features.py (_FOMC_WEEKS).
- 2026 dates after the fetch date are the published schedule as of Nov 11 2026; BLS/BEA 2026 pages list the
  scheduled date, so a release that slipped by a day in 2026 would not show here. Not cross checked against prices.
- time_et: release time. FOMC (14:00) and the three 10:00 PCE releases come out after the 08:30 brief AND after the open.
