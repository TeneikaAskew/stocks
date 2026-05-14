import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { useIndicatorConfig, type IndicatorConfig } from '@/hooks/useConfig';

interface GlossaryEntry {
  term: string;
  short: string;
  detail?: string;
  category: string;
}

// Build the glossary array from the live indicator config so periods and
// thresholds match what Python is actually using. When the config query is
// still loading we substitute the documented defaults from lib/config.py
// so the page never looks broken on first paint.
function buildGlossary(cfg: IndicatorConfig | undefined): GlossaryEntry[] {
  const rsiPeriod = cfg?.rsi.period ?? 14;
  const rsiOversold = cfg?.rsi.oversold ?? 30;
  const rsiOverbought = cfg?.rsi.overbought ?? 70;
  const emaFast = cfg?.ema.periods[0] ?? 9;
  const emaMid = cfg?.ema.periods[1] ?? 20;
  const stochOversold = cfg?.stoch_rsi.oversold ?? 20;
  const stochOverbought = cfg?.stoch_rsi.overbought ?? 80;
  const rvolThreshold = cfg?.rvol.signal_threshold ?? 1.0;
  const minConditions = cfg?.signal.min_conditions ?? 3;

  return [
  // Strategy & Signals
  { term: 'Win Rate', short: 'Percentage of trades that were profitable.', detail: 'A 41% win rate means roughly 4 out of every 10 trades made money. Win rate alone doesn\'t determine profitability — if winners are larger than losers, you can profit with a low win rate.', category: 'Performance' },
  { term: 'Profit Factor', short: 'Total gains divided by total losses.', detail: 'A profit factor of 1.03 means for every $1 lost, the strategy made $1.03. Above 1.0 = profitable. Above 1.5 = strong. Below 1.0 = losing money.', category: 'Performance' },
  { term: 'Total Return', short: 'Cumulative profit/loss across all trades.', detail: 'Expressed as a percentage of starting equity. A +9.6% total return means the strategy grew the account by 9.6% over the backtest period.', category: 'Performance' },
  { term: 'Max Drawdown (Max DD)', short: 'Largest peak-to-trough decline in equity.', detail: 'If the account went from $10,000 to $9,730 before recovering, the max drawdown is -2.7%. This measures worst-case pain during the strategy\'s lifetime.', category: 'Performance' },
  { term: 'Avg Win / Avg Loss', short: 'Average size of winning vs losing trades.', detail: 'Shown as percentages. If avg win is +0.29% and avg loss is -0.20%, winners are about 1.5x the size of losers. This ratio matters more than win rate for overall profitability.', category: 'Performance' },
  { term: 'Expectancy', short: 'Average expected return per trade.', detail: 'Calculated as (win_rate × avg_win) - (loss_rate × avg_loss). Positive expectancy means the strategy makes money over many trades.', category: 'Performance' },
  { term: 'Basis Points (bps)', short: 'One hundredth of a percent. 100 bps = 1%.', detail: 'Common in finance to express small percentage changes. 29 bps = 0.29%. This platform shows values as percentages for clarity, but you may see "bps" in external tools and research.', category: 'Performance' },

  // The Strat
  { term: 'The Strat', short: 'A price action methodology based on candlestick patterns.', detail: 'Created by Rob Smith. Classifies every candle as a 1 (inside bar), 2 (directional), or 3 (outside bar). Combines multi-timeframe candle types to identify setups.', category: 'The Strat' },
  { term: 'Strat Candle (1, 2U, 2D, 3)', short: 'Classification of a candle based on its high/low vs previous candle.', detail: '1 = Inside bar (lower high AND higher low). 2U = Higher high without lower low (bullish). 2D = Lower low without higher high (bearish). 3 = Outside bar (higher high AND lower low).', category: 'The Strat' },
  { term: 'Strat Combo', short: 'Sequence of candle types across bars (e.g., 2-1-2).', detail: 'A 2-1-2 means: previous bar was directional (2), current bar is inside (1), and you\'re waiting for the next bar to break out (2). Common setups: 2-1-2, 3-1-2, 1-2-2.', category: 'The Strat' },
  { term: 'FTFC (Full Timeframe Continuity)', short: 'All timeframes aligned in the same direction.', detail: 'When the 5min, 15min, 30min, hourly, and daily charts all show the same direction (e.g., all bullish 2U), there is full timeframe continuity. Higher FTFC score = stronger directional conviction.', category: 'The Strat' },
  { term: 'FTFC Score', short: 'Numeric measure of timeframe alignment (-1 to +1).', detail: 'Positive = bullish alignment across timeframes. Negative = bearish. Near zero = mixed/no clear direction. Calculated by weighting each timeframe\'s direction.', category: 'The Strat' },
  { term: 'RevStrat', short: 'Reversal Strat — a 3-bar reversal pattern.', detail: 'Occurs when a 3 (outside bar) reverses the prior direction. For example, a bearish move followed by a 3 that takes out the prior high signals a potential bullish reversal.', category: 'The Strat' },
  { term: 'Failed 2U (f2u_bear_reversal)', short: 'A 2U bar that closes below its open.', detail: 'High broke above the prior bar (printing 2U) but the candle closed below its own open — meaning bears took control after the breakout. Bearish reversal signal. Favors PUT setups. Lowest priority on collision: any multi-bar combo wins.', category: 'The Strat' },
  { term: 'Failed 2D (f2d_bull_reversal)', short: 'A 2D bar that closes above its open.', detail: 'Low broke below the prior bar (printing 2D) but the candle closed above its own open. Bullish reversal signal. Favors CALL setups. Mirror of Failed 2U.', category: 'The Strat' },
  { term: '22 Continuation', short: 'Two consecutive 2U or 2D bars — trend continuation.', detail: 'Each bar makes a higher high (22_bull_continuation) or lower low (22_bear_continuation) than the prior bar. Plain two-bar version, distinct from the 3-bar 212 continuation that requires a compressed inside bar between.', category: 'The Strat' },
  { term: '212 Reversal', short: '3-bar reversal: directional → inside → opposite directional.', detail: 'A 2D-1-2U breaks above the inside bar to signal a bullish reversal (212_bull_reversal); 2U-1-2D mirrors it bearishly. Highest-conviction multi-bar pattern.', category: 'The Strat' },
  { term: 'Inside Bar Setup', short: 'A 1 (inside bar) following a directional move — compression before the next leg.', detail: 'Inside bars compress the prior range and signal indecision. The breakout direction usually leans with the prior bar\'s direction (continuation) or opposite (reversal). Wait for the breakout, don\'t guess.', category: 'The Strat' },
  { term: 'Trigger Level', short: 'The breakout price that confirms a Strat setup.', detail: 'The prior bar\'s high (for bullish triggers) or low (for bearish). A candle that takes out the trigger with volume confirms the pattern. Used as the entry reference point.', category: 'The Strat' },

  // Technical Indicators
  { term: 'RSI (Relative Strength Index)', short: 'Momentum oscillator measuring speed of price changes (0-100).', detail: `Below ${rsiOversold} = oversold (potential bounce). Above ${rsiOverbought} = overbought (potential pullback). The strategy uses RSI ${rsiPeriod} (${rsiPeriod}-period) as the primary. RSI between 40-60 is neutral.`, category: 'Indicators' },
  { term: 'EMA (Exponential Moving Average)', short: 'A moving average that weights recent prices more heavily.', detail: `EMA ${emaFast} (fast) and EMA ${emaMid} (slow) are used. Price above EMA = bullish. EMA ${emaFast} crossing above EMA ${emaMid} = bullish signal. The strategy tracks "price vs EMA" as a percentage distance.`, category: 'Indicators' },
  { term: 'SMA 200', short: '200-day Simple Moving Average — the long-term trend line.', detail: 'Price above SMA 200 = long-term uptrend. Price below = downtrend. Institutional traders watch this level closely.', category: 'Indicators' },
  { term: 'VWAP (Volume Weighted Average Price)', short: 'Average price weighted by volume throughout the day.', detail: 'Resets daily. Price above VWAP = buyers are in control. Below = sellers. Day traders use VWAP as a key level for entries and exits.', category: 'Indicators' },
  { term: 'MACD', short: 'Moving Average Convergence Divergence — trend and momentum indicator.', detail: 'Shows the relationship between two EMAs (12 and 26 period). MACD line crossing above signal line = bullish. Histogram shows the gap between them.', category: 'Indicators' },
  { term: 'ATR (Average True Range)', short: 'Measures average price volatility over N periods.', detail: 'Higher ATR = more volatility = bigger potential moves (and bigger risk). Used for setting stop losses and profit targets proportional to current volatility.', category: 'Indicators' },
  { term: 'RVOL (Relative Volume)', short: 'Current volume compared to the average for this time of day.', detail: `RVOL 1.5 = 50% more volume than usual. High RVOL confirms that a move has participation. Low RVOL moves are more likely to reverse. The strategy requires RVOL > ${rvolThreshold.toFixed(1)} for signals.`, category: 'Indicators' },
  { term: 'Bollinger Bands', short: 'Volatility bands plotted 2 standard deviations from a moving average.', detail: 'Price touching the upper band = extended/overbought. Lower band = oversold. Band width expanding = increasing volatility. Squeezing = low vol, potential breakout coming.', category: 'Indicators' },
  { term: 'StochRSI', short: 'RSI applied to RSI — a more sensitive momentum oscillator.', detail: `Ranges from 0 to 100. Below ${stochOversold} = oversold. Above ${stochOverbought} = overbought. More responsive than regular RSI, so it gives earlier signals but more false positives.`, category: 'Indicators' },

  // ORB
  { term: 'ORB (Opening Range Breakout)', short: 'Trading strategy based on the first N minutes of the session.', detail: 'The opening range is defined by the high and low of the first 5, 15, or 30 minutes. A breakout above the ORB high is bullish; below the ORB low is bearish. Used with volume confirmation.', category: 'ORB' },
  { term: 'ORB Trend', short: 'Direction of the opening range breakout.', detail: 'Bullish if price broke above the ORB high first. Bearish if it broke below the ORB low. "Inside ORB" means price hasn\'t broken either level yet.', category: 'ORB' },

  // Options
  { term: 'CALL', short: 'Bullish option — profits when the underlying goes up.', detail: 'Buying a call gives you the right to buy the stock at the strike price. In this system, CALL signals mean the strategy expects the price to go up.', category: 'Options' },
  { term: 'PUT', short: 'Bearish option — profits when the underlying goes down.', detail: 'Buying a put gives you the right to sell the stock at the strike price. PUT signals mean the strategy expects the price to go down.', category: 'Options' },
  { term: '0DTE', short: 'Zero Days to Expiration — options expiring today.', detail: 'High risk, high reward. Small price moves create large percentage gains/losses. The strategy primarily trades 0DTE options on SPY, IWM, and QQQ.', category: 'Options' },
  { term: 'IV (Implied Volatility)', short: 'Market\'s expectation of future price movement, priced into options.', detail: 'Higher IV = more expensive options = market expects bigger moves. IV typically spikes before earnings/events and drops after (IV crush).', category: 'Options' },
  { term: 'Delta', short: 'How much the option price moves per $1 move in the stock.', detail: 'A call with delta 0.50 gains $0.50 when the stock goes up $1. Delta also approximates the probability of expiring in-the-money.', category: 'Options' },
  { term: 'Gamma', short: 'Rate of change of delta — how fast delta changes.', detail: 'High gamma means delta changes rapidly as the stock moves. 0DTE options have very high gamma, making them explosive in both directions.', category: 'Options' },
  { term: 'Theta', short: 'Time decay — how much value the option loses per day.', detail: 'Always negative for option buyers. 0DTE options have massive theta — they lose value rapidly as expiration approaches. This is why timing matters.', category: 'Options' },
  { term: 'Vega', short: 'Sensitivity to changes in implied volatility.', detail: 'A vega of 0.10 means the option price moves $0.10 for every 1 percentage point change in IV. Long options are long vega; their value rises when IV rises.', category: 'Options' },
  { term: 'Open Interest (OI)', short: 'Number of outstanding option contracts at a strike.', detail: 'High OI = more dealer hedging required at that strike, which is what makes it a gamma node. Volume is daily activity; OI is total open positions.', category: 'Options' },
  { term: 'Put/Call Ratio', short: 'Total put open interest divided by total call open interest.', detail: 'Above 1.0 = more puts than calls (bearish hedging or bearish bet). Below 1.0 = call-dominated (bullish skew). Extreme readings can be contrarian.', category: 'Options' },
  { term: 'Max Pain', short: 'Strike where the most option holders lose value at expiration.', detail: 'Theory: price tends to gravitate toward max pain on expiry days because dealers benefit. Used as a rough magnet level alongside gamma analysis.', category: 'Options' },
  { term: 'Implied Move', short: 'Expected price range through expiration based on option premiums.', detail: 'Computed from the at-the-money straddle. If implied move is $5 with spot at $250, the market is pricing a one-standard-deviation move into a $245-$255 range by expiry.', category: 'Options' },

  // Gamma Levels (Stratalyst-style taxonomy — see docs/gamma_levels.md)
  { term: 'GEX (Gamma Exposure)', short: 'Net dollar gamma dealers carry at each strike.', detail: 'Net GEX per strike = (call_gamma × call_OI − put_gamma × put_OI) × spot². Positive GEX = call-dominated (resistance / pinning). Negative GEX = put-dominated (support / vol-amplifying). Total GEX is the sum across the chain.', category: 'Gamma Levels' },
  { term: 'Spot Price', short: 'Current price of the underlying.', detail: 'Estimated server-side via three fallbacks: (1) put-call parity at the smallest |C−P| pair (most accurate), (2) the call closest to delta 0.5, (3) the median strike. The chip next to the spot input shows which method was used. You can override manually if the chain is too thin to estimate from.', category: 'Gamma Levels' },
  { term: 'Gamma Flip', short: 'The price level where dealer net gamma flips sign.', detail: 'Computed as the cumulative-GEX zero crossing nearest spot. Above the flip = positive gamma regime (pinning, range-bound). Below = negative gamma regime (trending, vol-amplifying). Crossing the flip with volume signals a regime change.', category: 'Gamma Levels' },
  { term: 'Regime — Positive Gamma', short: 'Price is above the flip — dealers suppress volatility.', detail: 'Dealers buy dips and sell rips to hedge their short-gamma position, which damps moves. Expect range-bound action, mean reversion at high-gamma strikes, and ~80% reaction rate on first touches of Kings.', category: 'Gamma Levels' },
  { term: 'Regime — Negative Gamma', short: 'Price is below the flip — dealers amplify volatility.', detail: 'Dealers sell dips and buy rips, which accelerates moves. Expect trending, breakouts that follow through, and Kings acting as magnets that pull price toward them.', category: 'Gamma Levels' },
  { term: 'King Node (★)', short: 'The strike with the largest absolute net GEX in the visible window.', detail: 'Primary support or resistance magnet. Dealers hedge most aggressively here, so first touches typically react. In positive gamma, expect a bounce; in negative gamma, expect price to be pulled toward it. Marked with a star and gold line on the chart.', category: 'Gamma Levels' },
  { term: 'Gate Node (◆)', short: 'A secondary high-gamma strike (≥20% of the King\'s |GEX|).', detail: 'Acts as resistance the King is hiding behind — price has to break the Gate before reaching the King. Multiple gates often form a corridor around the King. Marked with a diamond and blue dotted line on the chart.', category: 'Gamma Levels' },
  { term: 'Spot Tag', short: 'Strikes within 0.2% of the current spot price.', detail: 'Pure visual marker showing which strike(s) are at-the-money on the gamma ladder. No trading meaning by itself, but useful for orienting where price sits relative to the Kings and Gates.', category: 'Gamma Levels' },
  { term: 'Flip Tag (⇅)', short: 'The two strikes immediately bracketing the gamma flip price.', detail: 'These are the strikes you want to watch for a regime change. If price is sitting on a Flip-tagged strike and volume picks up in the direction of the cross, the dealer hedge flow flips with it.', category: 'Gamma Levels' },
  { term: 'Total GEX', short: 'Sum of net GEX across the visible window.', detail: 'Positive total = call concentration dominates (typically pinning bias). Negative total = put concentration dominates (typically trending bias). The metric card uses the same sign convention as the per-strike heatmap, derived from the per-strike sum.', category: 'Gamma Levels' },
  { term: 'Zero Gamma', short: 'Legacy field — first per-strike GEX sign change in the chain.', detail: 'Older naming for what gamma flip approximates. The modern Gamma Flip metric uses the cumulative-GEX zero crossing near spot, which is more meaningful than the first sign change.', category: 'Gamma Levels' },

  // Signals & Scoring
  { term: 'Signal Score', short: 'Number of conditions met out of 5 for a trade entry.', detail: `The system checks 5 conditions (RSI range, EMA alignment, VWAP position, RVOL threshold, StochRSI). A score of ${minConditions}/5 is the minimum for a signal. Higher = stronger conviction.`, category: 'Signals' },
  { term: 'Base Score', short: 'Score from the 5 core signal conditions.', detail: `Each met condition adds 1 point. Range: 0-5. The minimum threshold for a valid signal is ${minConditions}.`, category: 'Signals' },
  { term: 'Strat Bonus', short: 'Extra score points from Strat pattern alignment.', detail: 'Added to the base score when the Strat candle pattern and FTFC alignment support the signal direction. Can push a marginal signal into a strong one.', category: 'Signals' },
  { term: 'Conditions Met', short: 'Which of the 5 signal conditions are currently true.', detail: 'Displayed as "3/5" or "4/5". The conditions are: RSI in range, price vs EMA alignment, VWAP position, RVOL above minimum, and StochRSI confirmation.', category: 'Signals' },

  // Playbook & Backtest
  { term: 'Playbook', short: 'Predefined setup cards — specific patterns to watch for and trade.', detail: 'Each card defines: candle pattern, indicator conditions, direction (CALL/PUT), historical win rate, and average return. Generated from Phase 6 analysis of 10+ years of data.', category: 'Playbook' },
  { term: 'Backtest', short: 'Running the strategy on historical data to measure performance.', detail: 'The system backtests across 2015-2026 data. Results show how the strategy would have performed historically. Past results don\'t guarantee future performance.', category: 'Playbook' },
  { term: 'Exit Reason', short: 'Why a trade was closed.', detail: 'Common reasons: profit_target (hit take-profit), stop_loss (hit stop), time_stop (held too long, forced exit), rsi_exit (RSI hit extreme level).', category: 'Playbook' },
  { term: 'MAE / MFE', short: 'Maximum Adverse/Favorable Excursion — worst and best points during a trade.', detail: 'MAE = how far the trade went against you before closing. MFE = how far it went in your favor. Helps evaluate if stops are too tight or targets too aggressive.', category: 'Playbook' },

  // Dashboard
  { term: 'Daily Bias', short: 'The overall directional lean for the trading day.', detail: 'Derived from FTFC direction, RSI level, and price position vs EMAs. Bullish = favor CALL setups. Bearish = favor PUT setups. Neutral = no clear edge, be selective.', category: 'Dashboard' },
  { term: 'Previous Day Levels', short: 'Yesterday\'s high, low, and close — key support/resistance.', detail: 'Price tends to react at these levels. Previous high = resistance (sellers may appear). Previous low = support (buyers may step in). Previous close = neutral pivot.', category: 'Dashboard' },
  { term: 'Consecutive Up/Down', short: 'Number of days in a row the stock closed higher (or lower).', detail: 'A streak of 3+ consecutive up days may signal overextension. Useful for mean-reversion and continuation setups.', category: 'Dashboard' },
  { term: 'Cloud SQL', short: 'The cloud database storing all market data and analysis.', detail: 'When connected, the dashboard pulls daily indicators, premarket analysis, and trade history from Google Cloud SQL. When disconnected, some features are unavailable.', category: 'Dashboard' },

  // Structural levels — abbreviations shown in the premarket brief / playbook
  { term: 'PDH / PDL', short: 'Previous-trading-session High / Low.', detail: 'High and low of the MOST RECENT completed RTH session — that\'s Friday on a Monday brief, and the day before the holiday after a market holiday (not the calendar day before). The most heavily-watched levels because every prior-day trader remembers them as support/resistance. PDH typically caps a continuation rally; PDL typically catches a flush.', category: 'Structural Levels' },
  { term: 'PDC', short: 'Previous-trading-session Close.', detail: 'Closing price of the most recent completed RTH session — the neutral pivot for today\'s gap. Above PDC = bullish bias on the open; below = bearish gap. On a Monday brief this is Friday\'s close, not calendar-yesterday\'s.', category: 'Structural Levels' },
  { term: 'PDO (Previous-session Open)', short: 'Open of the most recent completed RTH session.', detail: 'Yesterday\'s RTH open price (Friday\'s on a Monday brief, etc.). Emitted in the 8:30 AM premarket brief because today\'s open does not exist yet — PDO is the latest-known open observable before today\'s RTH starts. Often a magnet level when today opens near it. Do NOT confuse with CDO (today\'s open, only knowable once today opens).', category: 'Structural Levels' },
  { term: 'CDO (Current Day Open)', short: 'TODAY\'s session open — only knowable after 9:30 AM ET.', detail: 'Today\'s actual RTH open price. Emitted by the strat-level builder ONLY when today\'s daily row is in the dataset (mid-session, post-close, or live analytics). In the 8:30 AM premarket brief, today has not opened yet so the builder emits PDO instead. CDO appears in mid-session insights, EOD reports, and the website\'s live charts; in the premarket brief you should be reading PDO.', category: 'Structural Levels' },
  { term: 'PWH / PWL / PWC / PWO', short: 'Previous Week High / Low / Close / Open.', detail: 'The completed prior week\'s anchor levels. PWH caps weekly rallies; PWL catches weekly flushes. PWO surfaces in the Monday-morning premarket brief when this Monday is the first session of a new week (same idea as PDO).', category: 'Structural Levels' },
  { term: 'CWO (Current Week Open)', short: 'THIS week\'s open — only knowable once Monday RTH has opened.', detail: 'This week\'s RTH open on the first trading day of the week. Like CDO, this is only emitted once the period has actually started; in the Monday-morning premarket the builder emits PWO instead.', category: 'Structural Levels' },
  { term: 'PMH / PML / PMC / PMO', short: 'Previous Month High / Low / Close / Open.', detail: 'Anchor levels from the completed prior month. PMO appears in the premarket brief when today is the first business day of a new month (same idea as PDO).', category: 'Structural Levels' },
  { term: 'CMO (Current Month Open)', short: 'THIS month\'s open — only knowable after the first business day opens.', detail: 'This month\'s RTH open on the first business day of the month. Only emitted once the period has actually started.', category: 'Structural Levels' },
  { term: 'PQH / PQL', short: 'Previous Quarter High / Low.', detail: 'Anchor highs/lows from the prior quarter. Longer-timeframe magnets that institutions use as reference points for quarterly rebalance decisions.', category: 'Structural Levels' },
  { term: 'PYH / PYL', short: 'Previous Year High / Low.', detail: 'The prior calendar year\'s extremes. Rare-touch levels but high-conviction when reached — frequently appear as the strongest PMG zone components.', category: 'Structural Levels' },
  { term: 'GAP_H / GAP_L', short: 'Unfilled gap high / low boundaries.', detail: 'When a session opens substantially above (or below) the prior close, the candle leaves an unfilled gap. GAP_H is the upper boundary of the gap; GAP_L is the lower. Gaps tend to act as magnets — price often returns to fill them. Labelled with the date of the gap, e.g. GAP_H_2026-05-05.', category: 'Structural Levels' },
  { term: 'PMK_H / PMK_L', short: 'Premarket High / Low (4 AM – 9:30 AM ET).', detail: 'High and low printed during the 4:00–9:30 ET premarket session. Surface in the brief on gap days as an early gauge of the day\'s extension. Often the actual turn level when the RTH ORB confirms.', category: 'Structural Levels' },
  { term: 'PMG Zone', short: 'Pivot Machine Gun — cluster of 2+ levels from different timeframes within ~0.15%.', detail: 'When PDH and PWH (for example) sit within 0.15% of each other, the cluster has compound strength — anyone watching either level sees the same price. Strength = count of clustering levels; 3-of-3 zones rarely get sliced through on the first touch.', category: 'Structural Levels' },

  // Earnings Brief — added 2026-05-14 with the AV ∩ UW pipeline + playability scoring
  { term: 'Earnings Brief', short: '8:30 AM ET Discord embed showing today\'s tradeable earnings reporters.', detail: 'Filters today\'s ~800 raw earnings names down to ~20-25 names that pass: (1) AV ∩ UW source confirmation, (2) options_volume > 0, (3) open_interest > 1000. Sorts by playability_score (vol × consistency × log(opt_vol)). Each name carries archetype (bullish/bearish/reversal/mixed) plus historical reaction profile.', category: 'Earnings Brief' },
  { term: 'AV ∩ UW Gate', short: 'Earnings tickers must appear in BOTH AlphaVantage AND Unusual Whales source rows.', detail: 'AV provides the date-of-truth from SEC filings. UW provides the curated daily list of options-tradeable names. Their intersection (~30-37 tickers/day) is the brief\'s universe. Replaces the legacy "tier ≤ 3" filter — keeps major institutional names like SONY/TCOM/JBS that EW templates skip, drops OTC pink-sheet AV-only entries.', category: 'Earnings Brief' },
  { term: 'Playability Score', short: 'Composite tradeability metric for an upcoming earnings reporter.', detail: 'Formula: move_magnitude × max(direction_consistency, 0.5 + 0.5 × reversal_rate) × log(options_volume + 1). Higher = more tradeable. Brief sorts by this descending. A score above 20 is exceptional; 10-20 is strong; below 5 is marginal. Computed in lib/earnings_reactions.py from the last N quarters of post-earnings reactions.', category: 'Earnings Brief' },
  { term: 'Playability Archetype', short: 'Categorical tag describing how a ticker historically reacts to earnings.', detail: 'One of five: bullish_trend, bearish_trend, reversal_play, mixed, quiet. Drives the action tag in the brief: bullish_trend → CALL, bearish_trend → PUT, reversal_play → STRDL (changed from FADE on 2026-05-14 after backtest showed the directional fade is anti-predictive at high conviction), mixed → STRDL, quiet → row filtered. Classified by classify_archetype() from move magnitude, directional bias, consistency, and reversal rate.', category: 'Earnings Brief' },
  { term: 'Archetype: bullish_trend', short: 'Stock consistently moves UP on earnings.', detail: 'High direction_consistency (≥65%) AND positive directional_bias (>0.5%). Action: CALL. 54.8% backtest hit rate — beats coin flip. Higher conviction with more quarters of history (nQ ≥ 12 required for the brief). Examples observed: AVGO, LLY, WMT.', category: 'Earnings Brief' },
  { term: 'Archetype: bearish_trend', short: 'Stock consistently moves DOWN on earnings — but treat with caution.', detail: 'High direction_consistency (≥65%) AND negative directional_bias (<-0.5%). Action: PUT. CAVEAT: 44.6% backtest hit rate is below the 50% baseline, meaning historically the directional put bet has underperformed for this archetype. Use as a small-size watch, not a high-conviction trade. The Q-quintile + confidence label tells you how much to trust the call.', category: 'Earnings Brief' },
  { term: 'Archetype: reversal_play', short: 'Stock has a historical pattern of reversing on earnings (gaps then fades).', detail: 'High reversal_rate (≥40%) AND low direction_consistency (<50%). Action: STRDL (was FADE pre-2026-05-14). Backtest 2026-05-14 showed the score INVERTS for this archetype — Q5 (top conviction) had 37.2% hit rate vs Q1 41.8%. Translation: when the model is most confident it will reverse, it usually doesn\'t. So we play vol (straddle) instead of betting the fade direction. Move magnitude is real; direction is not.', category: 'Earnings Brief' },
  { term: 'Archetype: mixed', short: 'Big moves but no consistent direction — pure volatility play.', detail: 'Moderate move magnitude, ~50% directional consistency. The play is to capture the volatility regardless of direction: long straddle (if IV < expected move) or iron butterfly (if IV > expected move). Examples: BHF ($3.5B, score 51.2!), DLO (12.3% Move), AMAT ($346B, deep liquidity).', category: 'Earnings Brief' },
  { term: 'Archetype: quiet', short: 'Small moves, no clear pattern — skip.', detail: 'Move magnitude below the typical_daily_return threshold OR insufficient history to classify. The brief still surfaces them if they pass the AV ∩ UW + liquidity gates, but their playability_score is null and they fall back to OI-ordered ranking. Treat as "in the universe but no edge."', category: 'Earnings Brief' },
  { term: 'Move Magnitude (Move%)', short: 'Average absolute reaction-day move over last N quarters.', detail: 'Mean of |reaction_gap_pct| across the lookback window. A 12% Move% means the average earnings reaction (positive or negative) moved the stock 12% on the report day. Compare to the implied move (priced into options) — if Move% > implied, options are CHEAP for the realized vol.', category: 'Earnings Brief' },
  { term: 'Direction Consistency (Dir%)', short: '% of quarters that moved in the same direction on earnings.', detail: 'Higher = more directional bias. Above 70% = strong directional pattern (use call/put spreads). 50% = coin flip (use straddle). Below 40% with high reversal_rate = pop-and-fade pattern.', category: 'Earnings Brief' },
  { term: 'Reversal Rate (Rev%)', short: '% of quarters with intraday reversal on the report day.', detail: 'Computed as: sign flip between the open-direction and close-direction within the report-day candle, AND the reversal magnitude is ≥0.5× the initial move. Above 60% = strong fade pattern; the announcement pop typically reverses by close.', category: 'Earnings Brief' },
  { term: 'Sample Size (nQ)', short: 'Number of historical quarters used to compute the playability metrics.', detail: 'Range: 1-12. nQ = 12 means we have 3 years of reaction data — high-confidence stats. nQ ≤ 4 means newly-IPO\'d or limited history — use with caution; the score is more volatile. The brief shows nQ alongside the score so you can weigh the conviction.', category: 'Earnings Brief' },
  { term: 'Reaction Gap', short: 'Earnings-day price move from anchor: D-1 close → D-open (BMO) or D-close → D+1-open (AMC).', detail: 'BMO reporters (premarket): the gap is yesterday-close vs today-open. AMC reporters (postmarket): the gap is today-close vs tomorrow-open. The reaction_basis (BMO/AMC) flag determines which calculation runs.', category: 'Earnings Brief' },
  { term: 'Sustain 3d / 5d / 10d', short: 'How much of the reaction gap was held N trading days later.', detail: 'Anchored at the reaction_anchor_price (D close for BMO, D+1 open for AMC). Sustain_5d_pct = (close on D+5 − anchor) / anchor × 100. Positive = the move held; negative = it reversed. Used to compute direction_consistent_5d (whether sustain has the same sign as reaction_gap) and is_reversal_5d (sign-flip with magnitude ≥50% of original gap).', category: 'Earnings Brief' },
  { term: 'BMO / AMC', short: 'Before Market Open / After Market Close — when the report is released.', detail: 'BMO reporters publish 7-9 AM ET, before the bell. AMC reporters publish 4-6 PM ET, after the close. Determines which trading day captures the reaction. The brief\'s embed splits today\'s names by BMO/AMC so you scan the right bucket for the right session.', category: 'Earnings Brief' },
  { term: 'Earnings History (table)', short: 'Per-quarter EPS announcement records pulled from AlphaVantage EARNINGS endpoint.', detail: 'Schema: ticker, fiscal_date_ending, reported_date, reported_eps, estimated_eps, surprise_pct, report_time. Populated by fetch-earnings-history Cloud Run Job for every AV ∩ UW ticker. Source-of-truth for which quarters a ticker reported, and the EPS surprise for each.', category: 'Earnings Brief' },
  { term: 'Earnings Reactions (table)', short: 'Per-quarter post-earnings reaction profile computed from earnings_history × OHLCV.', detail: 'Schema includes: reaction_basis (BMO/AMC), reaction_gap_pct, sustain_3d/5d/10d_pct, direction_consistent_5d, is_reversal_5d, pre_earnings_drift_10d_pct. Populated by compute-earnings-reactions Cloud Run Job. Feeds the playability_score and archetype classification.', category: 'Earnings Brief' },
  { term: 'Trade Strategy by Archetype', short: 'Mapping from archetype tag to action tag rendered in the brief.', detail: 'bullish_trend → CALL (long calls or call debit spreads — defined risk on direction). bearish_trend → PUT (long puts or put debit spreads — but treat as low-conviction; backtest 44.6% hit rate). reversal_play → STRDL (long straddle — vol-only, the model can\'t reliably predict the reversal direction). mixed → STRDL (long straddle or iron butterfly — pure vol play). quiet → row filtered from brief.', category: 'Earnings Brief' },
  // Added 2026-05-14: confidence labels + two-track policy
  { term: 'Confidence Label', short: 'Plain-English label next to each Earnings row telling you how much to size the trade.', detail: 'One of: 🔥 HIGH (Q5, 58.9% backtest hit rate — size up), ✅ SOLID (Q4, 51.7% — standard sizing), 🟡 OK (Q3, 46.5% — small position only), ❓ WEAK (Q2, 42.9% — paper/watch only), 🚫 SKIP (Q1, 34.8% — below baseline; auto-dropped from the brief, never rendered). Replaces the academic Q1-Q5 quintile labels — same data, actionable wording. Calibrated against 21,592-prediction walk-forward backtest (scripts/backtest_playability.py, 2026-05-14).', category: 'Earnings Brief' },
  { term: 'Score Quintile', short: 'Internal Q1-Q5 bucket for the playability_score, surfaced to users as the Confidence Label.', detail: 'Boundaries calibrated against the 2026-05-14 backtest: Q1 (<15.7), Q2 (15.7-21.2), Q3 (21.2-28.2), Q4 (28.2-41.9), Q5 (≥41.9). Hit rates per quintile are monotonically increasing from 34.8% (Q1) to 58.9% (Q5), validating the score formula. See score_quintile() in lib/earnings_reactions.py.', category: 'Earnings Brief' },
  { term: 'Two-Track Brief Policy', short: 'The earnings brief splits names into Track A (Earnings) and Track B (High-Flow Watchlist) — mutually exclusive.', detail: 'Track A = nQ ≥ 12 reactions AND not Q1 (SKIP) — full archetype + action + confidence label rendered. Track B = nQ < 12 reactions AND high flow (OI ≥ 50k AND options_volume ≥ 5k) — flow stats only, no score/archetype (sample too small for confident classification). Tracks are mutually exclusive: a ticker is in exactly one bucket. Added 2026-05-14 so IPO-edge institutional names (CRCL, FIG, VG, Q) stop being silently dropped by the strict nQ filter.', category: 'Earnings Brief' },
  { term: 'High-Flow Watchlist (Track B)', short: 'Discord brief section showing IPO-edge tickers with huge institutional flow but limited history.', detail: 'Renders as "📊 High-Flow Watchlist" after the BMO/AMC sections. Rows show ticker + EM + OI + Vol + market cap + nQ count, no archetype/score (sample < 12Q is too small for reliable stats). Sorted by open_interest DESC. DYOR caveat shown. Catches names like CRCL ($30B mcap, 768k OI, only 5Q public) that would otherwise vanish from the brief under the strict nQ≥12 confidence floor. Thresholds: BRIEF_WATCHLIST_MIN_OI (default 50k), BRIEF_WATCHLIST_MIN_VOL (default 5k).', category: 'Earnings Brief' },
  { term: 'Pipeline Cadence (Earnings)', short: 'When each piece of earnings data refreshes.', detail: 'Sun 7:00 PM ET — full week setup (calendar + AV options for next Mon-Fri AV ∩ UW). Sun 7:15 PM — earnings_history for the week. Sun 7:30 PM — reactions. Sun 9:00 PM — weekly preview brief. Mon-Fri 7:00 PM — tomorrow\'s reporters get fresh AV options snapshot from today\'s close. 7:15 PM — today\'s reporters get history re-fetched (capture eps_actual). 7:30 PM — today\'s reactions recomputed. Mon-Fri 8:30 AM — brief posts to Discord.', category: 'Earnings Brief' },
  ];
}

export default function HelpPage() {
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  // Indicator config powers the periods/thresholds shown in the glossary.
  const { data: indicatorCfg } = useIndicatorConfig();
  const glossary = useMemo(() => buildGlossary(indicatorCfg), [indicatorCfg]);
  const categories = useMemo(() => [...new Set(glossary.map((g) => g.category))], [glossary]);

  const filtered = glossary.filter(g => {
    const matchesSearch = !search || g.term.toLowerCase().includes(search.toLowerCase()) || g.short.toLowerCase().includes(search.toLowerCase());
    const matchesCat = !activeCategory || g.category === activeCategory;
    return matchesSearch && matchesCat;
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-bold text-[var(--color-text-primary)]">Help & Glossary</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-1">
          Quick reference for every term, indicator, and metric used in the platform.
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search terms..."
          className="w-full rounded-xl bg-[var(--surface-2)] py-2 pl-9 pr-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent-blue)] focus:outline-none"
        />
      </div>

      {/* Category pills */}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setActiveCategory(null)}
          className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
            !activeCategory
              ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
              : 'border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
          }`}
        >
          All ({glossary.length})
        </button>
        {categories.map(cat => {
          const count = glossary.filter(g => g.category === cat).length;
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(activeCategory === cat ? null : cat)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                activeCategory === cat
                  ? 'bg-[var(--color-accent-blue)] text-[var(--on-brand)]'
                  : 'border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
              }`}
            >
              {cat} ({count})
            </button>
          );
        })}
      </div>

      {/* Glossary entries */}
      <div className="space-y-1">
        {filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--color-text-muted)]">No matching terms found.</p>
        ) : (
          filtered.map(entry => (
            <button
              key={entry.term}
              onClick={() => setExpanded(expanded === entry.term ? null : entry.term)}
              className="w-full text-left rounded-xl bg-[var(--surface-2)] px-4 py-3 transition-colors hover:bg-[var(--color-bg-tertiary)]"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--color-text-primary)]">{entry.term}</span>
                    <span className="shrink-0 rounded-full bg-[var(--color-bg-tertiary)] px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                      {entry.category}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-[var(--color-text-secondary)]">{entry.short}</p>
                </div>
                <span className="shrink-0 text-xs text-[var(--color-text-muted)] mt-1">
                  {expanded === entry.term ? '−' : '+'}
                </span>
              </div>
              {expanded === entry.term && entry.detail && (
                <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-muted)] border-t border-[var(--color-border)] pt-2">
                  {entry.detail}
                </p>
              )}
            </button>
          ))
        )}
      </div>
    </div>
  );
}
