/**
 * Options Greeks Calculator (ported from options-heatseeker/js/greeksCalculator.js)
 * Computes GEX, VEX, and related metrics from options chain data.
 */

export interface OptionRecord {
  type: 'call' | 'put';
  strike: number;
  open_interest: number;
  gamma: number;
  vega: number;
  delta: number;
  volume: number;
  /** Provenance of the Greeks on this row. 'computed_bsm' for tickers
   * (e.g. SPX) where the platform back-end solves IV from AlphaVantage mid
   * prices; 'alphavantage' for tickers where AV publishes Greeks directly. */
  greeks_source?: 'alphavantage' | 'computed_bsm';
}

export interface AggregatedStrike {
  strike: number;
  net_gamma: number;
  call_gamma: number;
  put_gamma: number;
  call_oi: number;
  put_oi: number;
  call_volume: number;
  put_volume: number;
}

export interface GEXByStrike {
  strike: number;
  gex: number;
  call_gex: number;
  put_gex: number;
}

const SPOT_MULTIPLIER = 100;
const GEX_MULTIPLIER = 0.01;
const VEX_MULTIPLIER = 0.01;

export function aggregateByStrike(options: OptionRecord[]): AggregatedStrike[] {
  const map = new Map<number, AggregatedStrike>();

  for (const opt of options) {
    const s = opt.strike;
    if (!map.has(s)) {
      map.set(s, { strike: s, net_gamma: 0, call_gamma: 0, put_gamma: 0, call_oi: 0, put_oi: 0, call_volume: 0, put_volume: 0 });
    }
    const agg = map.get(s)!;
    const gamma = (opt.gamma ?? 0) * (opt.open_interest ?? 0);
    if (opt.type === 'call') {
      agg.call_gamma += gamma;
      agg.call_oi += opt.open_interest ?? 0;
      agg.call_volume += opt.volume ?? 0;
      agg.net_gamma += gamma; // calls add positive gamma
    } else {
      agg.put_gamma += gamma;
      agg.put_oi += opt.open_interest ?? 0;
      agg.put_volume += opt.volume ?? 0;
      agg.net_gamma -= gamma; // puts subtract gamma (dealer long put = short gamma)
    }
  }

  return Array.from(map.values()).sort((a, b) => a.strike - b.strike);
}

export function calculateGEXByStrike(strikes: AggregatedStrike[], spotPrice: number): GEXByStrike[] {
  return strikes.map(s => ({
    strike: s.strike,
    gex: s.net_gamma * Math.pow(spotPrice, 2) * GEX_MULTIPLIER,
    call_gex: s.call_gamma * Math.pow(spotPrice, 2) * GEX_MULTIPLIER,
    put_gex: -s.put_gamma * Math.pow(spotPrice, 2) * GEX_MULTIPLIER,
  }));
}

export function calculateTotalGEX(options: OptionRecord[], spotPrice: number): number {
  return options.reduce((sum, opt) => {
    if (!opt.gamma || !opt.open_interest) return sum;
    const dealerGamma = -opt.gamma;
    return sum + dealerGamma * opt.open_interest * SPOT_MULTIPLIER * Math.pow(spotPrice, 2) * GEX_MULTIPLIER;
  }, 0);
}

export function calculateTotalVEX(options: OptionRecord[], spotPrice: number): number {
  return options.reduce((sum, opt) => {
    if (!opt.vega || !opt.open_interest) return sum;
    const dealerVanna = -opt.vega;
    return sum + dealerVanna * opt.open_interest * SPOT_MULTIPLIER * spotPrice * VEX_MULTIPLIER;
  }, 0);
}

export function calculateZeroGammaLevel(strikes: AggregatedStrike[]): number | null {
  for (let i = 0; i < strikes.length - 1; i++) {
    if (strikes[i].net_gamma * strikes[i + 1].net_gamma < 0) {
      // Linear interpolation
      const { strike: s1, net_gamma: g1 } = strikes[i];
      const { strike: s2, net_gamma: g2 } = strikes[i + 1];
      return s1 + (0 - g1) * (s2 - s1) / (g2 - g1);
    }
  }
  return null;
}

export function calculateMaxPain(strikes: AggregatedStrike[]): number | null {
  if (strikes.length === 0) return null;
  let minPain = Infinity;
  let maxPainStrike = strikes[0].strike;
  for (const target of strikes) {
    const pain = strikes.reduce((sum, s) => {
      const callPain = Math.max(0, target.strike - s.strike) * s.call_oi;
      const putPain = Math.max(0, s.strike - target.strike) * s.put_oi;
      return sum + callPain + putPain;
    }, 0);
    if (pain < minPain) {
      minPain = pain;
      maxPainStrike = target.strike;
    }
  }
  return maxPainStrike;
}

export function calculateImpliedMove(options: OptionRecord[], spotPrice: number): number | null {
  const atm = options.filter(o => Math.abs(o.strike - spotPrice) / spotPrice < 0.02);
  if (atm.length === 0) return null;
  const avgVega = atm.reduce((s, o) => s + (o.vega ?? 0), 0) / atm.length;
  return avgVega * Math.sqrt(252) * spotPrice * 0.01;
}

export interface OptionsMetrics {
  totalGEX: number;
  totalVEX: number;
  zeroGamma: number | null;
  maxPain: number | null;
  impliedMove: number | null;
  putCallRatio: number;
}

export function computeAllMetrics(options: OptionRecord[], spotPrice: number): OptionsMetrics {
  const strikes = aggregateByStrike(options);
  const calls = options.filter(o => o.type === 'call');
  const puts = options.filter(o => o.type === 'put');
  const callOI = calls.reduce((s, o) => s + (o.open_interest ?? 0), 0);
  const putOI = puts.reduce((s, o) => s + (o.open_interest ?? 0), 0);

  return {
    totalGEX: calculateTotalGEX(options, spotPrice),
    totalVEX: calculateTotalVEX(options, spotPrice),
    zeroGamma: calculateZeroGammaLevel(strikes),
    maxPain: calculateMaxPain(strikes),
    impliedMove: calculateImpliedMove(options, spotPrice),
    putCallRatio: callOI > 0 ? putOI / callOI : 0,
  };
}
