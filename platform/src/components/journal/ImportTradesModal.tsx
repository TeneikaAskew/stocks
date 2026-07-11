import { useState, type ChangeEvent } from 'react';
import { AlertCircle, Upload } from 'lucide-react';
import { Modal } from '@/components/shared/Modal';
import {
  useImportPreview,
  useImportCommit,
  type ImportPreviewTrade,
} from '@/hooks/useJournalChartTrades';
import { fmtPct, NA } from '@/lib/format';

// ── Broker chips + generic column-mapper (design spec "Trade import") ──────
// Robinhood/Webull are native, header-detected parsers (lib/broker_import.py
// detect_broker) — no mapping UI. Every other platform routes through the
// SAME "generic" server-side parser (`_ALLOWED_BROKERS = {robinhood, webull,
// generic}` in journal.py) with a caller-supplied column mapping; the four
// non-native chips below are just different UI entry points (different
// presets, different localStorage keys) into that one generic path.

type BrokerId = 'robinhood' | 'webull' | 'schwab' | 'fidelity' | 'ibkr' | 'other';
type MappingKey = 'ticker' | 'direction' | 'action' | 'ts' | 'price' | 'quantity';

const NATIVE_BROKERS = new Set<BrokerId>(['robinhood', 'webull']);

// Matches lib.broker_import._GENERIC_REQUIRED_KEYS exactly.
const MAPPING_KEYS: MappingKey[] = ['ticker', 'direction', 'action', 'ts', 'price', 'quantity'];
const MAPPING_LABELS: Record<MappingKey, string> = {
  ticker: 'Ticker',
  direction: 'Direction (CALL/PUT)',
  action: 'Action (open/close)',
  ts: 'Timestamp',
  price: 'Price',
  quantity: 'Quantity',
};

const BROKER_CHIPS: { id: BrokerId; label: string }[] = [
  { id: 'robinhood', label: 'Robinhood' },
  { id: 'webull', label: 'Webull' },
  { id: 'schwab', label: 'Schwab' },
  { id: 'fidelity', label: 'Fidelity' },
  { id: 'ibkr', label: 'IBKR' },
  { id: 'other', label: 'Other' },
];

// Best-effort starting guesses for the generic column-mapper — the user
// confirms/adjusts against their own CSV's actual headers (design spec:
// "user confirms the mapping once; preset saved"). These are NOT verified
// against real Schwab/Fidelity/IBKR exports (out of this task's scope —
// `lib/broker_import.py`'s generic parser is a caller-supplied mapping by
// design, see its module docstring pt. 3); they exist only to save the
// common case a few clicks, never to silently commit an unconfirmed mapping
// (the user still must hit "Preview" and review real parsed rows).
const DEFAULT_PRESETS: Partial<Record<BrokerId, Partial<Record<MappingKey, string>>>> = {
  schwab: { ticker: 'Symbol', action: 'Action', ts: 'Date', price: 'Price', quantity: 'Quantity' },
  fidelity: { ticker: 'Symbol', action: 'Action', ts: 'Run Date', price: 'Price', quantity: 'Quantity' },
  ibkr: { ticker: 'Symbol', action: 'Code', ts: 'Date/Time', price: 'Price', quantity: 'Quantity' },
};

const emptyMapping = (): Record<MappingKey, string> => ({
  ticker: '',
  direction: '',
  action: '',
  ts: '',
  price: '',
  quantity: '',
});

const presetStorageKey = (id: BrokerId) => `journal-import-mapping-preset:${id}`;

export interface ImportTradesModalProps {
  open: boolean;
  onClose: () => void;
  /** Called once a commit succeeds — JournalPage flips the view to "My
   *  journal" (import always writes there, same rule as chart marking:
   *  "Import always writes to MY journal... flip to My journal after a
   *  successful commit"). Query invalidation itself happens inside
   *  `useImportCommit`, not here. */
  onImported?: () => void;
}

/**
 * 3-step broker CSV import modal (Task 7, journal one-stop-shop):
 *   1. broker chip + file — native (Robinhood/Webull) skip the mapper;
 *      Schwab/Fidelity/IBKR/Other show the six-field generic column-mapper
 *      once a file is chosen (options come from the CSV's own header row).
 *   2. preview table from POST /api/journal/import/preview — checkbox per
 *      row (duplicates pre-unchecked + labeled, active-import rows
 *      amber-labeled) + the honest skipped-row list (Rule 3.7 — every
 *      dropped input row surfaces a reason, never a silent drop).
 *   3. commit result ("Imported N · M duplicates skipped").
 *
 * Errors (413 file/row cap, 422 bad broker/mapping, network) surface via an
 * inline banner reading the mutation's `error.message` verbatim — no
 * fabricated/silent fallback on failure (Rule 3.7).
 */
export function ImportTradesModal({ open, onClose, onImported }: ImportTradesModalProps) {
  const [step, setStep] = useState<'select' | 'preview' | 'result'>('select');
  const [broker, setBroker] = useState<BrokerId | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<MappingKey, string>>(emptyMapping());
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const previewMutation = useImportPreview();
  const commitMutation = useImportCommit();

  const isNativeBroker = broker != null && NATIVE_BROKERS.has(broker);
  const mappingComplete = MAPPING_KEYS.every((k) => mapping[k]);
  const canPreview = !!file && !!broker && (isNativeBroker || mappingComplete);

  const resetState = () => {
    setStep('select');
    setBroker(null);
    setFile(null);
    setHeaders([]);
    setMapping(emptyMapping());
    setSelected(new Set());
    previewMutation.reset();
    commitMutation.reset();
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const selectBroker = (id: BrokerId) => {
    setBroker(id);
    previewMutation.reset();
    if (NATIVE_BROKERS.has(id)) {
      setMapping(emptyMapping());
      return;
    }
    let preset: Partial<Record<MappingKey, string>> = {};
    const stored = localStorage.getItem(presetStorageKey(id));
    if (stored) {
      try {
        preset = JSON.parse(stored);
      } catch {
        // Corrupt/foreign localStorage value under our own key — fall back
        // to the hardcoded default preset below rather than crashing the
        // modal on a bad JSON.parse (structural fallback, not a fabricated
        // financial value — Rule 3.7 doesn't apply to a UI text preset).
        preset = {};
      }
    }
    setMapping({ ...emptyMapping(), ...(DEFAULT_PRESETS[id] ?? {}), ...preset });
  };

  const onFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    previewMutation.reset();
    if (f && broker && !NATIVE_BROKERS.has(broker)) {
      const text = await f.text();
      const headerLine = text.split(/\r?\n/)[0] ?? '';
      setHeaders(headerLine.split(',').map((h) => h.trim().replace(/^"|"$/g, '')));
    }
  };

  const setMappingField = (key: MappingKey, value: string) => {
    setMapping((m) => {
      const next = { ...m, [key]: value };
      if (broker && !NATIVE_BROKERS.has(broker)) {
        localStorage.setItem(presetStorageKey(broker), JSON.stringify(next));
      }
      return next;
    });
  };

  const runPreview = () => {
    if (!file || !broker) return;
    previewMutation.mutate(
      {
        file,
        broker: isNativeBroker ? (broker as 'robinhood' | 'webull') : 'generic',
        mapping: isNativeBroker ? undefined : mapping,
      },
      {
        onSuccess: (data) => {
          // Duplicates start UNCHECKED (design spec) — everything else
          // (including active-import rows, which have no exit yet but are
          // still real, non-duplicate trades) starts checked.
          setSelected(new Set(data.trades.map((_, i) => i).filter((i) => !data.trades[i].duplicate)));
          setStep('preview');
        },
      }
    );
  };

  const toggleRow = (i: number) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const runCommit = () => {
    const data = previewMutation.data;
    if (!data) return;
    const trades = data.trades.filter((_, i) => selected.has(i));
    commitMutation.mutate(
      { broker: data.broker, trades },
      {
        onSuccess: () => {
          setStep('result');
          onImported?.();
        },
      }
    );
  };

  const previewTrades: ImportPreviewTrade[] = previewMutation.data?.trades ?? [];
  const skipped = previewMutation.data?.skipped ?? [];

  return (
    <Modal open={open} onClose={handleClose} title="Import trades from broker">
      <div className="w-[min(90vw,720px)] space-y-4">
        {step === 'select' && (
          <>
            <div>
              <div className="mb-1.5 text-xs font-medium text-[var(--color-text-secondary)]">Broker</div>
              <div className="flex flex-wrap gap-1.5">
                {BROKER_CHIPS.map((chip) => (
                  <button
                    key={chip.id}
                    onClick={() => selectBroker(chip.id)}
                    className={`rounded border px-3 py-1.5 text-xs font-medium transition-colors ${
                      broker === chip.id
                        ? 'border-[var(--color-accent-blue)] bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                        : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)]'
                    }`}
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-1.5 text-xs font-medium text-[var(--color-text-secondary)]">Statement CSV</div>
              <label
                data-testid="import-dropzone"
                className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-[var(--color-border)] p-6 text-center text-xs text-[var(--color-text-muted)] hover:border-[var(--color-accent-blue)]/50"
              >
                <Upload size={20} className="opacity-60" />
                {file ? file.name : 'Click to choose or drop a CSV export from your broker'}
                <input
                  type="file"
                  accept=".csv,text/csv"
                  data-testid="import-file-input"
                  onChange={onFileChange}
                  className="hidden"
                />
              </label>
            </div>

            {broker && !isNativeBroker && (
              <div>
                <div className="mb-1.5 text-xs font-medium text-[var(--color-text-secondary)]">
                  Column mapping —{' '}
                  {file ? "match each field to your CSV's header" : 'upload a CSV to populate header options'}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {MAPPING_KEYS.map((key) => (
                    <div key={key}>
                      <label className="mb-0.5 block text-[10px] text-[var(--color-text-muted)]">
                        {MAPPING_LABELS[key]}
                      </label>
                      <select
                        data-testid={`import-mapping-${key}`}
                        value={headers.includes(mapping[key]) ? mapping[key] : ''}
                        onChange={(e) => setMappingField(key, e.target.value)}
                        disabled={headers.length === 0}
                        className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-2 py-1 text-xs text-[var(--color-text-primary)] disabled:opacity-50"
                      >
                        <option value="">— select column —</option>
                        {headers.map((h) => (
                          <option key={h} value={h}>
                            {h}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {previewMutation.isError && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-[var(--bear)]"
              >
                <AlertCircle size={14} /> {previewMutation.error.message}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={handleClose}
                className="rounded px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-bg-tertiary)]"
              >
                Cancel
              </button>
              <button
                onClick={runPreview}
                disabled={!canPreview || previewMutation.isPending}
                className="rounded bg-[var(--color-accent-blue)] px-4 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:opacity-90 disabled:opacity-40"
              >
                {previewMutation.isPending ? 'Parsing…' : 'Preview'}
              </button>
            </div>
          </>
        )}

        {step === 'preview' && (
          <>
            <div className="max-h-[360px] overflow-auto rounded border border-[var(--color-border)]">
              <table data-testid="import-preview-table" className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-[var(--color-bg-tertiary)]">
                  <tr>
                    {['', 'Ticker', 'Dir', 'Entry', 'Entry $', 'Exit', 'Exit $', 'Return', 'Qty', ''].map((h, i) => (
                      <th key={`${h}-${i}`} className="px-2 py-1.5 font-medium text-[var(--color-text-muted)]">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {previewTrades.map((t, i) => (
                    <tr key={i} className={t.duplicate ? 'opacity-70' : ''}>
                      <td className="px-2 py-1.5">
                        <input
                          type="checkbox"
                          aria-label={`select ${t.ticker} ${t.direction} row`}
                          checked={selected.has(i)}
                          onChange={() => toggleRow(i)}
                          className="h-3.5 w-3.5"
                        />
                      </td>
                      <td className="px-2 py-1.5 font-mono">{t.ticker}</td>
                      <td
                        className={`px-2 py-1.5 font-bold ${
                          t.direction === 'CALL' ? 'text-[var(--bull)]' : 'text-[var(--bear)]'
                        }`}
                      >
                        {t.direction}
                      </td>
                      <td className="px-2 py-1.5 font-mono text-[10px]">{t.entry_ts}</td>
                      <td className="px-2 py-1.5 font-mono">${t.entry_price.toFixed(2)}</td>
                      <td className="px-2 py-1.5 font-mono text-[10px]">{t.exit_ts ?? NA}</td>
                      <td className="px-2 py-1.5 font-mono">
                        {t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : NA}
                      </td>
                      <td className="px-2 py-1.5 font-mono">{fmtPct(t.return_pct)}</td>
                      <td className="px-2 py-1.5 font-mono">{t.quantity}</td>
                      <td className="px-2 py-1.5">
                        {t.duplicate ? (
                          <span className="rounded bg-[var(--color-bg-hover)] px-1.5 py-0.5 text-[9px] font-medium text-[var(--color-text-muted)]">
                            duplicate — already in journal
                          </span>
                        ) : t.status === 'active' ? (
                          <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-medium text-amber-500/70">
                            imports as active
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {skipped.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-[var(--color-text-secondary)]">
                  Skipped rows ({skipped.length})
                </div>
                <ul
                  data-testid="import-skipped-list"
                  className="max-h-[120px] space-y-0.5 overflow-auto text-[10px] text-[var(--color-text-muted)]"
                >
                  {skipped.map((s) => (
                    <li key={s.raw_index}>
                      Row {s.raw_index + 1}: {s.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {commitMutation.isError && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-[var(--bear)]"
              >
                <AlertCircle size={14} /> {commitMutation.error.message}
              </div>
            )}

            <div className="flex justify-between gap-2">
              <button
                onClick={() => setStep('select')}
                className="rounded px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-bg-tertiary)]"
              >
                Back
              </button>
              <button
                onClick={runCommit}
                disabled={selected.size === 0 || commitMutation.isPending}
                className="rounded bg-[var(--color-accent-blue)] px-4 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:opacity-90 disabled:opacity-40"
              >
                {commitMutation.isPending
                  ? 'Importing…'
                  : `Import ${selected.size} trade${selected.size === 1 ? '' : 's'}`}
              </button>
            </div>
          </>
        )}

        {step === 'result' && commitMutation.data && (
          <div className="space-y-3 py-2 text-center">
            <p className="text-sm font-medium text-[var(--color-text-primary)]">
              Imported {commitMutation.data.imported} · {commitMutation.data.skipped_duplicates} duplicates skipped
            </p>
            <button
              onClick={handleClose}
              className="rounded bg-[var(--color-accent-blue)] px-4 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:opacity-90"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
