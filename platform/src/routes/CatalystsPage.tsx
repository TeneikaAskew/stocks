import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  TrendingUp, Phone, Target, DollarSign, Scissors, Rocket,
  GitMerge, Shield, Star, Globe, Calendar, RefreshCw, Filter,
  Lock, ArrowUpRight, Users, Building, Presentation, Monitor,
  Video, Briefcase,
} from 'lucide-react';
import { useThemeStore } from '@/stores/themeStore';

// ── Types ──────────────────────────────────────────────────────────────────

interface CatalystEvent {
  date: string;
  ticker: string;
  company_name: string;
  catalyst_type: string;
  event: string;
  expected_impact: string;
  confirmed: boolean;
  source: string;
  details?: Record<string, unknown>;
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
};

const IMPACT_COLORS: Record<string, string> = {
  'Very High': 'text-[var(--bear)]',
  'High': 'text-[var(--warn)]',
  'Medium': 'text-[var(--warn)]',
  'Low': 'text-[var(--on-surface-variant)]',
  'Variable': 'text-[var(--brand)]',
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

function EventRow({ event }: { event: CatalystEvent }) {
  const impactClass = IMPACT_COLORS[event.expected_impact] || 'text-[var(--on-surface-variant)]';
  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-[var(--surface-2)] transition-colors">
      <span className="w-14 shrink-0 text-xs font-bold text-[var(--brand)]">
        {event.ticker || '---'}
      </span>
      <CatalystBadge type={event.catalyst_type} />
      <span className="flex-1 truncate text-sm text-[var(--on-surface)]">
        {event.event}
      </span>
      <span className={`text-[10px] font-semibold ${impactClass}`}>
        {event.confirmed ? '' : '?'}
      </span>
    </div>
  );
}

function DateGroup({ date, events }: { date: string; events: CatalystEvent[] }) {
  const relative = getRelativeLabel(date);
  const isToday = relative === 'TODAY';
  return (
    <div className={`rounded-xl p-4 ${isToday ? 'bg-[var(--surface-2)] ring-1 ring-[var(--brand)]' : 'bg-[var(--surface-1)]'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--on-surface)]">{formatDate(date)}</span>
          {isToday && (
            <span className="rounded bg-[var(--brand)] px-2 py-0.5 text-[10px] font-bold text-[var(--on-brand)]">
              TODAY
            </span>
          )}
        </div>
        <span className="text-xs text-[var(--on-surface-variant)]">{relative}</span>
      </div>
      <div className="space-y-1">
        {events.map((e, i) => (
          <EventRow key={`${e.date}-${e.ticker}-${e.catalyst_type}-${i}`} event={e} />
        ))}
      </div>
    </div>
  );
}

function WSHUpgradeBanner({ types }: { types: CatalystTypesResponse | undefined }) {
  if (!types) return null;
  const wshTypes = Object.values(types.wsh_only_types);
  return (
    <div className="rounded-xl bg-[var(--surface-1)] p-4 border border-dashed border-[var(--brand)]">
      <div className="flex items-center gap-2 mb-2">
        <Lock size={14} className="text-[var(--brand)]" />
        <span className="text-sm font-semibold text-[var(--brand)]">Wall Street Horizon Upgrade</span>
      </div>
      <p className="text-xs text-[var(--on-surface-variant)] mb-3">
        These event types require WSH via IBKR TWS API ($49-149/mo):
      </p>
      <div className="flex flex-wrap gap-2 mb-3">
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
  const today = new Date();
  const [dateFrom] = useState(() => {
    const d = new Date(today);
    d.setDate(d.getDate() - 3);
    return d.toISOString().slice(0, 10);
  });
  const [dateTo] = useState(() => {
    const d = new Date(today);
    d.setDate(d.getDate() + 14);
    return d.toISOString().slice(0, 10);
  });
  const [refreshing, setRefreshing] = useState(false);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useCatalystEvents(dateFrom, dateTo, false);
  const { data: typesData } = useCatalystTypes();

  const handleRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  };

  // Filter events
  const eventsByDate = data?.events_by_date || {};
  const filteredDates = Object.entries(eventsByDate)
    .map(([date, events]) => {
      const filtered = activeFilter
        ? events.filter(e => e.catalyst_type === activeFilter)
        : events;
      return [date, filtered] as const;
    })
    .filter(([, events]) => events.length > 0)
    .sort(([a], [b]) => a.localeCompare(b));

  // Unique types in data for filter chips
  const allTypes = new Set<string>();
  Object.values(eventsByDate).flat().forEach(e => allTypes.add(e.catalyst_type));

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-[var(--on-surface)]">Catalysts</h1>
          <p className="text-xs text-[var(--on-surface-variant)]">
            {data?.total ?? 0} events &middot; {data?.source ?? 'Benzinga'}
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing || isLoading}
          className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-2)] px-3 py-1.5 text-xs font-medium text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)] hover:text-[var(--on-surface)] transition-colors disabled:opacity-50"
        >
          <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filter chips */}
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
            // Use the deeper "light"-variant hex as the active background so
            // white text reads at WCAG AA in both themes (the dark-variant
            // pastels would only get ~3:1 against white).
            const activeBg = config ? TONE_PALETTE[config.tone].light : undefined;
            return (
              <button
                key={type}
                onClick={() => setActiveFilter(activeFilter === type ? null : type)}
                className={`rounded-full px-3 py-1 text-[10px] font-semibold transition-colors ${
                  activeFilter === type
                    ? 'text-white'
                    : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)]'
                }`}
                style={activeFilter === type && activeBg ? { backgroundColor: activeBg } : undefined}
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
        <div className="rounded-lg bg-red-500/10 p-4 text-sm text-[var(--bear)]">
          Failed to load catalysts: {(error as Error).message}
        </div>
      )}
      {data?.status === 'no_data' && (
        <div className="rounded-lg bg-amber-500/10 p-4 text-sm text-[var(--warn)]">
          <Filter size={14} className="inline mr-1" />
          {data.message}
        </div>
      )}

      {/* Event timeline */}
      <div className="space-y-3">
        {filteredDates.map(([date, events]) => (
          <DateGroup key={date} date={date} events={events as CatalystEvent[]} />
        ))}
      </div>

      {/* WSH upgrade banner */}
      <WSHUpgradeBanner types={typesData} />
    </div>
  );
}
