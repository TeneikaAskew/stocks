// ===== Greeks Calculator =====

const GreeksCalculator = {
    /**
     * Calculate total GEX (Gamma Exposure)
     * GEX = Sum of (Gamma × OI × 100 × Spot² × 0.01)
     * Dealer perspective: opposite sign of customer positions
     */
    calculateGEX(options, spotPrice) {
        let totalGEX = 0;

        for (const option of options) {
            if (!option.gamma || !option.open_interest) continue;

            // Dealer sells options to customers, so they're short gamma
            // Customer long call = dealer short call (negative gamma for dealer)
            // Customer long put = dealer short put (negative gamma for dealer)
            const dealerGamma = -option.gamma;

            const gex = dealerGamma * option.open_interest *
                       CONFIG.GREEKS.SPOT_MULTIPLIER *
                       Math.pow(spotPrice, 2) *
                       CONFIG.GREEKS.GEX_MULTIPLIER;

            totalGEX += gex;
        }

        return totalGEX;
    },

    /**
     * Calculate GEX by strike
     */
    calculateGEXByStrike(aggregatedStrikes, spotPrice) {
        return aggregatedStrikes.map(strike => ({
            strike: strike.strike,
            gex: strike.net_gamma * Math.pow(spotPrice, 2) * CONFIG.GREEKS.GEX_MULTIPLIER,
            call_gex: strike.call_gamma * Math.pow(spotPrice, 2) * CONFIG.GREEKS.GEX_MULTIPLIER,
            put_gex: -strike.put_gamma * Math.pow(spotPrice, 2) * CONFIG.GREEKS.GEX_MULTIPLIER
        }));
    },

    /**
     * Calculate total VEX (Vanna Exposure)
     * VEX = Sum of (Vanna × OI × 100 × Spot × 0.01)
     * Simplified using Vega as proxy for Vanna
     */
    calculateVEX(options, spotPrice) {
        let totalVEX = 0;

        for (const option of options) {
            if (!option.vega || !option.open_interest) continue;

            // Using vega as proxy for vanna (vanna = d(delta)/d(vol))
            // Dealer perspective: opposite sign
            const dealerVanna = -option.vega;

            const vex = dealerVanna * option.open_interest *
                       CONFIG.GREEKS.SPOT_MULTIPLIER *
                       spotPrice *
                       CONFIG.GREEKS.VEX_MULTIPLIER;

            totalVEX += vex;
        }

        return totalVEX;
    },

    /**
     * Calculate Put/Call Ratio
     */
    calculatePutCallRatio(options) {
        const calls = options.filter(o => o.type === 'call');
        const puts = options.filter(o => o.type === 'put');

        const callOI = Utils.sum(calls, 'open_interest');
        const putOI = Utils.sum(puts, 'open_interest');

        const callVolume = Utils.sum(calls, 'volume');
        const putVolume = Utils.sum(puts, 'volume');

        return {
            oi_ratio: callOI > 0 ? putOI / callOI : 0,
            volume_ratio: callVolume > 0 ? putVolume / callVolume : 0,
            call_oi: callOI,
            put_oi: putOI,
            call_volume: callVolume,
            put_volume: putVolume
        };
    },

    /**
     * Calculate total delta exposure
     */
    calculateTotalDelta(options) {
        let totalDelta = 0;

        for (const option of options) {
            if (!option.delta || !option.open_interest) continue;

            // Dealer perspective: opposite sign
            const dealerDelta = -option.delta;
            totalDelta += dealerDelta * option.open_interest * CONFIG.GREEKS.SPOT_MULTIPLIER;
        }

        return totalDelta;
    },

    /**
     * Calculate zero gamma level (flip point)
     */
    calculateZeroGammaLevel(aggregatedStrikes, spotPrice) {
        // Find strikes above and below spot with opposite gamma signs
        const strikesAbove = aggregatedStrikes.filter(s => s.strike > spotPrice);
        const strikesBelow = aggregatedStrikes.filter(s => s.strike < spotPrice);

        // Look for sign change in gamma
        for (let i = 0; i < aggregatedStrikes.length - 1; i++) {
            const current = aggregatedStrikes[i];
            const next = aggregatedStrikes[i + 1];

            if ((current.net_gamma > 0 && next.net_gamma < 0) ||
                (current.net_gamma < 0 && next.net_gamma > 0)) {
                // Linear interpolation to find zero crossing
                const ratio = Math.abs(current.net_gamma) /
                            (Math.abs(current.net_gamma) + Math.abs(next.net_gamma));
                return current.strike + ratio * (next.strike - current.strike);
            }
        }

        return null;  // No zero gamma level found
    },

    /**
     * Calculate max pain (strike with maximum pain for option sellers)
     */
    calculateMaxPain(options) {
        const strikes = [...new Set(options.map(o => o.strike))].sort((a, b) => a - b);
        let maxPainStrike = strikes[0];
        let maxPainValue = Infinity;

        for (const strike of strikes) {
            let pain = 0;

            // Calculate total value of ITM options at this strike
            for (const option of options) {
                if (option.type === 'call' && option.strike < strike) {
                    pain += (strike - option.strike) * option.open_interest;
                } else if (option.type === 'put' && option.strike > strike) {
                    pain += (option.strike - strike) * option.open_interest;
                }
            }

            if (pain < maxPainValue) {
                maxPainValue = pain;
                maxPainStrike = strike;
            }
        }

        return maxPainStrike;
    },

    /**
     * Calculate implied move from ATM straddle
     */
    calculateImpliedMove(options, spotPrice) {
        // Find ATM options (closest to spot)
        let closestStrike = options[0].strike;
        let minDiff = Math.abs(options[0].strike - spotPrice);

        for (const option of options) {
            const diff = Math.abs(option.strike - spotPrice);
            if (diff < minDiff) {
                minDiff = diff;
                closestStrike = option.strike;
            }
        }

        // Get ATM call and put
        const atmCall = options.find(o =>
            o.strike === closestStrike &&
            o.type === 'call' &&
            o.dte < 7  // Use weekly options for implied move
        );

        const atmPut = options.find(o =>
            o.strike === closestStrike &&
            o.type === 'put' &&
            o.dte < 7
        );

        if (!atmCall || !atmPut) return null;

        // Straddle price (call + put)
        const straddlePrice = (atmCall.mark || atmCall.last || 0) +
                             (atmPut.mark || atmPut.last || 0);

        // Implied move as percentage
        const impliedMovePercent = (straddlePrice / spotPrice) * 100;

        return {
            straddle_price: straddlePrice,
            implied_move_percent: impliedMovePercent,
            implied_move_dollars: straddlePrice,
            upper_range: spotPrice + straddlePrice,
            lower_range: spotPrice - straddlePrice
        };
    },

    /**
     * Detect high gamma zones (strike ranges with concentrated gamma)
     */
    detectHighGammaZones(aggregatedStrikes, threshold = 0.9) {
        const zones = [];
        const sortedByGamma = [...aggregatedStrikes].sort((a, b) =>
            Math.abs(b.net_gamma) - Math.abs(a.net_gamma)
        );

        const totalGamma = Math.abs(Utils.sum(aggregatedStrikes, 'net_gamma'));
        let cumulativeGamma = 0;

        for (const strike of sortedByGamma) {
            cumulativeGamma += Math.abs(strike.net_gamma);

            zones.push({
                strike: strike.strike,
                gamma: strike.net_gamma,
                cumulative_percent: cumulativeGamma / totalGamma
            });

            if (cumulativeGamma / totalGamma >= threshold) {
                break;
            }
        }

        return zones;
    },

    /**
     * Calculate GEX/VEX profile interpretation
     */
    interpretGEXVEX(gex, vex) {
        const interpretation = {
            gex_signal: '',
            vex_signal: '',
            market_regime: '',
            volatility_bias: '',
            description: ''
        };

        // GEX interpretation
        if (gex > 0) {
            interpretation.gex_signal = 'Positive';
            interpretation.volatility_bias = 'Low volatility / Range-bound';
        } else {
            interpretation.gex_signal = 'Negative';
            interpretation.volatility_bias = 'High volatility / Trending';
        }

        // VEX interpretation
        if (vex > 0) {
            interpretation.vex_signal = 'Positive';
            interpretation.vol_change_bias = 'Bullish on vol drop';
        } else {
            interpretation.vex_signal = 'Negative';
            interpretation.vol_change_bias = 'Bearish on vol drop';
        }

        // Combined interpretation
        if (gex > 0 && vex > 0) {
            interpretation.market_regime = 'Pinned / Low Vol';
            interpretation.description = 'Market likely to chop. Positive VEX suggests upside if vol drops.';
        } else if (gex > 0 && vex < 0) {
            interpretation.market_regime = 'Pinned / Bearish Vol Bias';
            interpretation.description = 'Market choppy. Negative VEX suggests downside if vol drops.';
        } else if (gex < 0 && vex > 0) {
            interpretation.market_regime = 'Trending / Bullish Vol Bias';
            interpretation.description = 'Large moves possible. Positive VEX suggests strong upside potential.';
        } else {
            interpretation.market_regime = 'Trending / Bearish Vol Bias';
            interpretation.description = 'Large moves possible. Negative VEX suggests strong downside risk.';
        }

        return interpretation;
    }
};

// Freeze GreeksCalculator to prevent modifications
Object.freeze(GreeksCalculator);
