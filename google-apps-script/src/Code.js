/**
 * EarningsWhispers OptionTrades — Apps Script (sheet-bound, verbose)
 * - Fetches JSON from /api/get* endpoints for each strategy
 * - Normalizes JSON -> header row + data rows
 * - Appends to tabs named after strategies (creates if missing)
 * - Logs to console, Logger, and a "Log" sheet
 * - Optional login (set Script Properties: EW_USER, EW_PASS) if API needs session
 * https://hackernoon.com/writing-google-apps-script-code-locally-in-vscode
 * 
 * Dependencies:
 * - GlobalVars.js: Configuration constants and global variables
 * - HelperFunctions.js: Utility functions and helpers
 */

// ======= EXPOSE HELPER FUNCTIONS ON EW OBJECT =======
// Make URL helper available on EW object for backwards compatibility
EW.url = EW_url;

// ======= UI MENU =======
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('EarningsWhispers')
    .addItem('Run all strategies', 'EW_runAll')
    .addItem('Debug one (prompt)', 'EW_debugOne')
    .addSeparator()
    .addItem('Generate Success Report', 'EW_generateSuccessReport')
    .addItem('Update Tracking Data', 'EW_updateTrackingData')
    .addSeparator()
    .addSubMenu(SpreadsheetApp.getUi().createMenu('Automation & Triggers')
      .addItem('Setup Full Auto Tracking', 'EW_setupAutoTracking')
      .addItem('Setup Daily Data Fetch (8AM)', 'EW_setupDailyDataTrigger')
      .addItem('Setup Missing Triggers Only', 'EW_setupTriggersIfMissing')
      .addSeparator()
      .addItem('Stop All Auto Tracking', 'EW_stopAutoTracking')
      .addItem('Stop Daily Data Fetch', 'EW_stopDailyDataTrigger')
      .addSeparator()
      .addItem('List Active Triggers', 'EW_listActiveTriggers')
      .addItem('Validate Triggers', 'EW_validateTriggers')
      .addItem('Verify & Repair Triggers', 'EW_verifyAndRepairTriggers')
      .addSeparator()
      .addItem('Test Environment Detection', 'EW_testEnvironmentDetection')
    )
    .addToUi();
    
  // Auto-create success report on first run
  EW_ensureSuccessReportExists();
}

// Prompt to run a single tab quickly
function EW_debugOne() {
  const ui = SpreadsheetApp.getUi();
  const names = Object.keys(EW.STRATEGY_ENDPOINTS);
  const res = ui.prompt(
    'Debug one strategy',
    `Type one of:\n${names.join(', ')}`,
    ui.ButtonSet.OK_CANCEL
  );
  if (res.getSelectedButton() !== ui.Button.OK) return;
  const name = res.getResponseText().trim();
  if (!EW.STRATEGY_ENDPOINTS[name]) {
    ui.alert(`Unknown strategy: "${name}"`);
    return;
  }
  EW_runSingle(name);
}

// ======= Entry points =======
function EW_runAll() {
  EW_trace('MAIN', 'EW_runAll() started', true);

  let cookies = {};
  if (EW.p.user && EW.p.pass) {
    try {
      EW_trace('LOGIN', `Attempting login as ${EW.p.user}`);
      cookies = EW_login();
      EW_trace('LOGIN', `Login complete; cookies=${Object.keys(cookies).length}`);
      Utilities.sleep(600);
    } catch (e) {
      EW_trace('LOGIN', `Login failed: ${e && e.message ? e.message : e}`, true);
    }
  } else {
    EW_trace('LOGIN', 'No EW_USER/EW_PASS set; skipping login');
  }

  const ss = SpreadsheetApp.getActive();
  const endpoints = EW.STRATEGY_ENDPOINTS;
  EW_trace('MAIN', `Fetching ${Object.keys(endpoints).length} endpoints`);

  for (const [tabName, path] of Object.entries(endpoints)) {
    EW_runOneInternal(ss, tabName, path, cookies);
  }

  EW_trace('MAIN', 'EW_runAll() finished', true);
}

// run a single strategy programmatically
function EW_runSingle(tabName) {
  tabName = 'Bull Spreads'
  EW_trace('MAIN', `EW_runSingle(${tabName})`);
  const path = EW.STRATEGY_ENDPOINTS[tabName];
  if (!path) {
    EW_trace('MAIN', `Unknown tabName: ${tabName}`, true);
    return;
  }
  let cookies = {};
  if (EW.p.user && EW.p.pass) {
    try { cookies = EW_login(); } catch (e) {}
  }
  const ss = SpreadsheetApp.getActive();
  EW_runOneInternal(ss, tabName, path, cookies);
  EW_trace('MAIN', `EW_runSingle(${tabName}) done`, true);
}

// core per-endpoint work
function EW_runOneInternal(ss, tabName, path, cookies) {
  try {
    const url = EW.url(path);
    EW_trace(tabName, `GET ${url}`);
    const json = EW_fetchJson(url, cookies);
    EW_trace(tabName, `HTTP OK; JSON=${EW_summarizeJson(json)}`);
    const rows = EW_jsonToRows(json);
    EW_trace(tabName, `Parsed rows=${rows ? rows.length : 0}`);

    if (!rows || rows.length === 0) {
      EW_trace(tabName, 'Empty table or parse failure', true);
      return;
    }

    const before = ss.getSheetByName(tabName)?.getLastRow() || 0;
    EW_appendToTab(ss, tabName, rows, true);
    const after = ss.getSheetByName(tabName)?.getLastRow() || 0;
    EW_trace(tabName, `Wrote to sheet "${tabName}": +${Math.max(0, after - before)} rows`, true);

    Utilities.sleep(300);
  } catch (err) {
    const msg = (err && err.stack) ? err.stack : (err && err.message ? err.message : String(err));
    EW_trace(tabName, `ERROR: ${msg}`, true);
  }
}

// ======= HTTP & Auth =======
function EW_fetchJson(url, cookiesObj) {
  const headers = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'x-requested-with': 'XMLHttpRequest',
    'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)',
    'Referer': EW.MATRIX_REFERRER
  };
  if (cookiesObj && Object.keys(cookiesObj).length) {
    headers['Cookie'] = EW_cookieHeader(cookiesObj);
  }

  EW_trace('HTTP', `Fetching ${url}`);
  const res = UrlFetchApp.fetch(url, {
    method: 'get',
    headers,
    muteHttpExceptions: true,
    followRedirects: true
  });

  const code = res.getResponseCode();
  EW_trace('HTTP', `Response ${code} for ${url}`);
  if (code >= 400) {
    const snippet = (res.getContentText() || '').slice(0, 300).replace(/\s+/g, ' ');
    throw new Error(`HTTP ${code} for ${url}; body[0..300]: ${snippet}`);
  }

  const text = res.getContentText();
  console.log("Response: \n", text)
  try {
    const parsed = JSON.parse(text);
    return parsed;
  } catch (e) {
    EW_trace('HTTP', `JSON parse error for ${url}: ${(e && e.message) || e}`);
    throw new Error(`JSON parse error for ${url}: ${e.message || e}`);
  }
}

function EW_login() {
  const { user, pass, loginUrl } = EW.p;
  if (!user || !pass) {
    EW_trace('LOGIN', 'No credentials provided; returning empty cookies');
    return {};
  }

  EW_trace('LOGIN', `GET ${loginUrl}`);
  const res1 = UrlFetchApp.fetch(loginUrl, {
    method: 'get',
    muteHttpExceptions: true,
    followRedirects: false,
    headers: {
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)'
    }
  });
  const c1 = EW_collectSetCookies(res1);
  EW_trace('LOGIN', `res1 code=${res1.getResponseCode()} cookies=${Object.keys(c1).length}`);

  const html = res1.getContentText() || '';
  const csrf = EW_extractCsrf(html);
  if (csrf) EW_trace('LOGIN', `Found CSRF token`);

  const payload = { Email: user, Password: pass };
  if (csrf) payload['__RequestVerificationToken'] = csrf;

  EW_trace('LOGIN', `POST ${loginUrl}`);
  const res2 = UrlFetchApp.fetch(loginUrl, {
    method: 'post',
    payload,
    muteHttpExceptions: true,
    followRedirects: false,
    headers: {
      'Cookie': EW_cookieHeader(c1),
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)',
      'Origin': EW.BASE,
      'Referer': loginUrl
    }
  });
  let cookies = EW_mergeCookies(c1, EW_collectSetCookies(res2));
  EW_trace('LOGIN', `res2 code=${res2.getResponseCode()} cookies now=${Object.keys(cookies).length}`);

  if (res2.getResponseCode() >= 300 && res2.getResponseCode() < 400) {
    const loc = res2.getHeaders()['Location'];
    EW_trace('LOGIN', `Redirect -> ${loc || '(none)'}`);
    if (loc) {
      const res3 = UrlFetchApp.fetch(loc, {
        method: 'get',
        muteHttpExceptions: true,
        followRedirects: true,
        headers: {
          'Cookie': EW_cookieHeader(cookies),
          'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)'
        }
      });
      cookies = EW_mergeCookies(cookies, EW_collectSetCookies(res3));
      EW_trace('LOGIN', `res3 code=${res3.getResponseCode()} cookies now=${Object.keys(cookies).length}`);
    }
  }

  return cookies;
}

// ======= JSON -> rows =======
function EW_jsonToRows(data) {
  if (!data) return [];

  if (Array.isArray(data)) {
    EW_trace('PARSE', `Array detected len=${data.length}`);
    return EW_objectsToRows(data);
  }
  if (data && Array.isArray(data.data)) {
    EW_trace('PARSE', `Object with data[] len=${data.data.length}`);
    return EW_objectsToRows(data.data);
  }
  if (data && Array.isArray(data.rows) && Array.isArray(data.headers)) {
    EW_trace('PARSE', `Already {headers,rows} with rows=${data.rows.length}`);
    return [data.headers, ...data.rows];
  }

  if (typeof data === 'object') {
    EW_trace('PARSE', 'Single object -> one row');
    return EW_objectsToRows([data]);
  }

  EW_trace('PARSE', 'Unknown shape -> empty');
  return [];
}

function EW_objectsToRows(arr) {
  if (!arr || arr.length === 0) return [];
  const preferred = [
    'company','ticker','strategy','earningsDate','earningsTime','price',
    'strike','expiration','delta','iv','rvol','rsi','atr','premium','maxProfit',
    'breakeven','probITM','probOTM','notes','date','time'
  ];
  const keySet = new Set(preferred);
  arr.forEach(obj => {
    Object.keys(obj || {}).forEach(k => { if (!keySet.has(k)) keySet.add(k); });
  });
  const headers = Array.from(keySet).filter(k =>
    arr.some(o => Object.prototype.hasOwnProperty.call(o || {}, k))
  );

  const rows = arr.map(o => headers.map(h => {
    const v = (o && o[h] != null) ? o[h] : '';
    return (typeof v === 'object') ? JSON.stringify(v) : String(v);
  }));

  EW_trace('PARSE', `headers=${headers.length} dataRows=${rows.length}`);
  return [headers, ...rows];
}

// ======= Sheets helpers =======
// function EW_appendToTab(ss, tabName, rows, writeHeaderIfEmpty) {
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

// ======= Sheets helpers (with Run Date + GOOGLEFINANCE) =======
// function EW_appendToTab(ss, tabName, rows, writeHeaderIfEmpty) {
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

function EW_appendToTab(ss, tabName, rows, writeHeaderIfEmpty) {
  EW_trace('SHEET', `Append -> "${tabName}" rows=${rows.length}`);
  let sheet = ss.getSheetByName(tabName);
  if (!sheet) {
    EW_trace('SHEET', `Creating sheet "${tabName}"`);
    sheet = ss.insertSheet(tabName);
  }
  if (!rows || rows.length === 0) return;

  const incomingHeader = Array.isArray(rows[0]) ? rows[0].slice() : [];
  const incomingData = rows.slice(1).map(r => r.slice());
  const runDate = EW_getRunStamp();

  const lastRow = sheet.getLastRow();

  // First run on this tab
  if (writeHeaderIfEmpty && lastRow === 0) {
    const baseHeader   = EW_ensureRunDateInHeader(incomingHeader);
    const headerWithGF = EW_addGFHeaders(baseHeader);

    const width = headerWithGF.length;
    const dataRows = incomingData.map(r => {
      const row = [runDate, ...r];
      if (row.length < width) row.push(...Array(width - row.length).fill(''));
      return row;
    });

    sheet.getRange(1, 1, 1, width).setValues([headerWithGF]);
    EW_trace('SHEET', `Wrote header (${width} cols)`);

    if (dataRows.length) {
      sheet.getRange(2, 1, dataRows.length, width).setValues(dataRows);
      EW_trace('SHEET', `Wrote ${dataRows.length} data rows`);
    }

    // Plant ARRAYFORMULAs once
    const hdrMap = EW_headerMap(headerWithGF);
    EW_setGFArrayFormulas(sheet, hdrMap);
    return;
  }



  // Subsequent runs: align to existing header
  const sheetHeader = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(sheetHeader);
  const width = sheetHeader.length;

  const mapFromIncoming = EW_headerMap(incomingHeader);
  const aligned = incomingData.map(src => {
    const dst = Array(width).fill('');
    if (hdrMap.runDateCol) dst[hdrMap.runDateCol - 1] = runDate;
    for (const [name, src1] of Object.entries(mapFromIncoming.byName)) {
      const dst1 = hdrMap.byName[name];
      if (!dst1) continue;
      dst[dst1 - 1] = src[src1 - 1] != null ? src[src1 - 1] : '';
    }
    return dst;
  });

  if (!aligned.length) return;

    // If any GF header exists but row 1 cell is empty (formula removed), replant
  if (hdrMap.tickerCol && (
      (hdrMap.priceCol && !sheet.getRange(1, hdrMap.priceCol).getFormula()) ||
      (hdrMap.volCol   && !sheet.getRange(1, hdrMap.volCol).getFormula())
    )) {
    EW_trace('GF', 'Detected missing GF formulas; replanting');
    EW_setGFArrayFormulas(sheet, hdrMap);
  }


  const start = sheet.getLastRow() + 1;
  sheet.getRange(start, 1, aligned.length, width).setValues(aligned);
  EW_trace('SHEET', `Appended ${aligned.length} rows at row ${start}`);

  // Do NOT call any filler here; array formulas spill automatically.
}




// ======= Cookie & CSRF =======
// Add a rich set of eval columns for options decisioning
// function EW_addGFHeaders(header) {
//   const gf = [
//     'GF_Name','GF_Price','GF_ChangePct','GF_High','GF_Low','GF_High52','GF_Low52',
//     'GF_Volume','GF_AvgVol10','GF_MktCap','GF_PE','GF_Beta',
//     'HV_30D','RVOL_10','Ret_5D','Ret_20D','GapPct'
//   ];
//   const existing = new Set(header.map(h => String(h).toLowerCase()));
//   const toAdd = gf.filter(h => !existing.has(h.toLowerCase()));
//   return header.concat(toAdd);
// }

// Map header names to 1-based indices + friendly handles
// function EW_headerMap(headerRow) {
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

// Add our evaluation columns (exact labels used everywhere below)
const EW_GF_LABELS = [
  'GF_Name','GF_Price','GF_ChangePct','GF_High','GF_Low','GF_High52','GF_Low52',
  'GF_Volume','GF_AvgVol10','GF_MktCap','GF_PE','GF_Beta',
  'HV_30D','RVOL_10','Ret_5D','Ret_20D','GapPct'
];

// Add tracking columns for strategy success monitoring
const EW_TRACKING_LABELS = [
  'Days_To_Exp','Strike_Hit','Hit_Date','Max_Favorable','Min_Unfavorable',
  'Day1_Check','Day2_Check','Day3_Check','Day5_Check','Exp_Result',
  'Success_Score','Profit_Potential','Risk_Reward','Historical_High','Historical_Low',
  'Ever_Hit_Strike','First_Hit_Date','Last_Update','Total_Hit_Days','Peak_Profit_Date'
];

function EW_headerMap(headerRow) {
  const byName = {};               // raw key -> 1-based index
  const byNorm = {};               // normalized key -> 1-based index
  headerRow.forEach((h, i) => {
    const raw  = String(h || '').trim();
    const norm = EW_norm(raw);
    if (raw)  byName[raw.toLowerCase()] = i + 1;
    if (norm) byNorm[norm] = i + 1;
  });

  // Helper: first match among aliases (by normalized name)
  function find(aliases) {
    for (const a of aliases) {
      const ix = byNorm[EW_norm(a)];
      if (ix) return ix;
    }
    return null;
  }

  // Common aliases for upstream data
  const tickerCol   = find(['ticker','symbol','sym','underlying','root']);
  const runDateCol  = find(['run date','rundate','dateadded']);
  // (add more if needed: expiration/strike/etc for dedupe later)

  // GF/derived columns we ourselves add — locate by exact labels or normalized
  const nameCol     = find(['GF_Name']);
  const priceCol    = find(['GF_Price']);
  const chgPctCol   = find(['GF_ChangePct']);
  const highCol     = find(['GF_High']);
  const lowCol      = find(['GF_Low']);
  const high52Col   = find(['GF_High52','GF_52w High']);
  const low52Col    = find(['GF_Low52','GF_52w Low']);
  const volCol      = find(['GF_Volume']);
  const avgVol10Col = find(['GF_AvgVol10','GF_Avg Vol 10']);
  const mcapCol     = find(['GF_MktCap','GF_Market Cap']);
  const peCol       = find(['GF_PE']);
  const betaCol     = find(['GF_Beta']);

  const hv30Col     = find(['HV_30D']);
  const rvol10Col   = find(['RVOL_10']);
  const ret5Col     = find(['Ret_5D']);
  const ret20Col    = find(['Ret_20D']);
  const gapPctCol   = find(['GapPct','Gap %']);

  // Tracking columns
  const daysToExpCol    = find(['Days_To_Exp']);
  const strikeHitCol    = find(['Strike_Hit']);
  const hitDateCol      = find(['Hit_Date']);
  const maxFavorableCol = find(['Max_Favorable']);
  const minUnfavorableCol = find(['Min_Unfavorable']);
  const day1CheckCol    = find(['Day1_Check']);
  const day2CheckCol    = find(['Day2_Check']);
  const day3CheckCol    = find(['Day3_Check']);
  const day5CheckCol    = find(['Day5_Check']);
  const expResultCol    = find(['Exp_Result']);
  const successScoreCol = find(['Success_Score']);
  const profitPotentialCol = find(['Profit_Potential']);
  const riskRewardCol   = find(['Risk_Reward']);
  
  // Enhanced historical tracking columns
  const historicalHighCol = find(['Historical_High']);
  const historicalLowCol  = find(['Historical_Low']);
  const everHitStrikeCol  = find(['Ever_Hit_Strike']);
  const firstHitDateCol   = find(['First_Hit_Date']);
  const lastUpdateCol     = find(['Last_Update']);
  const totalHitDaysCol   = find(['Total_Hit_Days']);
  const peakProfitDateCol = find(['Peak_Profit_Date']);

  // Strategy and core data columns
  const strategyCol     = find(['strategy','Strategy']);
  const strikeCol       = find(['strike','Strike']);
  const expDateCol      = find(['expDate','expiration','Expiration']);

  return {
    byName, byNorm,
    runDateCol, tickerCol, strategyCol, strikeCol, expDateCol,
    nameCol, priceCol, chgPctCol, highCol, lowCol, high52Col, low52Col,
    volCol, avgVol10Col, mcapCol, peCol, betaCol,
    hv30Col, rvol10Col, ret5Col, ret20Col, gapPctCol,
    daysToExpCol, strikeHitCol, hitDateCol, maxFavorableCol, minUnfavorableCol,
    day1CheckCol, day2CheckCol, day3CheckCol, day5CheckCol, expResultCol,
    successScoreCol, profitPotentialCol, riskRewardCol,
    historicalHighCol, historicalLowCol, everHitStrikeCol, firstHitDateCol,
    lastUpdateCol, totalHitDaysCol, peakProfitDateCol,
    width: headerRow.length
  };
}



// Put ARRAYFORMULAs in row 1 so they spill down forever
// function EW_setGFArrayFormulas(sheet, hdrMap) {
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
//        st,   IFERROR(STDEV(r),),
//        IF(st="",,SQRT(252)*st*100)
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

function EW_setGFArrayFormulas(sheet, hdrMap) {
  if (!hdrMap.tickerCol) {
    EW_trace('GF', 'No "ticker" column found; skipping ARRAYFORMULAs');
    return;
  }
  const tLtr   = EW_columnToLetter(hdrMap.tickerCol);
  const tRange = `$${tLtr}2:$${tLtr}`;

  function setHeaderArray(colIndex, headerLabel, innerExpr) {
    if (!colIndex) return;
    const cell = sheet.getRange(1, colIndex);
    cell.setFormula(`={"${headerLabel}"; MAP(${tRange}, LAMBDA(t, IF(t="",,${innerExpr})))}`);
  }

  // GOOGLEFINANCE attributes
  setHeaderArray(hdrMap.nameCol,   'GF_Name',      `IFERROR(GOOGLEFINANCE(t,"name"),)`);
  setHeaderArray(hdrMap.priceCol,  'GF_Price',     `IFERROR(GOOGLEFINANCE(t,"price"),)`);
  setHeaderArray(hdrMap.chgPctCol, 'GF_ChangePct', `IFERROR(GOOGLEFINANCE(t,"changepct"),)`);
  setHeaderArray(hdrMap.highCol,   'GF_High',      `IFERROR(GOOGLEFINANCE(t,"high"),)`);
  setHeaderArray(hdrMap.lowCol,    'GF_Low',       `IFERROR(GOOGLEFINANCE(t,"low"),)`);
  setHeaderArray(hdrMap.high52Col, 'GF_High52',    `IFERROR(GOOGLEFINANCE(t,"high52"),)`);
  setHeaderArray(hdrMap.low52Col,  'GF_Low52',     `IFERROR(GOOGLEFINANCE(t,"low52"),)`);
  setHeaderArray(hdrMap.volCol,    'GF_Volume',    `IFERROR(GOOGLEFINANCE(t,"volume"),)`);
  setHeaderArray(hdrMap.mcapCol,   'GF_MktCap',    `IFERROR(GOOGLEFINANCE(t,"marketcap"),)`);
  setHeaderArray(hdrMap.peCol,     'GF_PE',        `IFERROR(GOOGLEFINANCE(t,"pe"),)`);
  setHeaderArray(hdrMap.betaCol,   'GF_Beta',      `IFERROR(GOOGLEFINANCE(t,"beta"),)`);

  // 10-day average volume
  setHeaderArray(
    hdrMap.avgVol10Col, 'GF_AvgVol10',
    `LET(
       vh, IFERROR(GOOGLEFINANCE(t,"volume",TODAY()-30,TODAY()),),
       n, ROWS(vh)-1,
       IF(n<10,,AVERAGE(INDEX(vh,SEQUENCE(10,1,n-8),2)))
     )`
  );

  // HV_30D (annualized, %)
  setHeaderArray(
    hdrMap.hv30Col, 'HV_30D',
    `LET(
       data, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-60,TODAY()),),
       n, ROWS(data),
       IF(n<32,,LET(
         returns, MAP(SEQUENCE(30), LAMBDA(i, LN(INDEX(data,n-i+1,2)/INDEX(data,n-i,2)))),
         SQRT(252)*STDEV(returns)*100
       ))
     )`
  );

  // RVOL_10 (current vol / 10-day avg vol)
  setHeaderArray(
    hdrMap.rvol10Col, 'RVOL_10',
    `LET(
       cv, IFERROR(GOOGLEFINANCE(t,"volume"),),
       vh, IFERROR(GOOGLEFINANCE(t,"volume",TODAY()-30,TODAY()),),
       n, ROWS(vh)-1,
       av, IF(n<10,,AVERAGE(INDEX(vh,SEQUENCE(10,1,n-8),2))),
       IF(OR(cv="",av=""),,cv/av)
     )`
  );

  // Ret_5D
  setHeaderArray(
    hdrMap.ret5Col, 'Ret_5D',
    `LET(
       d, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-20,TODAY()),),
       n, ROWS(d),
       IF(n<7,,(INDEX(d,n,2)/INDEX(d,n-5,2)-1)*100)
     )`
  );

  // Ret_20D
  setHeaderArray(
    hdrMap.ret20Col, 'Ret_20D',
    `LET(
       d, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-45,TODAY()),),
       n, ROWS(d),
       IF(n<22,,(INDEX(d,n,2)/INDEX(d,n-20,2)-1)*100)
     )`
  );

  // GapPct unchanged
  setHeaderArray(
    hdrMap.gapPctCol, 'GapPct',
    `LET(px, IFERROR(GOOGLEFINANCE(t,"price"),),
         op, IFERROR(GOOGLEFINANCE(t,"priceopen"),),
         IF(OR(px="",op=""),,(px-op)/op*100))`
  );

  // ===== ENHANCED HISTORICAL TRACKING FORMULAS =====
  
  // Historical High (never resets - captures peak favorable price)
  setHeaderArray(
    hdrMap.historicalHighCol, 'Historical_High',
    `LET(
       currentPrice, IFERROR(GOOGLEFINANCE(t,"price"),),
       prevHigh, INDEX($${EW_columnToLetter(hdrMap.historicalHighCol)}2:$${EW_columnToLetter(hdrMap.historicalHighCol)}, ROW(${tRange})-1),
       IF(currentPrice="", prevHigh, MAX(IF(prevHigh="", currentPrice, prevHigh), currentPrice))
     )`
  );

  // Historical Low (never resets - captures worst unfavorable price)
  setHeaderArray(
    hdrMap.historicalLowCol, 'Historical_Low',
    `LET(
       currentPrice, IFERROR(GOOGLEFINANCE(t,"price"),),
       prevLow, INDEX($${EW_columnToLetter(hdrMap.historicalLowCol)}2:$${EW_columnToLetter(hdrMap.historicalLowCol)}, ROW(${tRange})-1),
       IF(currentPrice="", prevLow, MIN(IF(prevLow="", currentPrice, prevLow), currentPrice))
     )`
  );

  // Ever Hit Strike (permanent flag - once hit, stays TRUE)
  setHeaderArray(
    hdrMap.everHitStrikeCol, 'Ever_Hit_Strike',
    `LET(
       stratCol, $${EW_columnToLetter(hdrMap.strategyCol)}2:$${EW_columnToLetter(hdrMap.strategyCol)},
       strikeCol, $${EW_columnToLetter(hdrMap.strikeCol)}2:$${EW_columnToLetter(hdrMap.strikeCol)},
       rowNum, ROW(${tRange})-1,
       strategy, UPPER(INDEX(stratCol, rowNum)),
       strike, INDEX(strikeCol, rowNum),
       currentPrice, IFERROR(GOOGLEFINANCE(t,"price"),),
       historicalHigh, INDEX($${EW_columnToLetter(hdrMap.historicalHighCol)}2:$${EW_columnToLetter(hdrMap.historicalHighCol)}, rowNum),
       historicalLow, INDEX($${EW_columnToLetter(hdrMap.historicalLowCol)}2:$${EW_columnToLetter(hdrMap.historicalLowCol)}, rowNum),
       prevEverHit, INDEX($${EW_columnToLetter(hdrMap.everHitStrikeCol)}2:$${EW_columnToLetter(hdrMap.everHitStrikeCol)}, rowNum),
       
       IF(OR(strategy="", strike="", currentPrice=""), prevEverHit,
         IF(prevEverHit="TRUE", "TRUE",
           IF(OR(ISNUMBER(SEARCH("LONG CALL", strategy)), ISNUMBER(SEARCH("BULL", strategy))),
             IF(historicalHigh >= strike, "TRUE", "FALSE"),
             IF(OR(ISNUMBER(SEARCH("LONG PUT", strategy)), ISNUMBER(SEARCH("BEAR", strategy))),
               IF(historicalLow <= strike, "TRUE", "FALSE"),
               IF(OR(ISNUMBER(SEARCH("SHORT CALL", strategy)), ISNUMBER(SEARCH("COVERED", strategy))),
                 IF(historicalHigh < strike, "FAVORABLE", "UNFAVORABLE"),
                 IF(ISNUMBER(SEARCH("SHORT PUT", strategy)),
                   IF(historicalLow > strike, "FAVORABLE", "UNFAVORABLE"),
                   "UNKNOWN"
                 )
               )
             )
           )
         )
       )
     )`
  );

  // First Hit Date (permanent - never changes once set)
  setHeaderArray(
    hdrMap.firstHitDateCol, 'First_Hit_Date',
    `LET(
       everHit, INDEX($${EW_columnToLetter(hdrMap.everHitStrikeCol)}2:$${EW_columnToLetter(hdrMap.everHitStrikeCol)}, ROW(${tRange})-1),
       prevFirstHit, INDEX($${EW_columnToLetter(hdrMap.firstHitDateCol)}2:$${EW_columnToLetter(hdrMap.firstHitDateCol)}, ROW(${tRange})-1),
       
       IF(AND(OR(everHit="TRUE", everHit="FAVORABLE"), prevFirstHit=""), 
         TEXT(TODAY(), "yyyy-mm-dd"), 
         prevFirstHit
       )
     )`
  );

  // Last Update timestamp
  setHeaderArray(
    hdrMap.lastUpdateCol, 'Last_Update',
    `TEXT(NOW(), "yyyy-mm-dd hh:mm:ss")`
  );

  // Total Hit Days (count of days strike was favorable)
  setHeaderArray(
    hdrMap.totalHitDaysCol, 'Total_Hit_Days',
    `LET(
       everHit, INDEX($${EW_columnToLetter(hdrMap.everHitStrikeCol)}2:$${EW_columnToLetter(hdrMap.everHitStrikeCol)}, ROW(${tRange})-1),
       prevTotal, INDEX($${EW_columnToLetter(hdrMap.totalHitDaysCol)}2:$${EW_columnToLetter(hdrMap.totalHitDaysCol)}, ROW(${tRange})-1),
       currentHit, INDEX($${EW_columnToLetter(hdrMap.strikeHitCol)}2:$${EW_columnToLetter(hdrMap.strikeHitCol)}, ROW(${tRange})-1),
       
       IF(OR(currentHit="HIT", currentHit="FAVORABLE"), 
         IF(prevTotal="", 1, prevTotal + 1), 
         IF(prevTotal="", 0, prevTotal)
       )
     )`
  );

  // Days to Expiration
  setHeaderArray(
    hdrMap.daysToExpCol, 'Days_To_Exp',
    `LET(
       expCol, $${EW_columnToLetter(hdrMap.expDateCol)}2:$${EW_columnToLetter(hdrMap.expDateCol)},
       rowNum, ROW(${tRange})-1,
       expDate, INDEX(expCol, rowNum),
       IF(expDate="",, MAX(0, expDate - TODAY()))
     )`
  );

  // Current Strike Hit Status
  setHeaderArray(
    hdrMap.strikeHitCol, 'Strike_Hit',
    `LET(
       stratCol, $${EW_columnToLetter(hdrMap.strategyCol)}2:$${EW_columnToLetter(hdrMap.strategyCol)},
       strikeCol, $${EW_columnToLetter(hdrMap.strikeCol)}2:$${EW_columnToLetter(hdrMap.strikeCol)},
       rowNum, ROW(${tRange})-1,
       strategy, UPPER(INDEX(stratCol, rowNum)),
       strike, INDEX(strikeCol, rowNum),
       currentPrice, IFERROR(GOOGLEFINANCE(t,"price"),),
       
       IF(OR(strategy="", strike="", currentPrice=""), "",
         IF(OR(ISNUMBER(SEARCH("LONG CALL", strategy)), ISNUMBER(SEARCH("BULL", strategy))),
           IF(currentPrice >= strike, "HIT", "NO"),
           IF(OR(ISNUMBER(SEARCH("LONG PUT", strategy)), ISNUMBER(SEARCH("BEAR", strategy))),
             IF(currentPrice <= strike, "HIT", "NO"),
             IF(OR(ISNUMBER(SEARCH("SHORT CALL", strategy)), ISNUMBER(SEARCH("COVERED", strategy))),
               IF(currentPrice < strike, "FAVORABLE", IF(currentPrice >= strike, "UNFAVORABLE", "NEUTRAL")),
               IF(ISNUMBER(SEARCH("SHORT PUT", strategy)),
                 IF(currentPrice > strike, "FAVORABLE", IF(currentPrice <= strike, "UNFAVORABLE", "NEUTRAL")),
                 "UNKNOWN"
               )
             )
           )
         )
       )
     )`
  );

  // Enhanced Success Score with historical data
  setHeaderArray(
    hdrMap.successScoreCol, 'Success_Score',
    `LET(
       everHit, INDEX($${EW_columnToLetter(hdrMap.everHitStrikeCol)}2:$${EW_columnToLetter(hdrMap.everHitStrikeCol)}, ROW(${tRange})-1),
       daysToExp, INDEX($${EW_columnToLetter(hdrMap.daysToExpCol)}2:$${EW_columnToLetter(hdrMap.daysToExpCol)}, ROW(${tRange})-1),
       totalHitDays, INDEX($${EW_columnToLetter(hdrMap.totalHitDaysCol)}2:$${EW_columnToLetter(hdrMap.totalHitDaysCol)}, ROW(${tRange})-1),
       rvol, INDEX($${EW_columnToLetter(hdrMap.rvol10Col)}2:$${EW_columnToLetter(hdrMap.rvol10Col)}, ROW(${tRange})-1),
       
       IF(OR(everHit="", daysToExp=""), "",
         LET(
           hitScore, IF(OR(everHit="TRUE", everHit="FAVORABLE"), 60, 
                        IF(everHit="UNFAVORABLE", 20, 40)),
           timeScore, MIN(30, MAX(0, daysToExp * 2)),
           volScore, MIN(10, MAX(0, (rvol - 1) * 10)),
           consistencyScore, MIN(20, totalHitDays * 2),
           hitScore + timeScore + volScore + consistencyScore
         )
       )
     )`
  );

  EW_trace('GF', 'ARRAYFORMULAs set (no DROP/TAKE)');
}

// ===== SUCCESS TRACKING & REPORTING FUNCTIONS =====

function EW_generateSuccessReport() {
  EW_trace('REPORT', 'Generating success report...', true);
  
  const ss = SpreadsheetApp.getActive();
  let reportSheet = ss.getSheetByName('Success_Report');
  if (!reportSheet) {
    reportSheet = ss.insertSheet('Success_Report');
  }
  
  // Clear existing content
  reportSheet.clear();
  
  // Create report header
  const reportHeaders = [
    'Strategy', 'Total_Positions', 'Hits', 'Hit_Rate_%', 'Avg_Success_Score',
    'Day1_Hit_Rate', 'Day2_Hit_Rate', 'Day5_Hit_Rate', 'Avg_Days_To_Hit',
    'Best_Performers', 'Worst_Performers', 'Recommendations'
  ];
  
  reportSheet.getRange(1, 1, 1, reportHeaders.length).setValues([reportHeaders]);
  
  // Get data from all strategy sheets
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  const reportData = [];
  
  strategies.forEach(strategy => {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) return;
    
    try {
      const data = sheet.getDataRange().getValues();
      const headers = data[0];
      const rows = data.slice(1);
      
      const hdrMap = EW_headerMap(headers);
      if (!hdrMap.strikeHitCol || !hdrMap.successScoreCol) return;
      
      // Calculate statistics
      const stats = EW_calculateStrategyStats(rows, hdrMap, strategy);
      reportData.push(stats);
      
    } catch (e) {
      EW_trace('REPORT', `Error processing ${strategy}: ${e.message}`, true);
    }
  });
  
  // Write report data
  if (reportData.length > 0) {
    const reportRows = reportData.map(stat => [
      stat.strategy,
      stat.totalPositions,
      stat.hits,
      stat.hitRate,
      stat.avgSuccessScore,
      stat.day1HitRate,
      stat.day2HitRate,
      stat.day5HitRate,
      stat.avgDaysToHit,
      stat.bestPerformers,
      stat.worstPerformers,
      stat.recommendations
    ]);
    
    reportSheet.getRange(2, 1, reportRows.length, reportHeaders.length).setValues(reportRows);
  }
  
  // Format the report
  reportSheet.getRange(1, 1, 1, reportHeaders.length).setFontWeight('bold');
  reportSheet.autoResizeColumns(1, reportHeaders.length);
  
  EW_trace('REPORT', 'Success report generated successfully!', true);
  SpreadsheetApp.getUi().alert('Success Report', 'Strategy success report has been generated in the "Success_Report" sheet.', SpreadsheetApp.getUi().ButtonSet.OK);
}

function EW_calculateStrategyStats(rows, hdrMap, strategyName) {
  const stats = {
    strategy: strategyName,
    totalPositions: rows.length,
    hits: 0,
    hitRate: 0,
    avgSuccessScore: 0,
    day1HitRate: 0,
    day2HitRate: 0,
    day5HitRate: 0,
    avgDaysToHit: 0,
    bestPerformers: '',
    worstPerformers: '',
    recommendations: ''
  };
  
  let totalSuccess = 0;
  let day1Hits = 0, day2Hits = 0, day5Hits = 0;
  let daysToHitSum = 0, hitCount = 0;
  const performers = [];
  
  rows.forEach((row, i) => {
    const ticker = row[hdrMap.tickerCol - 1] || '';
    const strikeHit = row[hdrMap.strikeHitCol - 1] || '';
    const successScore = parseFloat(row[hdrMap.successScoreCol - 1]) || 0;
    const day1Check = row[hdrMap.day1CheckCol - 1] || '';
    const day2Check = row[hdrMap.day2CheckCol - 1] || '';
    const day5Check = row[hdrMap.day5CheckCol - 1] || '';
    const hitDate = row[hdrMap.hitDateCol - 1] || '';
    const runDate = row[hdrMap.runDateCol - 1] || '';
    
    // Count hits
    if (strikeHit === 'HIT' || strikeHit === 'FAVORABLE') {
      stats.hits++;
      if (hitDate && runDate) {
        const days = (new Date(hitDate) - new Date(runDate)) / (1000 * 60 * 60 * 24);
        daysToHitSum += days;
        hitCount++;
      }
    }
    
    // Daily hit rates
    if (day1Check === 'HIT' || day1Check === 'FAVORABLE') day1Hits++;
    if (day2Check === 'HIT' || day2Check === 'FAVORABLE') day2Hits++;
    if (day5Check === 'HIT' || day5Check === 'FAVORABLE') day5Hits++;
    
    totalSuccess += successScore;
    
    performers.push({
      ticker: ticker,
      score: successScore,
      hit: strikeHit
    });
  });
  
  // Calculate percentages
  stats.hitRate = stats.totalPositions > 0 ? Math.round((stats.hits / stats.totalPositions) * 100) : 0;
  stats.day1HitRate = stats.totalPositions > 0 ? Math.round((day1Hits / stats.totalPositions) * 100) : 0;
  stats.day2HitRate = stats.totalPositions > 0 ? Math.round((day2Hits / stats.totalPositions) * 100) : 0;
  stats.day5HitRate = stats.totalPositions > 0 ? Math.round((day5Hits / stats.totalPositions) * 100) : 0;
  stats.avgSuccessScore = stats.totalPositions > 0 ? Math.round(totalSuccess / stats.totalPositions) : 0;
  stats.avgDaysToHit = hitCount > 0 ? Math.round(daysToHitSum / hitCount * 10) / 10 : 0;
  
  // Best and worst performers
  performers.sort((a, b) => b.score - a.score);
  stats.bestPerformers = performers.slice(0, 3).map(p => `${p.ticker}(${p.score})`).join(', ');
  stats.worstPerformers = performers.slice(-3).map(p => `${p.ticker}(${p.score})`).join(', ');
  
  // Generate recommendations
  if (stats.hitRate >= 70) {
    stats.recommendations = 'HIGH CONFIDENCE - Continue strategy';
  } else if (stats.hitRate >= 50) {
    stats.recommendations = 'MODERATE - Monitor closely';
  } else if (stats.hitRate >= 30) {
    stats.recommendations = 'LOW CONFIDENCE - Review parameters';
  } else {
    stats.recommendations = 'POOR PERFORMANCE - Revise strategy';
  }
  
  return stats;
}

function EW_updateTrackingData() {
  EW_trace('UPDATE', 'Updating tracking data for all sheets...', true);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let updatedSheets = 0;
  
  strategies.forEach(strategy => {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) return;
    
    try {
      // Force recalculation of tracking formulas
      const lastRow = sheet.getLastRow();
      const lastCol = sheet.getLastColumn();
      
      // Touch a cell to trigger recalculation
      const tempCell = sheet.getRange(lastRow + 1, 1);
      tempCell.setValue('REFRESH');
      tempCell.clear();
      
      SpreadsheetApp.flush(); // Force calculation
      updatedSheets++;
      
      EW_trace('UPDATE', `Updated tracking for ${strategy}`, false);
      
    } catch (e) {
      EW_trace('UPDATE', `Error updating ${strategy}: ${e.message}`, true);
    }
  });
  
  EW_trace('UPDATE', `Tracking data updated for ${updatedSheets} sheets`, true);
  SpreadsheetApp.getUi().alert('Update Complete', `Tracking data has been refreshed for ${updatedSheets} strategy sheets.`, SpreadsheetApp.getUi().ButtonSet.OK);
}

