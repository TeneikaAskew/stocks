// /**
//  * Legacy Code and Commented Functions
//  * This file contains old implementations and commented-out code that was removed during refactoring
//  * for historical reference and potential future use.
//  * 
//  * Contents:
//  * 1. Original EW_appendToTab implementations
//  * 2. Commented header mapping functions
//  * 3. Original GOOGLEFINANCE formula setters
//  * 4. Legacy utility functions
//  */

// // ==================== HARDCODED VALUES THAT WERE REMOVED ====================

// /**
//  * In EW_runSingle function, there was a hardcoded line that was overriding the parameter:
//  * tabName = 'Bull Spreads'
//  * This was removed to allow the function to work with any strategy passed as parameter
//  */

// // ==================== COMMENTED OUT FORMULA IMPLEMENTATIONS ====================

// /**
//  * Original formula implementations that were commented out
//  * These used DROP/TAKE functions that may not be available in all Google Sheets environments
//  */

// // HV_30D formula with commented implementation
//   setHeaderArray(
//     hdrMap.hv30Col, 'HV_30D',
//     `LET(
//        d, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-60,TODAY()),),
//        n, ROWS(d),
//        IF(n<32,,LET(
//          p, TAKE(DROP(INDEX(d,0,2),1),-30),
//          r, MAP(SEQUENCE(29), LAMBDA(i, LN(INDEX(p,i+1)/INDEX(p,i)))),
//          st,   IFERROR(STDEV(r),),
//          IF(st="",,SQRT(252)*st*100)
//        ))
//      )`
//   );

//   // RVOL_10: live volume / 10-day avg volume
//   setHeaderArray(
//     hdrMap.rvol10Col, 'RVOL_10',
//     `LET(
//        cv, IFERROR(GOOGLEFINANCE(t,"volume"),),
//        vh, IFERROR(GOOGLEFINANCE(t,"volume",TODAY()-20,TODAY()),),
//        vd, IF(ROWS(vh)<2,,DROP(vh,1)),
//        av, IF(ROWS(vd)<10,,AVERAGE(TAKE(vd,-10))),
//        IF(OR(cv="",av=""),,cv/av)
//      )`
//   );

//   // Ret_5D: (last close / close 5 trading days ago - 1) * 100
//   setHeaderArray(
//     hdrMap.ret5Col, 'Ret_5D',
//     `LET(
//        d, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-15,TODAY()),),
//        c, IF(ROWS(d)<2,,DROP(INDEX(d,0,2),1)),
//        n, ROWS(c),
//        IF(n<6,,(INDEX(c,n)/INDEX(c,n-5)-1)*100)
//      )`
//   );

//   // Ret_20D: (last close / close 20 trading days ago - 1) * 100
//   setHeaderArray(
//     hdrMap.ret20Col, 'Ret_20D',
//     `LET(
//        d, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-35,TODAY()),),
//        c, IF(ROWS(d)<2,,DROP(INDEX(d,0,2),1)),
//        n, ROWS(c),
//        IF(n<21,,(INDEX(c,n)/INDEX(c,n-20)-1)*100)
//      )`
//   );

//   // GapPct: (price - open)/open * 100  (intraday gap check)
//   setHeaderArray(
//     hdrMap.gapPctCol, 'GapPct',
//     `LET(px, IFERROR(GOOGLEFINANCE(t,"price"),),
//          op, IFERROR(GOOGLEFINANCE(t,"priceopen"),),
//          IF(OR(px="",op=""),,(px-op)/op*100))`
//   );

//   EW_trace('GF', 'ARRAYFORMULAs set for all eval columns');
// }

// // ==================== REMOVED REDUNDANT FUNCTIONS ====================

// /**
//  * EW_fixCorruptedHeaders was removed because EW_completeSheetRepair handles everything:
//  * - Removes corrupted headers (#ERROR!, #REF!)
//  * - Removes all formula columns
//  * - Ensures Strategy column exists
//  * - Re-applies all formulas fresh
//  * 
//  * The complete repair function is more thorough and handles all cases.
//  */

// function EW_fixCorruptedHeaders() {
//   EW_trace('FIX', 'Fixing corrupted headers in all sheets', true);
//   const ss = SpreadsheetApp.getActive();
//   const endpoints = EW.STRATEGY_ENDPOINTS;
//   let sheetsFixed = 0;
//   
//   for (const tabName of Object.keys(endpoints)) {
//     const sheet = ss.getSheetByName(tabName);
//     if (!sheet || sheet.getLastRow() === 0) continue;
//     
//     try {
//       const lastCol = sheet.getLastColumn();
//       const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
//       let hasCorrupted = false;
//       
//       // Map expected columns to their positions
//       const expectedColumns = [...EW_GF_LABELS, ...EW_TRACKING_LABELS];
//       const columnMap = new Map();
//       let nextExpectedIndex = 0;
//       
//       // Find and fix corrupted headers
//       const fixedHeaders = headers.map((header, index) => {
//         if (header && header.toString().startsWith('#')) {
//           hasCorrupted = true;
//           // Try to determine what this column should be based on position
//           // Skip past already found columns
//           while (nextExpectedIndex < expectedColumns.length && 
//                  columnMap.has(expectedColumns[nextExpectedIndex])) {
//             nextExpectedIndex++;
//           }
//           
//           if (nextExpectedIndex < expectedColumns.length) {
//             const expectedColumn = expectedColumns[nextExpectedIndex];
//             columnMap.set(expectedColumn, index);
//             nextExpectedIndex++;
//             EW_trace('FIX', `${tabName}: Replacing ${header} with ${expectedColumn} at column ${index + 1}`);
//             return expectedColumn;
//           }
//         } else if (header) {
//           // Track which expected columns we've found
//           const headerLower = header.toString().toLowerCase();
//           for (const expected of expectedColumns) {
//             if (expected.toLowerCase() === headerLower) {
//               columnMap.set(expected, index);
//               break;
//             }
//           }
//         }
//         return header;
//       });
//       
//       if (hasCorrupted) {
//         // Update the header row
//         sheet.getRange(1, 1, 1, lastCol).setValues([fixedHeaders]);
//         
//         // Re-apply formulas with corrected headers
//         const hdrMap = EW_headerMap(fixedHeaders);
//         EW_setGFArrayFormulas(sheet, hdrMap);
//         
//         sheetsFixed++;
//         EW_trace('FIX', `Fixed corrupted headers in ${tabName}`);
//       }
//       
//     } catch (e) {
//       EW_trace('FIX', `Error fixing ${tabName}: ${e.message}`, true);
//     }
//   }
//   
//   const msg = sheetsFixed > 0 ? 
//     `Fixed corrupted headers in ${sheetsFixed} sheets` : 
//     'No corrupted headers found';
//   
//   EW_trace('FIX', msg, true);
//   EW_safeAlert('Header Fix Complete', msg);
// }

// // ==================== ORIGINAL EW_appendToTab IMPLEMENTATIONS ====================

// /**
//  * Original simple EW_appendToTab function (Version 1)
//  * Basic implementation without Run Date or GOOGLEFINANCE integration
//  */
// function EW_appendToTab_v1(ss, tabName, rows, writeHeaderIfEmpty) {
//   EW_trace('SHEET', `Append -> "${tabName}" rows=${rows.length}`);
//   let sheet = ss.getSheetByName(tabName);
//   if (!sheet) {
//     EW_trace('SHEET', `Creating sheet "${tabName}"`);
//     sheet = ss.insertSheet(tabName);
//   }
//   if (!rows || rows.length === 0) return;

//   const lastRow = sheet.getLastRow();
//   if (writeHeaderIfEmpty && lastRow === 0 && rows.length > 0) {
//     const header = rows[0];
//     if (Array.isArray(header) && header.every(c => typeof c === 'string')) {
//       sheet.getRange(1, 1, 1, header.length).setValues([header]);
//       EW_trace('SHEET', `Wrote header (${header.length} cols)`);
//       if (rows.length > 1) {
//         sheet.getRange(2, 1, rows.length - 1, header.length).setValues(rows.slice(1));
//         EW_trace('SHEET', `Wrote ${rows.length - 1} data rows`);
//       }
//       return;
//     }
//   }

//   const width = Math.max(...rows.map(r => r.length));
//   const start = sheet.getLastRow() + 1;
//   const padded = rows.map(r => {
//     const copy = r.slice();
//     if (copy.length < width) copy.push(...Array(width - copy.length).fill(''));
//     return copy;
//   });
//   sheet.getRange(start, 1, padded.length, width).setValues(padded);
//   EW_trace('SHEET', `Appended ${padded.length} rows at row ${start}`);
// }

// /**
//  * Enhanced EW_appendToTab function (Version 2)
//  * With Run Date integration and GOOGLEFINANCE preparation
//  */
// function EW_appendToTab_v2(ss, tabName, rows, writeHeaderIfEmpty) {
//   EW_trace('SHEET', `Append -> "${tabName}" rows=${rows.length}`);
//   let sheet = ss.getSheetByName(tabName);
//   if (!sheet) {
//     EW_trace('SHEET', `Creating sheet "${tabName}"`);
//     sheet = ss.insertSheet(tabName);
//   }
//   if (!rows || rows.length === 0) return;

//   // Split incoming rows
//   const incomingHeader = Array.isArray(rows[0]) ? rows[0].slice() : [];
//   const incomingData = rows.slice(1).map(r => r.slice());

//   const runDate = EW_getRunStamp(); // e.g., 2025-08-15

//   const lastRow = sheet.getLastRow();

//   // If the sheet is empty, we create a new header with Run Date + GF columns
//   if (writeHeaderIfEmpty && lastRow === 0) {
//     // Build header: prepend Run Date, then incoming header, then GF headers
//     const baseHeader = EW_ensureRunDateInHeader(incomingHeader);
//     const headerWithGF = EW_addGFHeaders(baseHeader);

//     // Build data rows: prepend run date; pad to header width (GF cols left blank, formulas will fill)
//     const width = headerWithGF.length;
//     const dataRows = incomingData.map(r => {
//       const row = [runDate, ...r];
//       if (row.length < width) row.push(...Array(width - row.length).fill(''));
//       return row;
//     });

//     sheet.getRange(1, 1, 1, headerWithGF.length).setValues([headerWithGF]);
//     EW_trace('SHEET', `Wrote header (${headerWithGF.length} cols)`);

//     if (dataRows.length) {
//       sheet.getRange(2, 1, dataRows.length, width).setValues(dataRows);
//       EW_trace('SHEET', `Wrote ${dataRows.length} data rows`);
//       // Fill GF formulas for the rows we just wrote
//       const hdrMap = EW_headerMap(headerWithGF);
//       EW_writeGFForRows(sheet, 2, dataRows.length, hdrMap);
//     }
//     return;
//   }

//   // Existing sheet: read current header from row 1
//   const sheetHeader = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
//   const hdrMap = EW_headerMap(sheetHeader);

//   // Ensure the sheet already has "Run Date" as first column (created on first run)
//   const hasRunDate = (hdrMap.runDateCol === 1); // we create it as first col initially
//   if (!hasRunDate) {
//     EW_trace('SHEET', `Warning: "Run Date" not found as first column. Appending anyway.`, true);
//   }

//   // Align incoming data to sheet header order:
//   //  - Prepend Run Date value
//   //  - Reorder/trim/extend cells to match the sheet header columns
//   const width = sheetHeader.length;
//   const aligned = incomingData.map(r => {
//     const mapFromIncoming = EW_headerMap(incomingHeader);
//     const dstRow = Array(width).fill('');
//     // Put Run Date in col 1 if header has it
//     if (hdrMap.runDateCol) dstRow[hdrMap.runDateCol - 1] = runDate;
//     // Copy matching columns by header name
//     for (const [name, idx] of Object.entries(mapFromIncoming.byName)) {
//       if (!hdrMap.byName[name]) continue;             // skip fields not present in sheet
//       const dstIdx1 = hdrMap.byName[name];            // 1-based
//       const srcIdx0 = idx - 1;                        // incoming is 1-based in map
//       dstRow[dstIdx1 - 1] = r[srcIdx0] != null ? r[srcIdx0] : '';
//     }
//     return dstRow;
//   });

//   if (!aligned.length) return;

//   // Append aligned rows
//   const start = sheet.getLastRow() + 1;
//   sheet.getRange(start, 1, aligned.length, width).setValues(aligned);
//   EW_trace('SHEET', `Appended ${aligned.length} rows at row ${start}`);

//   // Add GF formulas for the new rows (if GF headers exist and ticker column is found)
//   EW_writeGFForRows(sheet, start, aligned.length, hdrMap);
// }

// // ==================== LEGACY HEADER FUNCTIONS ====================

// /**
//  * Original EW_addGFHeaders function
//  * Added GOOGLEFINANCE columns to header array
//  */
// function EW_addGFHeaders_legacy(header) {
//   const gf = [
//     'GF_Name','GF_Price','GF_ChangePct','GF_High','GF_Low','GF_High52','GF_Low52',
//     'GF_Volume','GF_AvgVol10','GF_MktCap','GF_PE','GF_Beta',
//     'HV_30D','RVOL_10','Ret_5D','Ret_20D','GapPct'
//   ];
//   const existing = new Set(header.map(h => String(h).toLowerCase()));
//   const toAdd = gf.filter(h => !existing.has(h.toLowerCase()));
//   return header.concat(toAdd);
// }

// /**
//  * Original EW_headerMap function
//  * Created mapping of header names to column indices with specific GF column support
//  */
// function EW_headerMap_legacy(headerRow) {
//   const byName = {};
//   headerRow.forEach((h, i) => {
//     const key = String(h || '').trim().toLowerCase();
//     if (key) byName[key] = i + 1;
//   });
//   return {
//     byName,
//     runDateCol:  byName['run date'] || null,
//     tickerCol:   byName['ticker'] || null,

//     // Live GF columns
//     nameCol:     byName['gf_name']     || null,
//     priceCol:    byName['gf_price']    || null,
//     chgPctCol:   byName['gf_changepct']|| null,
//     highCol:     byName['gf_high']     || null,
//     lowCol:      byName['gf_low']      || null,
//     high52Col:   byName['gf_high52']   || null,
//     low52Col:    byName['gf_low52']    || null,
//     volCol:      byName['gf_volume']   || null,
//     avgVol10Col: byName['gf_avgvol10'] || null,
//     mcapCol:     byName['gf_mktcap']   || null,
//     peCol:       byName['gf_pe']       || null,
//     betaCol:     byName['gf_beta']     || null,

//     // Derived signal columns
//     hv30Col:     byName['hv_30d']      || null,
//     rvol10Col:   byName['rvol_10']     || null,
//     ret5Col:     byName['ret_5d']      || null,
//     ret20Col:    byName['ret_20d']     || null,
//     gapPctCol:   byName['gappct']      || null,

//     width:       headerRow.length
//   };
// }

// // ==================== LEGACY GOOGLEFINANCE FORMULA FUNCTIONS ====================

// /**
//  * Original EW_setGFArrayFormulas function
//  * Set up ARRAYFORMULA functions for GOOGLEFINANCE data in row 1
//  */
// function EW_setGFArrayFormulas_legacy(sheet, hdrMap) {
//   if (!hdrMap.tickerCol) {
//     EW_trace('GF', 'No "ticker" column found; skipping ARRAYFORMULAs');
//     return;
//   }
//   const tLtr   = EW_columnToLetter(hdrMap.tickerCol);
//   const tRange = `$${tLtr}2:$${tLtr}`; // open-ended down the sheet

//   function setHeaderArray(colIndex, headerLabel, innerExpr) {
//     if (!colIndex) return;
//     // Row 1 cell holds: {"Header"; MAP(TickerRange, LAMBDA(t, IF(t="",, innerExpr )))}
//     const cell = sheet.getRange(1, colIndex);
//     const formula = `={"${headerLabel}"; MAP(${tRange}, LAMBDA(t, IF(t="",,${innerExpr})))}`;
//     cell.setFormula(formula);
//   }

//   // ---- Live GOOGLEFINANCE attributes (fast) ----
//   setHeaderArray(hdrMap.nameCol,   'GF_Name',      `IFERROR(GOOGLEFINANCE(t,"name"),)`       );
//   setHeaderArray(hdrMap.priceCol,  'GF_Price',     `IFERROR(GOOGLEFINANCE(t,"price"),)`      );
//   setHeaderArray(hdrMap.chgPctCol, 'GF_ChangePct', `IFERROR(GOOGLEFINANCE(t,"changepct"),)`  );
//   setHeaderArray(hdrMap.highCol,   'GF_High',      `IFERROR(GOOGLEFINANCE(t,"high"),)`       );
//   setHeaderArray(hdrMap.lowCol,    'GF_Low',       `IFERROR(GOOGLEFINANCE(t,"low"),)`        );
//   setHeaderArray(hdrMap.high52Col, 'GF_High52',    `IFERROR(GOOGLEFINANCE(t,"high52"),)`     );
//   setHeaderArray(hdrMap.low52Col,  'GF_Low52',     `IFERROR(GOOGLEFINANCE(t,"low52"),)`      );
//   setHeaderArray(hdrMap.volCol,    'GF_Volume',    `IFERROR(GOOGLEFINANCE(t,"volume"),)`     );
//   setHeaderArray(hdrMap.mcapCol,   'GF_MktCap',    `IFERROR(GOOGLEFINANCE(t,"marketcap"),)`  );
//   setHeaderArray(hdrMap.peCol,     'GF_PE',        `IFERROR(GOOGLEFINANCE(t,"pe"),)`         );
//   setHeaderArray(hdrMap.betaCol,   'GF_Beta',      `IFERROR(GOOGLEFINANCE(t,"beta"),)`       );

//   // 10-day average volume (from historical data)
//   setHeaderArray(
//     hdrMap.avgVol10Col, 'GF_AvgVol10',
//     `LET(vh, IFERROR(GOOGLEFINANCE(t,"volume",TODAY()-20,TODAY()),),
//          vd, IF(ROWS(vh)<2,,DROP(vh,1)),
//          IF(ROWS(vd)<10,,AVERAGE(TAKE(vd,-10))))`
//   );

//   // ---- Derived signals using history ----

//   // HV_30D: 30-day close-to-close historical volatility (annualized %) 
//   // Uses LN returns, STDEV, and scales by sqrt(252)
//   setHeaderArray(
//     hdrMap.hv30Col, 'HV_30D',
//     `LET(
//        data, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-40,TODAY()),),
//        cl,   IF(ROWS(data)<3,,DROP(INDEX(data,0,2),1)),              /* closes (drop header row) */
//        c1,   IF(ROWS(cl)<31,,DROP(cl,1)),                            /* t1..n */
//        c0,   IF(ROWS(cl)<31,,TAKE(cl,ROWS(cl)-1)),                   /* t0..n-1 */
//        r,    IF(OR(c1="",c0=""),,LN(c1/c0)),
//        IF(ROWS(r)<30,,STDEV(TAKE(r,-30))*SQRT(252)*100))`
//   );

//   // RVOL_10: Relative volume (today vs 10-day avg)
//   setHeaderArray(
//     hdrMap.rvol10Col, 'RVOL_10',
//     `LET(
//        vh,   IFERROR(GOOGLEFINANCE(t,"volume",TODAY()-15,TODAY()),),
//        vd,   IF(ROWS(vh)<2,,DROP(vh,1)),
//        tVol, IF(ROWS(vd)<1,,INDEX(vd,ROWS(vd),1)),
//        a10,  IF(ROWS(vd)<10,,AVERAGE(TAKE(vd,-10))),
//        IF(OR(tVol="",a10="",a10=0),,tVol/a10))`
//   );

//   // Ret_5D: 5-day return percentage
//   setHeaderArray(
//     hdrMap.ret5Col, 'Ret_5D',
//     `LET(
//        data, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-10,TODAY()),),
//        cl,   IF(ROWS(data)<2,,DROP(INDEX(data,0,2),1)),
//        now,  IF(ROWS(cl)<1,,INDEX(cl,ROWS(cl),1)),
//        d5,   IF(ROWS(cl)<6,,INDEX(cl,ROWS(cl)-5,1)),
//        IF(OR(now="",d5="",d5=0),,(now/d5-1)*100))`
//   );

//   // Ret_20D: 20-day return percentage
//   setHeaderArray(
//     hdrMap.ret20Col, 'Ret_20D',
//     `LET(
//        data, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-25,TODAY()),),
//        cl,   IF(ROWS(data)<2,,DROP(INDEX(data,0,2),1)),
//        now,  IF(ROWS(cl)<1,,INDEX(cl,ROWS(cl),1)),
//        d20,  IF(ROWS(cl)<21,,INDEX(cl,1,1)),
//        IF(OR(now="",d20="",d20=0),,(now/d20-1)*100))`
//   );

//   // GapPct: Today's gap % (high vs yesterday close)
//   setHeaderArray(
//     hdrMap.gapPctCol, 'GapPct',
//     `LET(
//        data, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-5,TODAY()),),
//        cl,   IF(ROWS(data)<3,,DROP(INDEX(data,0,2),1)),
//        yC,   IF(ROWS(cl)<2,,INDEX(cl,ROWS(cl)-1,1)),
//        tH,   IFERROR(GOOGLEFINANCE(t,"high"),),
//        IF(OR(tH="",yC="",yC=0),,(tH/yC-1)*100))`
//   );

//   EW_trace('GF', 'ARRAYFORMULA setup complete for all columns');
// }

// // ==================== NOTES ====================

// /**
//  * Historical Context:
//  * 
//  * These functions were part of the original EarningsWhispers implementation before
//  * the modular refactoring. They are preserved here for:
//  * 
//  * 1. Historical reference
//  * 2. Understanding evolution of the codebase
//  * 3. Potential rollback scenarios
//  * 4. Learning from past implementations
//  * 
//  * The current implementation uses:
//  * - Simplified and more robust EW_appendToTab function
//  * - Modular header management
//  * - Enhanced ARRAYFORMULA setup with better error handling
//  * - Improved performance and reliability
//  * 
//  * These legacy functions should not be called in production.
//  */
