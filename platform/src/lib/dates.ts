/** Market-calendar date helpers. The market lives in America/New_York;
 * `new Date().toISOString().slice(0,10)` is UTC and is WRONG for 4 hours
 * every evening (5 in winter). Always derive "today" through these. */
const ET_FMT = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/New_York',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** YYYY-MM-DD for an arbitrary instant, in Eastern Time. */
export function toETDateString(d: Date): string {
  return ET_FMT.format(d); // en-CA locale yields YYYY-MM-DD
}

/** Today's date (YYYY-MM-DD) on the US market calendar. */
export function todayET(): string {
  return toETDateString(new Date());
}

/** Add days to a YYYY-MM-DD string with UTC-anchored arithmetic — immune to
 * the browser's timezone (local-midnight round-trips shift a day east of UTC). */
export function addDaysToISO(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
