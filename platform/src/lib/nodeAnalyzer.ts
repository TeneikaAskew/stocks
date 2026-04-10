/**
 * Node Analyzer (ported from options-heatseeker/js/nodeAnalyzer.js)
 * Detects king nodes, gatekeepers, and midpoints from aggregated strike data.
 */
import type { AggregatedStrike } from './greeksCalculator';

// Constants matching the original heatseeker config
const MIN_THRESHOLD = 500; // min absolute net_gamma to be considered significant
const TOP_NODES_COUNT = 5; // king + top gatekeepers
const MIDPOINT_THRESHOLD = 0.5; // ratio range for midpoint detection

export interface StrikeNode {
  type: 'king' | 'gatekeeper' | 'midpoint';
  strike: number;
  gamma: number;
  distance_from_spot: number;
  distance_percent: number;
  lower_bound?: number; // midpoints only
  upper_bound?: number; // midpoints only
}

export interface NodeResult {
  kingNode: StrikeNode | null;
  gatekeepers: StrikeNode[];
  midpoints: StrikeNode[];
  allNodes: StrikeNode[];
}

export function detectNodes(strikes: AggregatedStrike[], spotPrice: number): NodeResult {
  const significant = strikes.filter(s => Math.abs(s.net_gamma) >= MIN_THRESHOLD);

  if (significant.length === 0) {
    return { kingNode: null, gatekeepers: [], midpoints: [], allNodes: [] };
  }

  const sortedByGamma = [...significant].sort(
    (a, b) => Math.abs(b.net_gamma) - Math.abs(a.net_gamma)
  );

  const kingNode: StrikeNode = {
    type: 'king',
    strike: sortedByGamma[0].strike,
    gamma: sortedByGamma[0].net_gamma,
    distance_from_spot: sortedByGamma[0].strike - spotPrice,
    distance_percent: ((sortedByGamma[0].strike - spotPrice) / spotPrice) * 100,
  };

  const gatekeepers: StrikeNode[] = sortedByGamma
    .slice(1, TOP_NODES_COUNT)
    .map(s => ({
      type: 'gatekeeper' as const,
      strike: s.strike,
      gamma: s.net_gamma,
      distance_from_spot: s.strike - spotPrice,
      distance_percent: ((s.strike - spotPrice) / spotPrice) * 100,
    }));

  const midpoints = detectMidpoints(sortedByGamma, spotPrice);

  const allNodes: StrikeNode[] = [kingNode, ...gatekeepers, ...midpoints];

  return { kingNode, gatekeepers, midpoints, allNodes };
}

function detectMidpoints(sortedStrikes: AggregatedStrike[], spotPrice: number): StrikeNode[] {
  const midpoints: StrikeNode[] = [];

  for (let i = 0; i < sortedStrikes.length - 1; i++) {
    const current = sortedStrikes[i];
    const next = sortedStrikes[i + 1];

    if (current.net_gamma * next.net_gamma < 0) {
      const gammaRatio = Math.abs(current.net_gamma / next.net_gamma);

      if (gammaRatio >= MIDPOINT_THRESHOLD && gammaRatio <= 1 / MIDPOINT_THRESHOLD) {
        const midStrike = (current.strike + next.strike) / 2;
        midpoints.push({
          type: 'midpoint',
          strike: midStrike,
          gamma: 0,
          distance_from_spot: midStrike - spotPrice,
          distance_percent: ((midStrike - spotPrice) / spotPrice) * 100,
          lower_bound: Math.min(current.strike, next.strike),
          upper_bound: Math.max(current.strike, next.strike),
        });
      }
    }
  }

  return midpoints;
}
