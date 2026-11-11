# Report-day calendar: sources (fetched 2026-11-11)

| Event | Time ET | Source page | Notes |
|---|---|---|---|
| CPI, jobs report (Employment Situation), PPI | 08:30 | BLS yearly schedules: https://www.bls.gov/schedule/2025/home.htm and https://www.bls.gov/schedule/2026/home.htm | 2025 page reflects the shutdown changes: no jobs report in Oct or Nov 2025 (Sep jobs came Nov 20, Oct and Nov jobs came Dec 16), Sep CPI came Oct 24, no Oct CPI, Nov CPI came Dec 18. |
| PCE (Personal Income and Outlays), GDP | 08:30, three PCE releases at 10:00 | BEA: https://www.bea.gov/news/schedule/full-2025 and https://www.bea.gov/news/schedule/full | 10:00 PCE: 2025-04-30, 2025-12-05, 2026-01-22. No Oct/Nov 2025 PCE dates (shutdown). |
| FOMC decision day | 14:00 statement, 14:30 press conference | Second day of each meeting as listed at https://fedratecalc.com/fomc-meeting-schedule/ (mirrors federalreserve.gov/monetarypolicy/fomccalendars.htm) | Not an 08:30 event; treated as its own group. |
| Retail sales (advance) | 08:30 | 2026: https://www.census.gov/economic-indicators/calendar-listview-2026.html | 2025 dates could not be fetched from Census (the page only served 2026/2027); they are typed from general knowledge and flagged in the note column. Tier 2 only. |

Tier 1 = CPI, jobs, PCE, FOMC. Tier 2 = PPI, GDP, retail sales. Weekly jobless claims (every Thursday 08:30) are
not in the calendar; they would mark one day in five and are not what the owner means by "report days".

Pages were read through a page-to-text fetch tool, so a typo is possible. Check: code/check_calendar.py compares
each 08:30 date with the size of the 08:30 minute in SPY premarket volume (a real release shows a spike).
Dates after 2026-06 are "as scheduled" by the agency; the same volume check covers them.
