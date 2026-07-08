import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Clock, Search } from 'lucide-react';
import { useTickerStore } from '@/stores/tickerStore';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useTickerSearch, useTickerCoverage, type SearchMatch, type TickerCoverage } from '@/hooks/useTickerSearch';

export type CoverageBadge = 'full' | 'daily' | 'new';
export type Coverage = TickerCoverage;
export type Suggestion = SearchMatch;

/**
 * Maps coverage state to the badge shown next to a search result.
 * `undefined` coverage (still loading / lookup missed) renders as "new" —
 * the honest default per CLAUDE.md Rule 3.7: never claim data we haven't
 * confirmed exists.
 */
export function coverageBadge(c: Coverage | undefined): CoverageBadge {
  if (c?.intraday && c.daily) return 'full';
  if (c?.daily) return 'daily';
  return 'new';
}

/** Attaches a coverage badge to each search result by symbol (case-insensitive). */
export function mergeSuggestions(
  results: Suggestion[],
  coverage: Record<string, Coverage>,
): (Suggestion & { badge: CoverageBadge })[] {
  return results.map((r) => ({ ...r, badge: coverageBadge(coverage[r.symbol.toUpperCase()]) }));
}

/**
 * Drops any search result whose symbol duplicates a quick-pick or recent
 * that's already rendered above it in the popover (case-insensitive).
 *
 * Why: the popover renders three sections (quick picks, recents, search)
 * from what used to be three independent `.map()` calls, each computing its
 * row's keyboard-highlight via `flat.indexOf(symbol)` against a combined
 * list. If a search result duplicated an existing quick-pick/recent (e.g.
 * typing "IWM" while IWM is already a quick pick), `indexOf` always
 * resolved to the FIRST occurrence — the later row's highlight silently
 * never lit up, and two DOM nodes ended up sharing
 * `data-testid="ticker-option-IWM"`. Rather than giving every row a
 * section-qualified testid (`ticker-option-quick-IWM` vs
 * `ticker-option-search-IWM`), we drop the redundant search row: the symbol
 * is already reachable via its quick-pick/recent chip, so showing it twice
 * added nothing. This keeps `flat` (the combined, keyboard-navigable list)
 * free of duplicate symbols, so `indexOf`-based highlighting and testids
 * are unambiguous again.
 */
export function dedupeSearchResults<T extends { symbol: string }>(
  searchResults: T[],
  quickPicks: string[],
  recents: string[],
): T[] {
  const alreadyShown = new Set([...quickPicks, ...recents].map((t) => t.toUpperCase()));
  return searchResults.filter((r) => !alreadyShown.has(r.symbol.toUpperCase()));
}

const BADGE_LABEL: Record<CoverageBadge, string> = {
  full: 'full',
  daily: 'daily',
  new: 'new',
};

const BADGE_STYLE: Record<CoverageBadge, string> = {
  full: 'border-[var(--bull)]/40 bg-[var(--bull)]/15 text-[var(--bull)]',
  daily: 'border-[var(--brand)]/40 bg-[var(--brand)]/15 text-[var(--brand)]',
  new: 'border-[var(--warn)]/40 bg-[var(--warn)]/15 text-[var(--warn)]',
};

function BadgeChip({ badge }: { badge: CoverageBadge }) {
  return (
    <span
      className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${BADGE_STYLE[badge]}`}
    >
      {BADGE_LABEL[badge]}
    </span>
  );
}

interface TickerComboboxProps {
  className?: string;
  /** Called whenever a symbol is picked — Task 3 hooks this to auto-ingest never-before-seen tickers. */
  onPickNew?: (symbol: string) => void;
}

/**
 * Ticker type-ahead combobox (`TickerCombobox`) — replaces the old fixed
 * IWM/SPY/QQQ dropdown selector. Trigger shows `activeTicker`; the popover
 * offers quick-picks, recents, and (once ≥1 char is typed) live symbol
 * search with a per-row data-coverage badge (full/daily/new) so a user
 * can tell, before picking, whether a symbol already has history.
 *
 * Follows ReplayControl.tsx's popover idiom (trigger button + outside-click
 * / Escape close) and CommandPalette.tsx's clamped keyboard-nav pattern.
 */
export function TickerCombobox({ className, onPickNew }: TickerComboboxProps) {
  const { activeTicker, quickPicks, recentTickers, setTicker, pushRecent } = useTickerStore();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [sel, setSel] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const debounced = useDebouncedValue(query.trim(), 300);
  const searchEnabled = debounced.length >= 1;
  const search = useTickerSearch(debounced, searchEnabled);

  const results = useMemo(() => search.data?.results ?? [], [search.data]);
  const symbolsCsv = useMemo(
    () => Array.from(new Set(results.map((r) => r.symbol.toUpperCase()))).join(','),
    [results],
  );
  const coverage = useTickerCoverage(symbolsCsv, symbolsCsv.length > 0);
  const merged = useMemo(
    () => mergeSuggestions(results, coverage.data?.coverage ?? {}),
    [results, coverage.data],
  );

  const recents = recentTickers.filter((t) => !quickPicks.includes(t));

  // Search rows drop anything that duplicates a quick-pick/recent symbol —
  // see dedupeSearchResults' doc comment for why (indexOf-highlight + testid
  // collision otherwise).
  const searchRows = useMemo(
    () => (searchEnabled ? dedupeSearchResults(merged, quickPicks, recents) : []),
    [searchEnabled, merged, quickPicks, recents],
  );

  // Flatten selectable rows for keyboard nav: quick-picks, then recents, then
  // (once search is active) suggestions — mirrors CommandPalette's clamp
  // pattern. Every symbol appears at most once (searchRows is pre-deduped),
  // so `flat.indexOf(symbol)` below is unambiguous.
  const flat = useMemo(
    () => [...quickPicks, ...recents, ...searchRows.map((m) => m.symbol)],
    [quickPicks, recents, searchRows],
  );
  const safeSel = Math.min(sel, Math.max(0, flat.length - 1));

  // Closes the popover AND resets its draft state. Routed through a single
  // helper (rather than a setState-on-close effect keyed on `open`) so
  // closing never triggers a cascading render — see React docs on avoiding
  // setState-in-effect.
  const close = () => {
    setOpen(false);
    setQuery('');
    setSel(0);
  };

  // Outside click / Escape closes the popover — same idiom as ReplayControl.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const choose = (symbol: string) => {
    const upper = symbol.toUpperCase();
    setTicker(upper);
    pushRecent(upper);
    onPickNew?.(upper);
    close();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      close();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSel((s) => Math.min(s + 1, flat.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSel((s) => Math.max(s - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (flat[safeSel]) choose(flat[safeSel]);
    }
  };

  return (
    <div ref={ref} className={`relative shrink-0 ${className ?? ''}`}>
      <button
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="Active ticker"
        data-testid="ticker-combobox"
        className="flex min-w-24 items-center justify-between gap-1.5 rounded-lg border border-[var(--outline-variant)] bg-[var(--surface-1)] px-2.5 py-1.5 font-display text-sm font-semibold tracking-wide text-[var(--on-surface)] hover:bg-[var(--surface-2)]"
      >
        <span>{activeTicker}</span>
        <ChevronDown size={12} className={`transition-transform${open ? ' rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-xl border border-[var(--surface-3)] bg-[var(--surface-1)] shadow-2xl">
          <div className="border-b border-[var(--outline-variant)] p-2">
            <div className="flex items-center gap-2 rounded-lg border border-[var(--outline-variant)] bg-[var(--surface-lowest)] px-2.5 py-1.5">
              <Search size={13} className="shrink-0 text-[var(--on-surface-muted)]" />
              <input
                ref={inputRef}
                data-testid="ticker-combobox-input"
                placeholder="Search ticker or company…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setSel(0);
                }}
                onKeyDown={onKeyDown}
                className="w-full bg-transparent text-sm text-[var(--on-surface)] placeholder:text-[var(--on-surface-muted)] focus:outline-none"
              />
            </div>
          </div>

          <div className="max-h-80 overflow-y-auto p-2" data-testid="ticker-combobox-panel">
            {/* Quick picks */}
            <div className="mb-2">
              <div className="px-1 pb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--on-surface-label)]">
                Quick picks
              </div>
              <div className="flex flex-wrap gap-1.5 px-1">
                {quickPicks.map((t) => {
                  const idx = flat.indexOf(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      data-testid={`ticker-option-${t}`}
                      onClick={() => choose(t)}
                      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                        idx === safeSel
                          ? 'border-[var(--brand)] bg-[var(--brand)]/15 text-[var(--brand)]'
                          : 'border-[var(--outline-variant)] text-[var(--on-surface)] hover:bg-[var(--surface-2)]'
                      }`}
                    >
                      {t}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Recents */}
            {recents.length > 0 && (
              <div className="mb-2">
                <div className="flex items-center gap-1 px-1 pb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--on-surface-label)]">
                  <Clock size={10} /> Recent
                </div>
                <div className="flex flex-wrap gap-1.5 px-1">
                  {recents.map((t) => {
                    const idx = flat.indexOf(t);
                    return (
                      <button
                        key={t}
                        type="button"
                        data-testid={`ticker-option-${t}`}
                        onClick={() => choose(t)}
                        className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                          idx === safeSel
                            ? 'border-[var(--brand)] bg-[var(--brand)]/15 text-[var(--brand)]'
                            : 'border-[var(--outline-variant)] text-[var(--on-surface)] hover:bg-[var(--surface-2)]'
                        }`}
                      >
                        {t}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Search results */}
            {searchEnabled && (
              <div>
                <div className="px-1 pb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--on-surface-label)]">
                  Results
                </div>
                {search.isError && (
                  <div className="px-1.5 py-2 text-xs text-[var(--bear)]" data-testid="ticker-search-error">
                    search unavailable
                    {search.error instanceof Error ? ` (${search.error.message})` : ''}
                  </div>
                )}
                {!search.isError && search.isLoading && (
                  <div className="px-1.5 py-2 text-xs text-[var(--on-surface-muted)]">Searching…</div>
                )}
                {!search.isError && !search.isLoading && searchRows.length === 0 && (
                  <div className="px-1.5 py-2 text-xs text-[var(--on-surface-muted)]">
                    No matches for &ldquo;{debounced}&rdquo;
                  </div>
                )}
                {/* Coverage lookup failed but search itself succeeded — still
                    render suggestions (badges honestly default to "new" per
                    coverageBadge's contract) plus a subtle hint that the
                    badges may not reflect real coverage. */}
                {!search.isError && coverage.isError && (
                  <div
                    className="px-1.5 pb-1.5 text-[10px] text-[var(--on-surface-muted)]"
                    data-testid="ticker-coverage-error"
                  >
                    coverage lookup unavailable — badges may be inaccurate
                  </div>
                )}
                {!search.isError &&
                  searchRows.map((m) => {
                    const idx = flat.indexOf(m.symbol);
                    return (
                      <button
                        key={m.symbol}
                        type="button"
                        data-testid={`ticker-option-${m.symbol}`}
                        onClick={() => choose(m.symbol)}
                        className={`flex w-full items-center justify-between gap-2 rounded-lg px-1.5 py-1.5 text-left ${
                          idx === safeSel ? 'bg-[var(--surface-2)]' : 'hover:bg-[var(--surface-2)]'
                        }`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-semibold text-[var(--on-surface)]">
                            {m.symbol}
                          </span>
                          <span className="block truncate text-xs text-[var(--on-surface-variant)]">
                            {m.name}
                          </span>
                        </span>
                        <BadgeChip badge={m.badge} />
                      </button>
                    );
                  })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
