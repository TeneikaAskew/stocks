import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  TrendingUp, Phone, Target, DollarSign, Scissors, Rocket,
  GitMerge, Shield, Star, Globe, Calendar, RefreshCw, Filter,
  Lock, ArrowUpRight, Users, Building, Presentation, Monitor,
  Video, Briefcase,
} from 'lucide-react';

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

// ── Icon mapping ───────────────────────────────────────────────────────────

const ICON_MAP: Record<string, typeof TrendingUp> = {
  TrendingUp, Phone, Target, DollarSign, Scissors, Rocket,
  GitMerge, Shield, Star, Globe,
};

const TYPE_CONFIG: Record<string, { label: string; color: string; icon: typeof TrendingUp }> = {
  EARNINGS:           { label: 'Earnings',    color: '#e74c3c', icon: TrendingUp },
  CONFERENCE_CALL:    { label: 'Conf. Call',  color: '#3498db', icon: Phone },
  GUIDANCE:           { label: 'Guidance',    color: '#f39c12', icon: Target },
  DIVIDEND:           { label: 'Dividend',    color: '#27ae60', icon: DollarSign },
  SPLIT:              { label: 'Split',       color: '#9b59b6', icon: Scissors },
  IPO:                { label: 'IPO',         color: '#1abc9c', icon: Rocket },
  MERGER_ACQUISITION: { label: 'M&A',         color: '#e67e22', icon: GitMerge },
  FDA:                { label: 'FDA',         color: '#c0392b', icon: Shield },
  ANALYST_RATING:     { label: 'Rating',      color: '#2980b9', icon: Star },
  ECONOMIC:           { label: 'Economic',    color: '#7f8c8d', icon: Globe },
  // Corporate Events API types
  CORPORATE_EVENT:    { label: 'Corp. Event', color: '#34495e', icon: Calendar },
  INVESTOR_CONFERENCE:{ label: 'Conference',  color: '#8e44ad', icon: Users },
  SUMMIT:             { label: 'Summit',      color: '#16a085', icon: Globe },
  SHAREHOLDER_MEETING:{ label: 'Shareholder', color: '#2c3e50', icon: Building },
  ANALYST_DAY:        { label: 'Analyst Day', color: '#e74c3c', icon: Presentation },
  INVESTOR_DAY:       { label: 'Investor Day',color: '#d35400', icon: Users },
  PRESENTATION:       { label: 'Presentation',color: '#2980b9', icon: Monitor },
  BUSINESS_UPDATE:    { label: 'Biz Update',  color: '#f39c12', icon: Briefcase },
  WEBCAST:            { label: 'Webcast',     color: '#1abc9c', icon: Video },
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
  const config = TYPE_CONFIG[type] || { label: type, color: '#95a5a6', icon: Calendar };
  const Icon = config.icon;
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
      style={{ backgroundColor: config.color + '22', color: config.color, border: `1px solid ${config.color}44` }}
    >
      <Icon size={11} />
      {config.label}
    </span>
  );
}

function EventRow({ event, isToday }: { event: CatalystEvent; isToday: boolean }) {
  const impactClass = IMPACT_COLORS[event.expected_impact] || 'text-[var(--on-surface-variant)]';
  // Inside today's surface-2 DateGroup, rows need surface-3 to stand out.
  // Inside normal surface-1 DateGroup, rows use surface-2.
  const bgClass = isToday
    ? 'bg-[var(--surface-3)] hover:brightness-110'
    : 'bg-[var(--surface-2)] hover:bg-[var(--surface-3)]';
  return (
    <div className={`flex items-center gap-4 rounded-lg px-4 py-2.5 transition-colors ${bgClass}`}>
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
        <span className="label-micro">{relative}</span>
      </div>
      <div className="space-y-2">
        {events.map((e, i) => (
          <EventRow key={`${e.date}-${e.ticker}-${e.catalyst_type}-${i}`} event={e} isToday={isToday} />
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
        {wshTypes.map(t => (
          <span
            key={t.label}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide opacity-50"
            style={{ backgroundColor: t.color + '22', color: t.color, border: `1px solid ${t.color}44` }}
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-[var(--color-brand)]">Catalysts</h1>
          <p className="label-micro mt-2">
            {data?.total ?? 0} events · {data?.source ?? 'Benzinga'}
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
            return (
              <button
                key={type}
                onClick={() => setActiveFilter(activeFilter === type ? null : type)}
                className={`rounded-full px-3 py-1 text-[10px] font-semibold transition-colors ${
                  activeFilter === type
                    ? ''
                    : 'bg-[var(--surface-2)] text-[var(--on-surface-variant)] hover:bg-[var(--surface-3)]'
                }`}
                style={
                  activeFilter === type && config
                    ? {
                        backgroundColor: config.color + '33',
                        color: config.color,
                        border: `1px solid ${config.color}55`,
                      }
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
          <DateGroup key={date} date={date} events={events as CatalystEvent[]} />
        ))}
      </div>

      {/* WSH upgrade banner */}
      <WSHUpgradeBanner types={typesData} />
    </div>
  );
}
