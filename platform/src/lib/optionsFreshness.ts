// Pure freshness-badge logic for the OptionsFlowPage.
//
// AUDIT-2026-05-22: added with Track 4 of the realtime-options multi-track plan.
// See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md.
//
// The badge tone tells users at a glance whether the gamma data they're
// viewing is live (REALTIME — auto-refreshing), end-of-day (EOD — last
// nightly fetch), or stale (>2 trading days old). The three tones map
// 1:1 to a single source of truth in this module so the page, hook,
// and tests all agree on the rules.

export type MarketSession = 'REALTIME' | 'EOD' | string | null | undefined;
export type FreshnessTone = 'live' | 'eod' | 'stale';

export interface FreshnessBadge {
  tone: FreshnessTone;
  label: string;
  title: string;
}

const TRADING_DAYS_STALE_THRESHOLD = 2;

const ET_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/New_York',
});

const ET_DOW_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/New_York',
});

const ET_FULL_FORMATTER = new Intl.DateTimeFormat('en-US', {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/New_York',
});

function parseSnapshot(ts: string | null | undefined): Date | null {
  if (!ts) return null;
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? null : d;
}

const ET_DATE_PARTS = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

// Extract YYYY-MM-DD in America/New_York, then materialize as a UTC-midnight
// Date so arithmetic is timezone-free. A 21:00 ET timestamp is on the ET
// trading day, even though it crosses midnight UTC.
function toEtMidnightUtc(d: Date): Date {
  const parts = ET_DATE_PARTS.formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '0';
  const y = Number(get('year'));
  const m = Number(get('month'));
  const day = Number(get('day'));
  return new Date(Date.UTC(y, m - 1, day));
}

// Count weekdays (Mon-Fri) strictly between the ET calendar dates of `from`
// and `to`. Inclusive of neither endpoint. Approximation: ignores US market
// holidays, which means the badge can be off by up to one trading day around
// holidays — acceptable for a UX hint that just decides green/amber/red.
export function tradingDaysBetween(from: Date, to: Date): number {
  if (from.getTime() >= to.getTime()) return 0;
  const cursor = toEtMidnightUtc(from);
  const end = toEtMidnightUtc(to);
  if (cursor.getTime() >= end.getTime()) return 0;
  let count = 0;
  while (cursor.getTime() < end.getTime()) {
    cursor.setUTCDate(cursor.getUTCDate() + 1);
    const dow = cursor.getUTCDay();
    if (dow !== 0 && dow !== 6) count += 1;
  }
  return count;
}

export function freshnessFromSnapshot(
  market_session: MarketSession,
  snapshot_ts: string | null | undefined,
  now: Date = new Date(),
): FreshnessBadge {
  const snap = parseSnapshot(snapshot_ts);

  if (market_session === 'REALTIME') {
    if (!snap) {
      return {
        tone: 'live',
        label: 'Live',
        title: 'Realtime options snapshot — refreshes every 60s',
      };
    }
    const time = ET_TIME_FORMATTER.format(snap);
    return {
      tone: 'live',
      label: `Live · ${time} ET`,
      title: `Realtime snapshot as of ${ET_FULL_FORMATTER.format(snap)} ET — refreshes every 60s`,
    };
  }

  if (!snap) {
    return {
      tone: 'stale',
      label: 'Stale · unknown',
      title: 'Snapshot timestamp unavailable — data may be stale',
    };
  }

  const elapsed = tradingDaysBetween(snap, now);

  if (market_session === 'EOD' && elapsed <= TRADING_DAYS_STALE_THRESHOLD) {
    const dowTime = ET_DOW_TIME_FORMATTER.format(snap).replace(',', '');
    return {
      tone: 'eod',
      label: `EOD · ${dowTime} ET`,
      title: `End-of-day snapshot from ${ET_FULL_FORMATTER.format(snap)} ET`,
    };
  }

  // Either market_session is unknown/legacy or the snapshot is too old.
  const dayWord = elapsed === 1 ? 'day' : 'days';
  return {
    tone: 'stale',
    label: `Stale · ${elapsed}d old`,
    title: `Snapshot is ${elapsed} trading ${dayWord} old (${ET_FULL_FORMATTER.format(snap)} ET) — may not reflect current dealer positioning`,
  };
}

// Tailwind class bundles for each tone. Centralized so the badge styling
// can't drift between the page and any future surface that needs it.
export function freshnessBadgeClasses(tone: FreshnessTone): string {
  switch (tone) {
    case 'live':
      return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400';
    case 'eod':
      return 'border-amber-500/40 bg-amber-500/10 text-amber-400';
    case 'stale':
      return 'border-rose-500/40 bg-rose-500/10 text-rose-400';
  }
}
