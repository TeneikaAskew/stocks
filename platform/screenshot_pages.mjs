import { chromium } from 'playwright';
import fs from 'fs';

const OUT_DIR = '/tmp/page-screenshots';
fs.mkdirSync(OUT_DIR, { recursive: true });

// Routes that exist on the current branch (per Sidebar navItems).
const PAGES = [
  { name: 'dashboard', path: '/' },
  { name: 'live-market', path: '/live' },
  { name: 'charts', path: '/charts' },
  { name: 'options-flow', path: '/options' },
  { name: 'playbook', path: '/playbook' },
  { name: 'reports', path: '/reports' },
  { name: 'signals', path: '/signals' },
  { name: 'journal', path: '/journal' },
  { name: 'insights', path: '/insights', tabs: [
    { label: 'history', selector: 'button:has-text("History")' },
    { label: 'chat', selector: 'button:has-text("Chat")' },
  ] },
  { name: 'catalysts', path: '/catalysts' },
  { name: 'admin', path: '/admin' },
  { name: 'help', path: '/help' },
];

const results = [];
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const consoleErrors = [];
page.on('pageerror', (err) => consoleErrors.push({ type: 'pageerror', msg: err.message }));
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push({ type: 'console.error', msg: msg.text() });
});

for (const p of PAGES) {
  consoleErrors.length = 0;
  const url = `http://localhost:5173${p.path}`;
  const start = Date.now();
  let status = 'ok';
  let error = null;
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT_DIR}/${p.name}.png`, fullPage: true });
    if (p.tabs) {
      for (const tab of p.tabs) {
        try {
          await page.click(tab.selector, { timeout: 5000 });
          await page.waitForTimeout(800);
          await page.screenshot({ path: `${OUT_DIR}/${p.name}-${tab.label}.png`, fullPage: true });
        } catch (e) {
          results.push({ name: `${p.name}-${tab.label}`, status: 'tab-fail', error: e.message });
        }
      }
    }
  } catch (e) {
    status = 'fail';
    error = e.message;
  }
  results.push({
    name: p.name,
    url,
    status,
    error,
    errors: [...consoleErrors],
    ms: Date.now() - start,
  });
}

await browser.close();
console.log(JSON.stringify(results, null, 2));
