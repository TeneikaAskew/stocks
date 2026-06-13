import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  TrendingUp, Phone, Target, DollarSign, Scissors, Rocket,
  GitMerge, Shield, Star, Globe, Calendar, RefreshCw, Filter,
  Lock, ArrowUpRight, Users, Building, Presentation, Monitor,
  Video, Briefcase, Flame, ChevronRight,
} from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';
import { useTickerStore } from '@/stores/tickerStore';
import type { Ticker } from '@/types';

// ── Types ──────────────────────────────────────────────────────────────────

interface CatalystEvent {
  date: string;
  ticker: string;
  company_name?: string;
  catalyst_type: string;
  // Benzinga uses `event`; DB-sourced events use `title`. Renderer
  // prefers `title` then falls back to `event`.
  event?: string;
  title?: string;
  // Benzinga: `expected_impact` ('Very High'|'High'|'Medium'|'Low').
  // DB: `impact` (same vocabulary). Renderer accepts either.
  expected_impact?: string;
  impact?: string;
  confirmed?: boolean;
  source?: string;
  details?: Record<string, unknown>;
  // News-specific
  sentiment_score?: number;
  sentiment_label?: string;
  relevance_score?: number;
  url?: string;
  // SEC-specific
  items?: string[];
  primary_doc?: string;
  // Insider-specific
  insiders?: number;
  total_value?: number;
}

const IMPACT_RANK: Record<string, number> = {
  'Very High': 4,
  'High': 3,
  'Medium': 2,
  'Low': 1,
};

function impactKey(e: CatalystEvent): string {
  // Benzinga sends lowercase ('high'), DB sources send Title Case
  // ('High'); normalize so IMPACT_RANK lookups match either input.
  const raw = (e.impact || e.expected_impact || 'Medium').trim() || 'Medium';
  if (raw.toLowerCase() === 'very high') return 'Very High';
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}

function impactScore(e: CatalystEvent): number {
  return IMPACT_RANK[impactKey(e)] ?? 2;
}

function eventTitle(e: CatalystEvent): string {
  return e.title || e.event || `${e.ticker} ${e.catalyst_type}`;
}

interface CatalystsResponse {
  status: string;
  source: string;
  date_range: { from: string; to: string };
  total: number;
  events_by_date: Record<string, CatalystEvent[]>;
  message?: string;
}

interface CatalystTypesResponse {
  benzinga_types: Record<string, { label: string; color: string; icon: string }>;
  wsh_only_types: Record<string, { label: string; color: string; icon: string }>;
  upgrade_note: string;
}

// Tone palette: each tone has a (dark, light) hex pair tuned so the badge
// text reads at WCAG AA against both the dark and light surface-2 cards.
// Replaces the original flat-UI palette which was tuned for dark surfaces
// only — colors like #1abc9c → 2.3:1 and #f39c12 → 2.4:1 on light, and
// #34495e → 1.6:1 / #2c3e50 → 1.4:1 on dark.
type Tone = 'red' | 'orange' | 'amber' | 'green' | 'teal' | 'blue' | 'indigo' | 'purple' | 'neutral';

const TONE_PALETTE: Record<Tone, { dark: string; light: string }> = {
  red:     { dark: '#f87171', light: '#b91c1c' },
  orange:  { dark: '#fb923c', light: '#c2410c' },
  amber:   { dark: '#fbbf24', light: '#b45309' },
  green:   { dark: '#4ade80', light: '#15803d' },
  teal:    { dark: '#2dd4bf', light: '#0f766e' },
  blue:    { dark: '#60a5fa', light: '#1d4ed8' },
  indigo:  { dark: '#a5b4fc', light: '#4338ca' },
  purple:  { dark: '#c084fc', light: '#6d28d9' },
  neutral: { dark: '#94a3b8', light: '#475569' },
};

function toneColor(tone: Tone, theme: 'dark' | 'light'): string {
  return TONE_PALETTE[tone][theme];
}

const TYPE_CONFIG: Record<string, { label: string; tone: Tone; icon: typeof TrendingUp }> = {
  EARNINGS:           { label: 'Earnings',    tone: 'red',     icon: TrendingUp },
  CONFERENCE_CALL:    { label: 'Conf. Call',  tone: 'blue',    icon: Phone },
  GUIDANCE:           { label: 'Guidance',    tone: 'amber',   icon: Target },
  DIVIDEND:           { label: 'Dividend',    tone: 'green',   icon: DollarSign },
  SPLIT:              { label: 'Split',       tone: 'purple',  icon: Scissors },
  IPO:                { label: 'IPO',         tone: 'teal',    icon: Rocket },
  MERGER_ACQUISITION: { label: 'M&A',         tone: 'orange',  icon: GitMerge },
  FDA:                { label: 'FDA',         tone: 'red',     icon: Shield },
  ANALYST_RATING:     { label: 'Rating',      tone: 'blue',    icon: Star },
  ECONOMIC:           { label: 'Economic',    tone: 'neutral', icon: Globe },
  // Corporate Events API types
  CORPORATE_EVENT:    { label: 'Corp. Event', tone: 'neutral', icon: Calendar },
  INVESTOR_CONFERENCE:{ label: 'Conference',  tone: 'purple',  icon: Users },
  SUMMIT:             { label: 'Summit',      tone: 'teal',    icon: Globe },
  SHAREHOLDER_MEETING:{ label: 'Shareholder', tone: 'neutral', icon: Building },
  ANALYST_DAY:        { label: 'Analyst Day', tone: 'red',     icon: Presentation },
  INVESTOR_DAY:       { label: 'Investor Day',tone: 'orange',  icon: Users },
  PRESENTATION:       { label: 'Presentation',tone: 'indigo',  icon: Monitor },
  BUSINESS_UPDATE:    { label: 'Biz Update',  tone: 'amber',   icon: Briefcase },
  WEBCAST:            { label: 'Webcast',     tone: 'teal',    icon: Video },
  // DB-sourced events (news with catalyst topics + SEC 8-K filings)
  NEWS_CATALYST:      { label: 'News',        tone: 'blue',    icon: Globe },
  EARNINGS_NEWS:      { label: 'Earnings News',tone: 'red',    icon: TrendingUp },
  SEC_8K:             { label: '8-K',         tone: 'amber',   icon: Briefcase },
};

// Impact → bg-color class lookup (single source of truth for the impact dot
// + any future text-color usage via the matching `text-[var(--…)]` class).
const IMPACT_COLORS: Record<string, string> = {
  'Very High': 'var(--bear)',
  'High': 'var(--warn)',
  'Medium': 'var(--brand)',
  'Low': 'var(--on-surface-variant)',
  'Variable': 'var(--brand)',
};

// ── Hooks ──────────────────────────────────────────────────────────────────

function useCatalystEvents(dateFrom: string, dateTo: string, refresh: boolean) {
  return useQuery<CatalystsResponse>({
    queryKey: ['catalysts', dateFrom, dateTo, refresh],
    queryFn: async () => {
      const params = new URLSearchParams({
        date_from: dateFrom,
        date_to: dateTo,
      });
      if (refresh) params.set('refresh', 'true');
      const r = await fetch(`/api/catalysts/events?${params}`);
      if (!r.ok) throw new Error('Failed to fetch catalysts');
      return r.json();
    },
    staleTime: 5 * 60_000,
  });
}

function useCatalystTypes() {
  return useQuery<CatalystTypesResponse>({
    queryKey: ['catalyst-types'],
    queryFn: async () => {
      const r = await fetch('/api/catalysts/types');
      if (!r.ok) throw new Error('Failed to fetch types');
      return r.json();
    },
    staleTime: 60 * 60_000,
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

function getRelativeLabel(dateStr: string): string | null {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(dateStr + 'T00:00:00');
  const diff = Math.round((target.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return 'TODAY';
  if (diff === 1) return 'TOMORROW';
  if (diff === -1) return 'YESTERDAY';
  if (diff > 0) return `in ${diff} days`;
  return `${Math.abs(diff)} days ago`;
}

// ── Components ─────────────────────────────────────────────────────────────

function CatalystBadge({ type }: { type: string }) {
  const theme = useThemeStore((s) => s.theme);
  const config = TYPE_CONFIG[type] || { label: type, tone: 'neutral' as Tone, icon: Calendar };
  const color = toneColor(config.tone, theme);
  const Icon = config.icon;
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
      style={{ backgroundColor: color + '22', color, border: `1px solid ${color}44` }}
    >
      <Icon size={11} />
      {config.label}
    </span>
  );
}

function ImpactDot({ event }: { event: CatalystEvent }) {
  const k = impactKey(event);
  const color = IMPACT_COLORS[k] || IMPACT_COLORS.Low;
  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{ backgroundColor: color }}
      title={`${k} impact`}
      aria-label={`${k} impact`}
    />
  );
}

function SentimentIndicator({ event }: { event: CatalystEvent }) {
  if (typeof event.sentiment_score !== 'number') return null;
  const s = event.sentiment_score;
  if (Math.abs(s) < 0.1) return null;
  const cls = s > 0 ? 'text-[var(--bull)]' : 'text-[var(--bear)]';
  const symbol = s > 0 ? '▲' : '▼';
  return (
    <span
      className={`text-[10px] font-bold ${cls} tabular-nums`}
      title={`Sentiment ${s.toFixed(2)} (${event.sentiment_label || ''})`}
    >
      {symbol} {Math.abs(s).toFixed(2)}
    </span>
  );
}

function EventRow({ event, onOpenTicker }: {
  event: CatalystEvent;
  onOpenTicker: (ticker: string) => void;
}) {
  const macro = event.ticker === 'MACRO' || !event.ticker;
  return (
    <div className="group flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-[var(--surface-2)] transition-colors">
      <ImpactDot event={event} />
      {macro ? (
        <span className="w-16 shrink-0 text-xs font-bold text-[var(--on-surface-variant)]">
          MACRO
        </span>
      ) : (
        <button
          onClick={() => onOpenTicker(event.ticker)}
          className="w-16 shrink-0 text-left text-xs font-bold text-[var(--brand)] hover:underline"
          title={`Open ${event.ticker} insight report`}
        >
          {event.ticker || '---'}
        </button>
      )}
      <CatalystBadge type={event.catalyst_type} />
      <span className="flex-1 truncate text-sm text-[var(--on-surface)]">
        {eventTitle(event)}
      </span>
      <SentimentIndicator event={event} />
      {event.source && (
        <span className="hidden md:inline text-[10px] text-[var(--on-surface-variant)] truncate max-w-[110px]">
          {event.source}
        </span>
      )}
      {!macro && (
        <button
          onClick={() => onOpenTicker(event.ticker)}
          className="opacity-0 group-hover:opacity-100 inline-flex items-center gap-0.5 text-[11px] text-[var(--brand)] transition-opacity"
          title="Open insight report"
        >
          View
          <ChevronRight size={12} />
        </button>
      )}
    </div>
  );
}

function DateGroup({ date, events, onOpenTicker }: {
  date: string;
  events: CatalystEvent[];
  onOpenTicker: (ticker: string) => void;
}) {
  const relative = getRelativeLabel(date);
  const isToday = relative === 'TODAY';
  // Sort within group: impact desc, then ticker
  const sorted = [...events].sort((a, b) => {
    const di = impactScore(b) - impactScore(a);
    if (di) return di;
    return (a.ticker || '').localeCompare(b.ticker || '');
  });
  return (
    <div className={`rounded-xl p-6 ${isToday ? 'bg-[var(--surface-2)] ring-1 ring-[var(--brand)]' : 'bg-[var(--surface-1)]'}`}>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--on-surface)]">{formatDate(date)}</span>
          {isToday && (
            <span className="rounded-lg bg-[var(--brand)] px-2 py-0.5 text-[10px] font-bold text-[var(--on-brand)]">
              TODAY
            </span>
          )}
        </div>
        <span className="text-xs text-[var(--on-surface-variant)]">
          {relative} &middot; {events.length} events
        </span>
      </div>
      <div className="space-y-1">
        {sorted.map((e, i) => (
          <EventRow
            key={`${e.date}-${e.ticker}-${e.catalyst_type}-${i}`}
            event={e}
            onOpenTicker={onOpenTicker}
          />
        ))}
      </div>
    </div>
  );
}

function WSHUpgradeBanner({ types }: { types: CatalystTypesResponse | undefined }) {
  if (!types) return null;
  const wshTypes = Object.values(types.wsh_only_types);
  return (
    <div className="rounded-xl bg-[var(--surface-1)] p-6 border border-dashed border-[var(--brand)]">
      <div className="mb-3 flex items-center gap-2">
        <Lock size={14} className="text-[var(--brand)]" />
        <span className="text-sm font-semibold text-[var(--brand)]">Wall Street Horizon Upgrade</span>
      </div>
      <p className="mb-4 text-xs text-[var(--on-surface-variant)]">
        These event types require WSH via IBKR TWS API ($49-149/mo):
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        {/* Server-supplied hex colors are dark-tuned and would fail WCAG on
            the light surface; render as theme-neutral "locked" chips so the
            upsell preview is readable in both modes. */}
        {wshTypes.map(t => (
          <span
            key={t.label}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide bg-[var(--surface-2)] text-[var(--on-surface-muted)] border border-[var(--outline-variant)]"
          >
            <Lock size={9} />
            {t.label}
          </span>
        ))}
      </div>
      <a
        href="https://www.wallstreethorizon.com/ibkr-wsh"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-xs text-[var(--brand)] hover:underline"
      >
        Learn more about WSH <ArrowUpRight size={12} />
      </a>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function CatalystsPage() {
  const theme = useThemeStore((s) => s.theme);
  const today = new Date();
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date(today);
    d.setDate(d.getDate() - 3);
    return d.toISOString().slice(0, 10);
  });
  const [dateTo, setDateTo] = useState(() => {
    const d = new Date(today);
    d.setDate(d.getDate() + 14);
    return d.toISOString().slice(0, 10);
  });
  const resetDates = () => {
    const t = new Date();
    const from = new Date(t); from.setDate(from.getDate() - 3);
    const to   = new Date(t); to.setDate(to.getDate() + 14);
    setDateFrom(from.toISOString().slice(0, 10));
    setDateTo(to.toISOString().slice(0, 10));
  };
  const [refreshing, setRefreshing] = useState(false);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [minImpact, setMinImpact] = useState<'All' | 'Medium' | 'High'>('All');

  const { data, isLoading, error, refetch } = useCatalystEvents(dateFrom, dateTo, false);
  const { data: typesData } = useCatalystTypes();
  const navigate = useNavigate();
  const setTicker = useTickerStore(s => s.setTicker);
  const handleOpenTicker = (ticker: string) => {
    if (!ticker || ticker === 'MACRO') return;
    setTicker(ticker.toUpperCase() as Ticker);
    navigate('/insights');
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  };

  // Pull events into a single list so we can compute summary stats
  // before grouping back by date (drives the filter chips, the "hot
  // now" panel, and the impact-tier counters).
  const eventsByDate = data?.events_by_date || {};
  const allEvents: CatalystEvent[] = useMemo(
    () => Object.values(eventsByDate).flat(),
    [eventsByDate],
  );

  const passes = (e: CatalystEvent): boolean => {
    if (activeFilter && e.catalyst_type !== activeFilter) return false;
    if (minImpact === 'High' && impactScore(e) < 3) return false;
    if (minImpact === 'Medium' && impactScore(e) < 2) return false;
    return true;
  };

  const filteredDates = Object.entries(eventsByDate)
    .map(([date, events]) => [date, events.filter(passes)] as const)
    .filter(([, events]) => events.length > 0)
    .sort(([a], [b]) => a.localeCompare(b));

  // Today's hot catalysts: high-impact items in today + tomorrow.
  // This is the "actionable" panel — the user lands here, sees what
  // could move price in the next 24-48h, clicks straight to /insights.
  const isoToday = today.toISOString().slice(0, 10);
  const isoTomorrow = (() => {
    const t = new Date(today); t.setDate(t.getDate() + 1);
    return t.toISOString().slice(0, 10);
  })();
  const hotEvents: CatalystEvent[] = useMemo(() => {
    return allEvents
      .filter(e => (e.date === isoToday || e.date === isoTomorrow))
      .filter(e => impactScore(e) >= 3)
      .sort((a, b) => {
        const di = impactScore(b) - impactScore(a);
        if (di) return di;
        return (a.date || '').localeCompare(b.date || '');
      })
      .slice(0, 10);
  }, [allEvents, isoToday, isoTomorrow]);

  // Counts for the impact + type chip badges
  const impactCounts = useMemo(() => {
    const c = { Total: 0, High: 0, Medium: 0, Low: 0 };
    for (const e of allEvents) {
      c.Total += 1;
      const k = impactKey(e);
      if (k === 'High' || k === 'Very High') c.High += 1;
      else if (k === 'Medium') c.Medium += 1;
      else c.Low += 1;
    }
    return c;
  }, [allEvents]);

  // Unique types in data for filter chips
  const allTypes = new Set<string>();
  allEvents.forEach(e => allTypes.add(e.catalyst_type));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-[22px] font-bold tracking-[-0.02em] text-[var(--on-surface)]">Catalysts</h1>
          <p className="label-micro mt-2">
            {impactCounts.Total} events
            {' '}<span className="text-[var(--bear)] font-semibold">{impactCounts.High}H</span>{' / '}
            <span className="text-[var(--brand)] font-semibold">{impactCounts.Medium}M</span>{' / '}
            <span className="text-[var(--on-surface-variant)]">{impactCounts.Low}L</span>
            {' · '}{data?.source ?? 'Benzinga'}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="flex items-center gap-1.5 text-[11px] text-[var(--on-surface-variant)]">
            From
            <input
              type="date"
              value={dateFrom}
              max={dateTo}
              onChange={e => setDateFrom(e.target.value)}
              className="rounded-md bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--on-surface)] outline-none ring-1 ring-transparent focus:ring-[var(--brand)]"
            />
          </label>
          <label className="flex items-center gap-1.5 text-[11px] text-[var(--on-surface-variant)]">
            To
            <input
              type="date"
              value={dateTo}
              min={dateFrom}
              onChange={e => setDateTo(e.target.value)}
              className="rounded-md bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--on-surface)] outline-none ring-1 ring-transparent focus:ring-[var(--brand)]"
            />
          </label>
          <button
            onClick={resetDates}
            className="rounded-md bg-[var(--surface-2)] px-2 py-1 text-[11px] font-medium text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)] hover:text-[var(--on-surface)] transition-colors"
            title="Reset to default range (today-3 → today+14)"
          >
            Today
          </button>
          <button
            onClick={handleRefresh}
            disabled={refreshing || isLoading}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)] hover:text-[var(--on-surface)] transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Hot Now — high-impact catalysts in today/tomorrow window */}
      {hotEvents.length > 0 && (
        <div className="rounded-xl bg-[var(--surface-1)] p-3 ring-1 ring-[var(--warn)]/30">
          <div className="flex items-center gap-2 mb-2">
            <Flame size={14} className="text-[var(--warn)]" />
            <span className="text-xs font-bold uppercase tracking-wide text-[var(--warn)]">
              Hot now
            </span>
            <span className="text-[10px] text-[var(--on-surface-variant)]">
              high-impact, today + tomorrow
            </span>
          </div>
          <div className="space-y-0.5">
            {hotEvents.map((e, i) => (
              <EventRow
                key={`hot-${e.date}-${e.ticker}-${e.catalyst_type}-${i}`}
                event={e}
                onOpenTicker={handleOpenTicker}
              />
            ))}
          </div>
        </div>
      )}

      {/* Impact tier filter */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-wide text-[var(--on-surface-variant)] mr-1">
          Min impact:
        </span>
        {(['All', 'Medium', 'High'] as const).map(t => (
          <button
            key={t}
            onClick={() => setMinImpact(t)}
            className={`rounded-full px-3 py-1 text-[10px] font-semibold transition-colors ${
              minImpact === t
                ? 'bg-[var(--brand)] text-[var(--on-brand)]'
                : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)]'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Type filter chips */}
      {allTypes.size > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setActiveFilter(null)}
            className={`rounded-full px-3 py-1 text-[10px] font-semibold transition-colors ${
              !activeFilter
                ? 'bg-[var(--brand)] text-[var(--on-brand)]'
                : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)]'
            }`}
          >
            All Types
          </button>
          {Array.from(allTypes).sort().map(type => {
            const config = TYPE_CONFIG[type];
            // Active background uses the deeper "light"-variant hex so white
            // text reads at WCAG AA in both themes; the theme-aware
            // `chipColor` is layered on top as the border accent so the chip
            // still tracks the user's active theme.
            const activeBg = config ? TONE_PALETTE[config.tone].light : undefined;
            const chipColor = config ? toneColor(config.tone, theme) : null;
            return (
              <button
                key={type}
                onClick={() => setActiveFilter(activeFilter === type ? null : type)}
                className={`rounded-full px-3 py-1 text-[10px] font-semibold transition-colors ${
                  activeFilter === type
                    ? 'text-white'
                    : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)]'
                }`}
                style={
                  activeFilter === type && activeBg
                    ? { backgroundColor: activeBg, border: chipColor ? `1px solid ${chipColor}` : undefined }
                    : undefined
                }
              >
                {config?.label || type}
              </button>
            );
          })}
        </div>
      )}

      {/* Loading / Error states */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <RefreshCw size={20} className="animate-spin text-[var(--brand)]" />
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-[var(--bear)]/40 bg-[var(--bear)]/10 px-4 py-2.5 text-sm text-[var(--bear)]">
          Failed to load catalysts: {(error as Error).message}
        </div>
      )}
      {data?.status === 'no_data' && (
        <div className="rounded-lg border border-[var(--warn)]/40 bg-[var(--warn)]/10 px-4 py-2.5 text-sm text-[var(--warn)]">
          <Filter size={14} className="mr-1 inline" />
          {data.message}
        </div>
      )}

      {/* Event timeline */}
      <div className="space-y-4">
        {filteredDates.map(([date, events]) => (
          <DateGroup
            key={date}
            date={date}
            events={events as CatalystEvent[]}
            onOpenTicker={handleOpenTicker}
          />
        ))}
      </div>

      {/* WSH upgrade banner */}
      <WSHUpgradeBanner types={typesData} />
    </div>
  );
}
