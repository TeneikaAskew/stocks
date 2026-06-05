// ─────────────────────────────────────────────────────────────────────────
// MOCK PLACEHOLDER DATA — NOT LIVE. Real source TBD.
//
// Heatseeker "Swing Mode" needs a 2D dealer-exposure surface: strikes (rows)
// × expiration dates (columns) of GEX/VEX dollar exposure. There is NO
// per-expiration backend endpoint today — `/levels` and `/greeks` only return
// a single-date chain collapsed to a per-strike profile — so this typed mock
// drives the Swing heatmap until a per-expiration dealer-exposure endpoint
// exists. The SwingMode view renders a persistent "Demo data" pill so this is
// never mistaken for live market data. Replace with a real
// `/api/options/exposure-surface/...` hook once it exists, and delete this file.
// ─────────────────────────────────────────────────────────────────────────

export type SwingMetric = 'gex' | 'vex';

export interface SwingSurface {
  /** Focus symbol this surface represents. */
  symbol: string;
  /** Estimated spot — used to highlight the spot row. */
  spot: number;
  /** King strike (largest |exposure|) — highlighted gold. */
  king: number;
  /** Expiration column labels, near → far (ISO date strings). */
  expirations: string[];
  /** Strike row labels, high → low. */
  strikes: number[];
  /**
   * Exposure matrix indexed [strikeRow][expirationCol].
   * `gex` and `vex` are separate surfaces (toggled in the UI). Values are
   * signed dollar exposure: positive = call-dominant, negative = put-dominant.
   */
  gex: number[][];
  vex: number[][];
}

// Deterministic pseudo-surface generator so the mock is stable across renders
// (no Math.random → no hydration / snapshot churn). Shapes a realistic
// dealer-exposure surface peaked near spot, decaying with distance and time.
function buildSurface(
  symbol: string,
  spot: number,
  strikeStep: number,
  rows: number,
  expirations: string[],
  kingOffsetRows: number,
  scale: number,
): SwingSurface {
  const half = Math.floor(rows / 2);
  const strikes: number[] = [];
  for (let i = 0; i < rows; i++) {
    // high → low
    strikes.push(Math.round((spot + (half - i) * strikeStep) * 100) / 100);
  }
  const king = strikes[Math.max(0, Math.min(rows - 1, half + kingOffsetRows))];

  const gex: number[][] = [];
  const vex: number[][] = [];
  for (let r = 0; r < rows; r++) {
    const strike = strikes[r];
    const dist = (strike - spot) / spot; // signed
    const gexRow: number[] = [];
    const vexRow: number[] = [];
    for (let c = 0; c < expirations.length; c++) {
      // Time decay: near expirations carry larger magnitude.
      const timeDecay = 1 / (1 + c * 0.35);
      // Strike envelope: peak near spot, sign flips above/below the King.
      const envelope = Math.exp(-Math.pow(dist * 14, 2));
      const sign = strike >= king ? 1 : -1;
      // Deterministic "texture" so cells aren't uniform.
      const texture = 0.6 + 0.4 * Math.sin((r * 1.7 + c * 2.3) % 6.28);
      const base = scale * envelope * timeDecay * texture;
      const g = Math.round(sign * base);
      // VEX surface — smaller magnitude, slightly different phase.
      const vTexture = 0.55 + 0.45 * Math.cos((r * 1.3 + c * 1.9) % 6.28);
      const v = Math.round(sign * scale * 0.45 * envelope * timeDecay * vTexture);
      gexRow.push(g);
      vexRow.push(v);
    }
    gex.push(gexRow);
    vex.push(vexRow);
  }

  return { symbol, spot, king, expirations, strikes, gex, vex };
}

const EXPIRATIONS = [
  '2026-01-16',
  '2026-01-23',
  '2026-01-30',
  '2026-02-06',
  '2026-02-20',
  '2026-03-20',
  '2026-04-17',
  '2026-06-18',
  '2026-09-18',
  '2026-12-18',
];

// A handful of symbols matching the Skylit ticker tabs (All / SPY / TSLA / QQQ / SPXW).
export const SWING_SURFACES: Record<string, SwingSurface> = {
  SPY: buildSurface('SPY', 605, 5, 21, EXPIRATIONS, 2, 9_400_000),
  QQQ: buildSurface('QQQ', 528, 5, 21, EXPIRATIONS, 1, 7_100_000),
  IWM: buildSurface('IWM', 232, 2, 21, EXPIRATIONS, -1, 3_600_000),
  TSLA: buildSurface('TSLA', 430, 10, 21, EXPIRATIONS, 3, 5_200_000),
  SPXW: buildSurface('SPXW', 6010, 25, 21, EXPIRATIONS, 2, 12_800_000),
};

export const SWING_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'TSLA', 'SPXW'] as const;

/** Resolve a surface for a focus symbol, falling back to SPY. */
export function surfaceFor(symbol: string): SwingSurface {
  return SWING_SURFACES[symbol] ?? SWING_SURFACES.SPY;
}
