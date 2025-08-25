/**
 * Diagnose the specific issue where strike 235 shows hit at 234.04
 */
function EW_diagnoseHitIssue() {
  console.log('=== DIAGNOSING HIT PRICE ISSUE ===');
  
  // Simulate the problematic case
  const strike = 235.00;
  const hitPrice = 234.04;
  
  // Calculate what percentage move this would be
  const pctMove = (hitPrice - strike) / strike;
  console.log(`\nProblem Case: Strike=${strike}, Hit=${hitPrice}`);
  console.log(`Percentage move: ${pctMove} (${(pctMove * 100).toFixed(2)}%)`);
  console.log(`This is NEGATIVE (-0.41%), which means price went DOWN!`);
  
  // For a Long Call/Bull strategy, this should NOT be a hit
  console.log(`\nFor Long Call/Bull strategies:`);
  console.log(`- Hit ONLY when price > strike`);
  console.log(`- ${hitPrice} < ${strike}, so this should NOT be marked as hit`);
  
  // Check what could cause this
  console.log(`\n=== POSSIBLE CAUSES ===`);
  
  console.log(`\n1. Strike_Hit array contains negative value:`);
  console.log(`   If Strike_Hit = [-0.004085], the calculation would be:`);
  console.log(`   hitPrice = ${strike} * (1 + (-0.004085)) = ${(strike * (1 + (-0.004085))).toFixed(2)}`);
  console.log(`   This matches ${hitPrice}!`);
  
  console.log(`\n2. The backfill process marked this as a hit incorrectly:`);
  console.log(`   - Maybe day high was ${hitPrice}, which is BELOW strike`);
  console.log(`   - But the code still marked it as 'hit' and stored the negative percentage`);
  
  console.log(`\n3. Wrong strategy type detection:`);
  console.log(`   - If this was actually a PUT/Bear strategy, ${hitPrice} < ${strike} would be correct`);
  console.log(`   - But the report shows these as bullish strategies`);
}

/**
 * Test the strike hit detection logic
 */
function EW_testStrikeHitDetection() {
  console.log('=== TESTING STRIKE HIT DETECTION ===');
  
  // Test case 1: Bullish strategy where high is below strike
  const strike1 = 235.00;
  const dayHigh1 = 234.04;
  const dayLow1 = 230.00;
  
  console.log(`\nTest 1: Long Call with dayHigh BELOW strike`);
  console.log(`Strike: ${strike1}, Day High: ${dayHigh1}, Day Low: ${dayLow1}`);
  
  // Check if this would be marked as hit
  const isBullish = true;
  const wouldHit = isBullish && dayHigh1 >= strike1;
  console.log(`Would be marked as hit: ${wouldHit}`);
  console.log(`Correct! This should NOT be a hit.`);
  
  // But if we calculate the percentage anyway
  const pctMove = ((dayHigh1 - strike1) / strike1).toFixed(6);
  console.log(`\nIf we stored the percentage anyway: ${pctMove}`);
  console.log(`This is negative: ${(parseFloat(pctMove) * 100).toFixed(2)}%`);
  
  // Test case 2: What the extreme percentages mean
  console.log(`\n\nTest 2: Understanding extreme percentages`);
  const testCases = [
    { strike: 172.50, maxProfit: 16.42, displayedAs: 1642 },
    { strike: 710.00, maxProfit: 11.54, displayedAs: 1154 },
    { strike: 235.00, maxProfit: 17.20, displayedAs: 1720 }
  ];
  
  testCases.forEach(test => {
    console.log(`\nStrike: ${test.strike}`);
    console.log(`If max favorable = ${test.maxProfit} (stored as percentage, not decimal)`);
    console.log(`Success Report shows: ${test.displayedAs}% (multiplied by 100 again)`);
    console.log(`Actual profit should be: ${test.maxProfit}%`);
    
    // Calculate what day high this implies
    const impliedHigh = test.strike * (1 + test.maxProfit / 100);
    console.log(`This implies day high of: ${impliedHigh.toFixed(2)}`);
  });
}

/**
 * Create a fix for the Strike_Hit array to filter out invalid hits
 */
function EW_createStrikeHitFix() {
  console.log('=== PROPOSED FIX FOR STRIKE HIT ARRAY ===');
  
  console.log(`
The issue is that Strike_Hit array is storing negative values when:
1. A bullish strategy has dayHigh < strike
2. A bearish strategy has dayLow > strike

These should NOT be marked as hits at all!

SOLUTION: Modify EW_buildStrikeHitArray to validate before storing:
`);

  console.log(`
if (strikeHit) {
  const strategyUpper = strategy.toUpperCase();
  const isBullish = strategyUpper.includes('BULL') || strategyUpper.includes('LONG CALL');
  const isBearish = strategyUpper.includes('BEAR') || strategyUpper.includes('LONG PUT');
  
  let percentMove = null;
  if (isBullish) {
    // For bullish: ONLY store if dayHigh > strike
    if (dayHigh > strike) {
      percentMove = ((dayHigh - strike) / strike).toFixed(6);
    } else {
      // This is NOT a hit - return null
      array[dayIndex] = null;
      return array;
    }
  } else if (isBearish) {
    // For bearish: ONLY store if dayLow < strike
    if (dayLow < strike) {
      percentMove = ((strike - dayLow) / strike).toFixed(6);
    } else {
      // This is NOT a hit - return null
      array[dayIndex] = null;
      return array;
    }
  }
  
  array[dayIndex] = percentMove;
}
`);
}