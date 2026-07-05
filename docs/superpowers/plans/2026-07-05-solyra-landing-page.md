# Solyra Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the public Solyra marketing/landing page (10 sections per spec) inside `platform/`, with a public waitlist API, public route wiring, and visuals that mirror the real app's gamma/chart language.

**Architecture:** The landing page is a React route (`platform/src/routes/LandingPage.tsx` + `components/landing/*`) rendered to signed-out visitors by `AuthGate` (firebase mode) and always available at `/welcome`. A new public `POST /api/waitlist` endpoint (FastAPI router + `waitlist_signups` table) captures signups with loud failures. All page numbers/visuals come from a clearly-marked marketing fixture module — no new financial math.

**Tech Stack:** React 19 + Vite 7 + TS 5.9, react-router-dom v7, plain CSS (design tokens), FastAPI + SQLAlchemy (`gcp.database.get_engine`), pytest (hermetic TestClient), vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-07-05-solyra-landing-page-design.md` — read it before starting.

## Global Constraints

- **Branch:** work on `feature/solyra-landing` (branched from `main` after the spec PR merges, or from `docs/solyra-landing-design` if not yet merged). Never commit to `main`.
- **Naming:** the words "Heatseeker", "Flowseeker", "Skylit" must NOT appear anywhere in landing copy, code, or fixtures. Public module names are exactly: `The Brief`, `Gamma Map`, `Flow`, `Council`, `Movement Read`, `Playbook` (spec §2).
- **Rule 3.7 (no silent fallbacks):** waitlist failures are loud (400/429/503 + visible UI error). Sole sanctioned exception: a tripped honeypot returns fake success to bots (documented in code).
- **No new npm or pip dependencies.** No `@testing-library/*`, no `email-validator` — validate email with a regex.
- **No new financial math in the frontend** — all landing numbers are static fixtures in `fixtures.ts`, clearly commented as marketing sample-day data (spec §6). The proof tile ships `hitRatePct: null` (renders without a number) unless filled from the real DB (Task 8).
- **Visual fidelity (spec §5):** King = solid gold `#f59e0b` width 2 · Gate = dotted blue `#3b82f6` · Flip = dashed violet `#a78bfa` · +gamma green `#34d399` / −gamma purple `#a78bfa`-family · heatmap green `rgba(34,197,94,α)` / red `rgba(239,68,68,α)` with gold-bordered King cell.
- **Motion:** every animation honors `prefers-reduced-motion: reduce` (reveal instantly, no typing effect).
- **Commits:** conventional format, no AI branding, one commit per task (or per red/green cycle where noted).
- **Commands run from:** repo root for `pytest`/`make`, `platform/` for `npm`.

---

### Task 1: Waitlist table + public API endpoint

**Files:**
- Modify: `gcp/schema.sql` (append table at end of file)
- Create: `platform/api/routers/waitlist.py`
- Modify: `platform/api/auth.py:34` (`_OPEN_API_PREFIXES`)
- Modify: `platform/api/main.py:23` (import) and `:73` (include_router)
- Test: `tests/test_waitlist_router.py`

**Interfaces:**
- Consumes: `gcp.database.get_engine()` (existing), `api.auth._OPEN_API_PREFIXES` (existing tuple).
- Produces: `POST /api/waitlist` accepting JSON `{"email": str, "source": str|null, "website": str}` → `200 {"status":"ok"}` | `400` | `429` | `503`. Frontend Task 7 calls this exact contract.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_waitlist_router.py`:

```python
"""Tests for POST /api/waitlist — the public landing-page signup endpoint.

Asserts (spec §7 + CLAUDE.md Rule 3.7):
  (a) valid email → 200 + one idempotent upsert executed;
  (b) malformed email → 400, no DB call;
  (c) filled honeypot (`website`) → 200 fake-success WITHOUT a DB call
      (the one sanctioned anti-bot fake success, documented in the router);
  (d) DB failure → LOUD 503, never a fake success;
  (e) >5 requests / window from one IP → 429.
Hermetic: gcp.database.get_engine is patched — no Cloud SQL.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform" / "api"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import waitlist as waitlist_router


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    waitlist_router._hits.clear()
    yield
    waitlist_router._hits.clear()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(waitlist_router.router)
    return TestClient(app)


def _engine_mock() -> MagicMock:
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False
    return engine


def test_valid_email_upserts_and_returns_ok():
    engine = _engine_mock()
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().post(
            "/api/waitlist",
            json={"email": "Trader@Example.com", "source": "landing-hero", "website": ""},
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    conn = engine.begin.return_value.__enter__.return_value
    assert conn.execute.call_count == 1
    params = conn.execute.call_args.args[1]
    assert params["email"] == "trader@example.com"  # normalized lowercase


def test_invalid_email_is_400_and_no_db_call():
    with patch("gcp.database.get_engine") as ge:
        r = _client().post("/api/waitlist", json={"email": "not-an-email", "website": ""})
    assert r.status_code == 400
    ge.assert_not_called()


def test_honeypot_returns_fake_success_without_db_call():
    with patch("gcp.database.get_engine") as ge:
        r = _client().post(
            "/api/waitlist",
            json={"email": "bot@spam.com", "website": "http://spam"},
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    ge.assert_not_called()


def test_db_failure_is_loud_503():
    with patch("gcp.database.get_engine", side_effect=RuntimeError("db down")):
        r = _client().post("/api/waitlist", json={"email": "a@b.co", "website": ""})
    assert r.status_code == 503


def test_rate_limit_429_after_five_requests():
    engine = _engine_mock()
    client = _client()
    with patch("gcp.database.get_engine", return_value=engine):
        for _ in range(5):
            assert client.post(
                "/api/waitlist", json={"email": "a@b.co", "website": ""}
            ).status_code == 200
        r = client.post("/api/waitlist", json={"email": "a@b.co", "website": ""})
    assert r.status_code == 429
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_waitlist_router.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'routers.waitlist'` (or ImportError) on every test.

- [ ] **Step 3: Create the router**

Create `platform/api/routers/waitlist.py`:

```python
"""Waitlist router — public signup capture for the Solyra landing page.

POST /api/waitlist
    Body: {"email": "...", "source": "landing-hero", "website": ""}

`website` is a honeypot field: the form hides it, humans never fill it, bots
do. A filled honeypot returns 200 WITHOUT writing — the one sanctioned
anti-bot fake success (spec §7). Every real failure is LOUD (Rule 3.7):
400 invalid email · 429 rate-limited · 503 DB unavailable.

Public endpoint: listed in api.auth._OPEN_API_PREFIXES (no bearer token).
"""
from __future__ import annotations

import logging
import re
import sys
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Per-IP sliding window: 5 requests / 10 min. In-memory = per Cloud Run
# instance; acceptable as a basic abuse guard for a waitlist form — durable
# abuse is already bounded by the UNIQUE(email) upsert.
_RATE_LIMIT = 5
_RATE_WINDOW_S = 600
_hits: dict[str, deque] = {}


class WaitlistBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    source: str | None = Field(default=None, max_length=64)
    website: str = ""  # honeypot — must stay empty


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    q = _hits.setdefault(ip, deque())
    while q and now - q[0] > _RATE_WINDOW_S:
        q.popleft()
    if len(q) >= _RATE_LIMIT:
        return True
    q.append(now)
    return False


@router.post("/api/waitlist")
def join_waitlist(body: WaitlistBody, request: Request) -> dict:
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="enter a valid email address")

    if body.website:
        # Honeypot tripped — bot traffic. Fake success, write nothing.
        logger.info(
            "waitlist honeypot tripped ip=%s",
            request.client.host if request.client else "?",
        )
        return {"status": "ok"}

    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="too many attempts — try again later")

    try:
        from gcp.database import get_engine  # noqa: PLC0415 — lazy: sqlalchemy is heavy
        from sqlalchemy import text  # noqa: PLC0415

        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO waitlist_signups (email, source, user_agent)
                    VALUES (:email, :source, :ua)
                    ON CONFLICT (email) DO UPDATE SET updated_at = now()
                    """
                ),
                {
                    "email": email,
                    "source": (body.source or "landing")[:64],
                    "ua": (request.headers.get("user-agent") or "")[:512],
                },
            )
    except HTTPException:
        raise
    except Exception as exc:  # INTERNAL failure → loud 503 (Rule 3.7), never fake success
        logger.error("waitlist insert failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="could not save your signup — please retry"
        ) from exc

    return {"status": "ok"}
```

Note for test (a): the test patches `gcp.database.get_engine`, so the lazy `from gcp.database import get_engine` inside the handler picks up the patched attribute at call time.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_waitlist_router.py -v`
Expected: 5 passed.

- [ ] **Step 5: Wire into the app + open-prefix allowlist + schema**

In `platform/api/auth.py` change line 34:

```python
_OPEN_API_PREFIXES = ("/api/health", "/api/me", "/api/config/firebase", "/api/waitlist")
```

In `platform/api/main.py` line 23, add `waitlist` to the router import list:

```python
from api.routers import live, options, playbook, backtest, signals, insights, journal, dashboard, catalysts, admin, analytics, config as config_router, health, glossary, grid, magnitude, earnings, waitlist
```

and after line 73 (`app.include_router(earnings.router, prefix="")`):

```python
app.include_router(waitlist.router, prefix="")
```

Append to the end of `gcp/schema.sql`:

```sql
-- ── Solyra landing page waitlist (public POST /api/waitlist) ────────────────
CREATE TABLE IF NOT EXISTS waitlist_signups (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    source        TEXT,
    user_agent    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 6: Run the full hermetic suite**

Run: `make test`
Expected: passes (existing auth tests in `tests/test_platform_auth.py` must still pass — the new prefix only ADDS an open path).

- [ ] **Step 7: Commit**

```bash
git add gcp/schema.sql platform/api/routers/waitlist.py platform/api/auth.py platform/api/main.py tests/test_waitlist_router.py
git commit -m "feat: add public waitlist endpoint + waitlist_signups table"
```

---

### Task 2: Public route wiring + LandingPage skeleton

**Files:**
- Create: `platform/src/routes/LandingPage.tsx` (skeleton — full content in Tasks 3–7)
- Modify: `platform/src/App.tsx`
- Modify: `platform/src/components/auth/AuthGate.tsx`

**Interfaces:**
- Consumes: existing `AuthGate`, `SignInScreen`, `LoadingSpinner`.
- Produces: route `/welcome` (always public), route `/signin` (redirects to `/` when signed in; shows `SignInScreen` when signed out), and the rule "signed-out firebase visitor on any path except `/signin` sees `LandingPage`". `LandingPage` default-exports a component rendering `<main className="solyra-landing" data-testid="landing-page">`. Tasks 3–7 fill it; Task 8's e2e asserts the testid.

- [ ] **Step 1: Create the skeleton page**

Create `platform/src/routes/LandingPage.tsx`:

```tsx
/**
 * Solyra public landing page — spec:
 * docs/superpowers/specs/2026-07-05-solyra-landing-page-design.md
 * Rendered (a) at /welcome always, (b) by AuthGate for signed-out visitors
 * in firebase mode. Must not require auth or Firebase.
 */
export default function LandingPage() {
  return (
    <main className="solyra-landing" data-testid="landing-page">
      <h1>Solyra</h1>
    </main>
  );
}
```

- [ ] **Step 2: Add the public routes**

In `platform/src/App.tsx`:

1. Add to the imports (line 2): `Navigate`:

```tsx
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
```

2. Add the lazy import after line 21:

```tsx
const LandingPage = lazy(() => import('@/routes/LandingPage'));
```

3. Replace the `createBrowserRouter([...])` call (lines 44–64) with:

```tsx
const router = createBrowserRouter([
  // Public marketing page — reachable in every auth mode (dev preview at /welcome).
  {
    path: '/welcome',
    element: <Suspense fallback={<PageLoader />}><LandingPage /></Suspense>,
  },
  // Signed-in users landing on /signin (post-login) bounce into the app.
  { path: '/signin', element: <Navigate to="/" replace /> },
  {
    element: <AppShell />,
    errorElement,
    children: [
      { path: '/', errorElement, element: <Suspense fallback={<PageLoader />}><DashboardPage /></Suspense> },
      { path: '/live', errorElement, element: <Suspense fallback={<PageLoader />}><LiveMarketPage /></Suspense> },
      { path: '/charts', errorElement, element: <Suspense fallback={<PageLoader />}><ChartsPage /></Suspense> },
      { path: '/options', errorElement, element: <Suspense fallback={<PageLoader />}><OptionsFlowPage /></Suspense> },
      { path: '/playbook', errorElement, element: <Suspense fallback={<PageLoader />}><PlaybookPage /></Suspense> },
      { path: '/reports', errorElement, element: <Suspense fallback={<PageLoader />}><ReportsPage /></Suspense> },
      { path: '/signals', errorElement, element: <Suspense fallback={<PageLoader />}><SignalsPage /></Suspense> },
      { path: '/journal', errorElement, element: <Suspense fallback={<PageLoader />}><JournalPage /></Suspense> },
      { path: '/insights', errorElement, element: <Suspense fallback={<PageLoader />}><InsightsPage /></Suspense> },
      { path: '/catalysts', errorElement, element: <Suspense fallback={<PageLoader />}><CatalystsPage /></Suspense> },
      { path: '/admin', errorElement, element: <Suspense fallback={<PageLoader />}><AdminPage /></Suspense> },
      { path: '/help', errorElement, element: <Suspense fallback={<PageLoader />}><HelpPage /></Suspense> },
      { path: '/settings', errorElement, element: <Suspense fallback={<PageLoader />}><SettingsPage /></Suspense> },
    ],
  },
]);
```

(Only the two new top-level routes are added; the AppShell group is unchanged.)

- [ ] **Step 3: Make AuthGate serve the landing page to signed-out visitors**

Replace the full contents of `platform/src/components/auth/AuthGate.tsx` with:

```tsx
import { lazy, Suspense, type ReactNode } from 'react';
import { useUser } from '@/hooks/useUser';
import { LoadingSpinner } from '@/components/shared/LoadingSpinner';
import { SignInScreen } from './SignInScreen';

const LandingPage = lazy(() => import('@/routes/LandingPage'));

/**
 * Top-level auth gate.
 *
 * Only `firebase` mode (the public app-login service) gates anything. In
 * `iap`/`open` mode the app renders directly, unchanged (keeps E2E specs
 * rendering as before).
 *
 * Signed-out firebase visitors get the PUBLIC LANDING PAGE (the product's
 * front door) on every path except /signin, which shows the login screen.
 * AuthGate renders outside the router, so the landing page uses plain
 * <a href> navigation and /signin is read from window.location.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { authMode, isSignedIn, isLoading } = useUser();

  if (authMode !== 'firebase') return <>{children}</>;

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)]">
        <LoadingSpinner size={28} />
      </div>
    );
  }

  if (!isSignedIn) {
    if (window.location.pathname === '/signin') return <SignInScreen />;
    return (
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)]">
            <LoadingSpinner size={28} />
          </div>
        }
      >
        <LandingPage />
      </Suspense>
    );
  }

  return <>{children}</>;
}
```

Post-login flow check (no code change expected): after a successful sign-in on `/signin`, `useUser().isSignedIn` flips → AuthGate renders the router → the `/signin` route `Navigate`s to `/`.

- [ ] **Step 4: Verify it compiles and dev-renders**

Run (in `platform/`): `npm run build`
Expected: `tsc -b && vite build` succeeds.

Run: `npm run dev` then open `http://localhost:5173/welcome`
Expected: dark page showing the "Solyra" h1 skeleton (open mode). `http://localhost:5173/` still renders the dashboard.

- [ ] **Step 5: Commit**

```bash
git add platform/src/routes/LandingPage.tsx platform/src/App.tsx platform/src/components/auth/AuthGate.tsx
git commit -m "feat: public /welcome landing route + signed-out landing front door"
```

---

### Task 3: Landing foundation — CSS tokens, fixtures, Nav, Hero with typing terminal

**Files:**
- Create: `platform/src/components/landing/landing.css`
- Create: `platform/src/components/landing/fixtures.ts`
- Create: `platform/src/components/landing/useTypingLines.ts`
- Create: `platform/src/components/landing/LandingNav.tsx`
- Create: `platform/src/components/landing/Hero.tsx`
- Modify: `platform/src/routes/LandingPage.tsx`

**Interfaces:**
- Produces (used by Tasks 4–7):
  - CSS classes: `.solyra-landing`, `.sl-sec`, `.sl-panel`, `.sl-tile`, `.sl-cta`, `.sl-cta2`, `.sl-mut`, `.sl-dim`, `.sl-mono`, `.sl-bull`, `.sl-bear`, `.sl-gold`, `.sl-viol`, `.sl-blue`, `.sl-h2`, `.sl-kicker`.
  - `fixtures.ts` named exports: `AGENT_LINES: {tag: string; text: string}[]`, `GAMMA_LADDER: {strike: string; side: 'pos'|'neg'; pct: number; marker?: 'king'|'gate'|'flip'}[]`, `SPOT_LABEL: string`, `BENTO: {verdict: {dir: string; bullScore: number; bearScore: number}; catalysts: {when: string; label: string; impact?: string}[]; movementRead: string; signals: {state: 'fired'|'armed'; text: string}[]; proof: {hitRatePct: number | null; caption: string}}`, `CANDLES: {bodyTop: number; bodyH: number; wickTop: number; wickBot: number; up: boolean}[]`, `HEAT_ROWS: {strike: string; kind: 'pos'|'neg'; alphas: number[]; marker?: 'king'|'spot'|'flip'}[]`, `FLOW_ROWS: {time: string; contract: string; size: string; prem: string; side: 'ask'|'bid'; sideLabel: string; read: string; flag?: boolean}[]`, `COUNCIL: {bull: {score: number; quote: string}; bear: {score: number; quote: string}; verdict: string; personas: string[]}`, `RHYTHM: {time: string; phase: string; title: string; body: string}[]`, `FAQ: {q: string; a: string}[]`.
  - `useTypingLines(total: number, intervalMs?: number): number` — visible-line count, reveals all instantly under reduced motion.

- [ ] **Step 1: Create `landing.css`**

```css
/* Solyra landing page — scoped design tokens + shared classes.
   Base palette matches the app's Obsidian tokens (index.css); the dawn
   accent (amber→orange) is landing-only. Spec §3. */
.solyra-landing {
  --sl-bg: #0b0d11;
  --sl-panel: #12151b;
  --sl-border: rgba(255, 255, 255, 0.08);
  --sl-text: #e8ecf1;
  --sl-mut: #97a1ad;
  --sl-dim: #6e7781;
  --sl-amber: #ffb85c;
  --sl-orange: #ff7a4d;
  --sl-gold: #ffb800;
  --sl-king: #f59e0b;
  --sl-gate: #3b82f6;
  --sl-bull: #34d399;
  --sl-bear: #f87171;
  --sl-viol: #a78bfa;
  --sl-blue: #6ec3f2;
  background: var(--sl-bg);
  color: var(--sl-text);
  min-height: 100vh;
  font-family: 'Montserrat', 'Segoe UI', system-ui, sans-serif;
}
.solyra-landing * { box-sizing: border-box; }
.sl-sec { padding: 72px 6vw; border-top: 1px solid rgba(255, 255, 255, 0.05); max-width: 1200px; margin: 0 auto; }
.sl-panel { background: var(--sl-panel); border: 1px solid var(--sl-border); border-radius: 12px; }
.sl-tile { background: var(--sl-panel); border: 1px solid var(--sl-border); border-radius: 12px; padding: 16px; }
.sl-tile h4 { margin: 0 0 2px; font-size: 11px; letter-spacing: 1.2px; color: var(--sl-mut); font-weight: 600; text-transform: uppercase; }
.sl-cta {
  background: linear-gradient(90deg, var(--sl-amber), var(--sl-orange));
  color: #1a1005; font-weight: 700; border: none; border-radius: 8px;
  padding: 11px 22px; font-size: 14px; cursor: pointer; display: inline-block;
  text-decoration: none;
}
.sl-cta2 { border: 1px solid rgba(255, 255, 255, 0.2); color: #cdd5de; border-radius: 8px; padding: 11px 22px; font-size: 14px; background: none; cursor: pointer; display: inline-block; text-decoration: none; }
.sl-mut { color: var(--sl-mut); }
.sl-dim { color: var(--sl-dim); }
.sl-mono { font-family: Consolas, ui-monospace, monospace; }
.sl-bull { color: var(--sl-bull); }
.sl-bear { color: var(--sl-bear); }
.sl-gold { color: var(--sl-gold); }
.sl-viol { color: var(--sl-viol); }
.sl-blue { color: var(--sl-blue); }
.sl-h2 { font-size: clamp(22px, 3vw, 28px); font-weight: 800; margin: 0 0 6px; }
.sl-kicker { font-size: 11px; letter-spacing: 2px; color: var(--sl-gold); text-transform: uppercase; }
.sl-sun {
  width: 22px; height: 22px; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #ffd9a0, #ff8a4d 55%, #7a3416);
  box-shadow: 0 0 14px rgba(255, 150, 70, 0.5);
}
.sl-2col { display: flex; gap: 36px; align-items: center; }
@media (max-width: 900px) { .sl-2col { flex-direction: column; } .sl-sec { padding: 48px 5vw; } }
```

- [ ] **Step 2: Create `fixtures.ts`**

```ts
/**
 * MARKETING FIXTURES — a representative sample trading day for the Solyra
 * landing page. These are STATIC illustrations of the product's real visual
 * language (spec §5/§6), NOT live data and NOT performance claims. The proof
 * tile ships hitRatePct: null (renders without a number) until filled from
 * walk_forward_results — see the plan Task 8 verification step.
 */
export const AGENT_LINES: { tag: string; text: string }[] = [
  { tag: '', text: '06:58:12 · waking 7 agents for SPY, QQQ, IWM…' },
  { tag: 'brief', text: 'daily bias LONG — full-timeframe continuity 3/4 aligned' },
  { tag: 'gamma', text: 'dealer wall at 592 · flip zone 585 · dealers short gamma' },
  { tag: 'flow', text: '3× sweep clusters on 590C 0DTE, $4.2M premium, ask-side' },
  { tag: 'council', text: 'bull 6.2 / bear 3.8 → verdict: LONG above 588' },
  { tag: 'catalyst', text: 'CPI 8:30a — expect widened range; plan sized at ½R' },
  { tag: '', text: '07:00:00 · your brief is ready. read it →' },
];

export const SPOT_LABEL = 'spot 590.61';

export const GAMMA_LADDER: {
  strike: string; side: 'pos' | 'neg'; pct: number; marker?: 'king' | 'gate' | 'flip';
}[] = [
  { strike: '596', side: 'neg', pct: 18 },
  { strike: '594', side: 'pos', pct: 34 },
  { strike: '592', side: 'pos', pct: 96, marker: 'king' },
  { strike: '591', side: 'pos', pct: 46 },
  { strike: '590', side: 'pos', pct: 40, marker: 'gate' },
  { strike: '589', side: 'neg', pct: 22 },
  { strike: '588', side: 'neg', pct: 64 },
  { strike: '586', side: 'neg', pct: 38 },
  { strike: '585', side: 'neg', pct: 52, marker: 'flip' },
  { strike: '583', side: 'neg', pct: 20 },
];

export const BENTO = {
  verdict: { dir: 'LONG', bullScore: 6.2, bearScore: 3.8 },
  catalysts: [
    { when: '08:30', label: 'CPI', impact: 'HIGH' },
    { when: 'Thu', label: 'NVDA earnings' },
    { when: 'Fri', label: 'OpEx · $2.1T' },
  ],
  movementRead:
    '"SPY held the Gate at 588, reclaimed VWAP on the 10:05 bar, and dealers chased it back toward the King…"',
  signals: [
    { state: 'fired' as const, text: 'fired 10:07 · gate-hold LONG +1.4R' },
    { state: 'armed' as const, text: 'armed · vwap-reclaim' },
    { state: 'armed' as const, text: 'armed · king-reject fade' },
  ],
  proof: {
    hitRatePct: null as number | null,
    caption: 'walk-forward validated out-of-sample · every signal graded HIT / WRONG / NOISE',
  },
};

/** 24 five-minute candles in SVG y-space (viewBox 0 0 720 280). */
export const CANDLES: {
  bodyTop: number; bodyH: number; wickTop: number; wickBot: number; up: boolean;
}[] = [
  { bodyTop: 225, bodyH: 14, wickTop: 218, wickBot: 246, up: true },
  { bodyTop: 208, bodyH: 17, wickTop: 202, wickBot: 228, up: true },
  { bodyTop: 206, bodyH: 10, wickTop: 198, wickBot: 222, up: false },
  { bodyTop: 188, bodyH: 18, wickTop: 182, wickBot: 212, up: true },
  { bodyTop: 168, bodyH: 16, wickTop: 162, wickBot: 192, up: true },
  { bodyTop: 148, bodyH: 18, wickTop: 142, wickBot: 172, up: true },
  { bodyTop: 150, bodyH: 12, wickTop: 140, wickBot: 168, up: false },
  { bodyTop: 128, bodyH: 20, wickTop: 122, wickBot: 152, up: true },
  { bodyTop: 106, bodyH: 20, wickTop: 100, wickBot: 130, up: true },
  { bodyTop: 88, bodyH: 16, wickTop: 82, wickBot: 110, up: true },
  { bodyTop: 74, bodyH: 12, wickTop: 50, wickBot: 92, up: true },
  { bodyTop: 76, bodyH: 16, wickTop: 48, wickBot: 96, up: false },
  { bodyTop: 94, bodyH: 18, wickTop: 88, wickBot: 118, up: false },
  { bodyTop: 114, bodyH: 18, wickTop: 108, wickBot: 138, up: false },
  { bodyTop: 112, bodyH: 12, wickTop: 104, wickBot: 132, up: true },
  { bodyTop: 122, bodyH: 22, wickTop: 116, wickBot: 158, up: false },
  { bodyTop: 144, bodyH: 16, wickTop: 138, wickBot: 166, up: false },
  { bodyTop: 150, bodyH: 10, wickTop: 144, wickBot: 170, up: true },
  { bodyTop: 152, bodyH: 10, wickTop: 146, wickBot: 176, up: false },
  { bodyTop: 138, bodyH: 16, wickTop: 132, wickBot: 162, up: true },
  { bodyTop: 118, bodyH: 18, wickTop: 112, wickBot: 142, up: true },
  { bodyTop: 100, bodyH: 16, wickTop: 94, wickBot: 124, up: true },
  { bodyTop: 84, bodyH: 14, wickTop: 78, wickBot: 108, up: true },
  { bodyTop: 72, bodyH: 10, wickTop: 64, wickBot: 94, up: true },
];

export const HEAT_ROWS: {
  strike: string; kind: 'pos' | 'neg'; alphas: number[]; marker?: 'king' | 'spot' | 'flip';
}[] = [
  { strike: '596', kind: 'pos', alphas: [0.25, 0.35, 0.2, 0.15, 0.25, 0.12, 0.1] },
  { strike: '592', kind: 'pos', alphas: [0.85, 0.6, 0.45, 0.3, 0.45, 0.22, 0.15], marker: 'king' },
  { strike: '590', kind: 'pos', alphas: [0.4, 0.5, 0.3, 0.22, 0.15, 0.25, 0.1], marker: 'spot' },
  { strike: '588', kind: 'neg', alphas: [0.55, 0.4, 0.48, 0.25, 0.32, 0.18, 0.12] },
  { strike: '585', kind: 'neg', alphas: [0.5, 0.35, 0.42, 0.28, 0.2, 0.24, 0.12], marker: 'flip' },
  { strike: '583', kind: 'neg', alphas: [0.3, 0.22, 0.26, 0.15, 0.18, 0.12, 0.08] },
];

export const HEAT_EXPIRIES = ['0DTE', '1d', '2d', '1w', '2w', '3w', '30d'];

export const FLOW_ROWS: {
  time: string; contract: string; size: string; prem: string;
  side: 'ask' | 'bid'; sideLabel: string; read: string; flag?: boolean;
}[] = [
  { time: '10:06:52', contract: 'SPY 590C 0DTE', size: '2,400', prem: '$1.9M', side: 'ask', sideLabel: 'ASK sweep', read: '⚑ cluster 3/3', flag: true },
  { time: '10:06:41', contract: 'SPY 590C 0DTE', size: '1,850', prem: '$1.4M', side: 'ask', sideLabel: 'ASK sweep', read: 'cluster 2/3' },
  { time: '10:05:58', contract: 'QQQ 512C 2d', size: '900', prem: '$0.8M', side: 'ask', sideLabel: 'ASK', read: '—' },
  { time: '10:05:13', contract: 'SPY 585P 0DTE', size: '3,100', prem: '$0.9M', side: 'bid', sideLabel: 'BID (closing)', read: 'puts sold ↓' },
  { time: '10:04:47', contract: 'IWM 218C 1w', size: '1,200', prem: '$0.5M', side: 'ask', sideLabel: 'ASK', read: '—' },
];

export const COUNCIL = {
  bull: { score: 6.2, quote: '"Timeframes aligned long, dealers short gamma above 588 — rallies get chased, not sold."' },
  bear: { score: 3.8, quote: '"CPI at 8:30 can flip the tape; RSI is stretched into the King."' },
  verdict: 'LONG above 588 · target 592 · invalidated below 585 · half size until CPI prints',
  personas: ['scalper plan', 'swing plan', 'income plan'],
};

export const RHYTHM = [
  {
    time: '07:00', phase: 'LEARN', title: 'The Brief',
    body: 'Bias, the three levels that matter, today’s catalysts, and the setup the playbook likes — in plain language, with every term one tap from its glossary definition. Five minutes, coffee in hand.',
  },
  {
    time: '09:30', phase: 'DO', title: 'The open — signals live',
    body: 'Agents watch every 1-minute bar. When a playbook setup triggers, you get the alert with entry, target, stop, and the win rate that earned it a place in the book. No chart-staring required.',
  },
  {
    time: '16:00', phase: 'ACT', title: 'The close — review & compound',
    body: 'Movement Read explains the day in one paragraph. Your journal auto-grades the signals you took against the ones you skipped. Tomorrow’s you starts smarter.',
  },
];

export const FAQ = [
  {
    q: 'Is this financial advice?',
    a: 'No — Solyra is an analytics and education platform. It shows you what’s happening and what has historically followed; decisions stay yours.',
  },
  {
    q: 'Do I need options experience?',
    a: 'No. Every brief links each concept to a plain-language explainer. Learn is a first-class module, not a help page.',
  },
  {
    q: 'Where does the data come from?',
    a: 'Institutional options chains, 1-minute market data, and a validated signal engine — every signal graded daily against reality.',
  },
];
```

- [ ] **Step 3: Create `useTypingLines.ts`**

```ts
import { useEffect, useState } from 'react';

/**
 * Progressive line-reveal for the hero agent terminal.
 * Returns how many lines are visible. Reveals one line per `intervalMs`.
 * Honors prefers-reduced-motion by revealing everything immediately.
 */
export function useTypingLines(total: number, intervalMs = 650): number {
  const [visible, setVisible] = useState(0);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setVisible(total);
      return;
    }
    setVisible(0);
    const id = window.setInterval(() => {
      setVisible((v) => {
        if (v + 1 >= total) window.clearInterval(id);
        return Math.min(v + 1, total);
      });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [total, intervalMs]);

  return visible;
}
```

- [ ] **Step 4: Create `LandingNav.tsx`**

```tsx
/** Section 01 — top nav. Plain anchors: AuthGate renders this outside the router. */
export function LandingNav() {
  return (
    <nav
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '16px 6vw', maxWidth: 1200, margin: '0 auto',
      }}
    >
      <a href="/welcome" style={{ display: 'flex', alignItems: 'center', gap: 9, textDecoration: 'none', color: 'inherit' }}>
        <div className="sl-sun" />
        <span style={{ fontWeight: 800, letterSpacing: '2.5px', fontSize: 15 }}>SOLYRA</span>
      </a>
      <div className="sl-mut" style={{ fontSize: 13, display: 'flex', gap: 22 }}>
        <a href="#modules" style={{ color: 'inherit', textDecoration: 'none' }}>Modules</a>
        <a href="#learn" style={{ color: 'inherit', textDecoration: 'none' }}>Learn</a>
        <a href="#faq" style={{ color: 'inherit', textDecoration: 'none' }}>FAQ</a>
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <a href="/signin" className="sl-mut" style={{ fontSize: 13, textDecoration: 'none' }}>Sign in</a>
        <a href="#waitlist" className="sl-cta" style={{ padding: '8px 16px', fontSize: 12 }}>Request access</a>
      </div>
    </nav>
  );
}
```

- [ ] **Step 5: Create `Hero.tsx`**

```tsx
import { AGENT_LINES } from './fixtures';
import { useTypingLines } from './useTypingLines';

/** Section 02 — hero with the live agent terminal (spec §4.2). */
export function Hero() {
  const visible = useTypingLines(AGENT_LINES.length);

  return (
    <header
      className="sl-sec sl-2col"
      style={{
        borderTop: 'none', paddingTop: 44, paddingBottom: 56,
        background:
          'radial-gradient(ellipse 70% 55% at 72% 30%, rgba(255,150,70,.13), transparent), ' +
          'radial-gradient(ellipse 40% 40% at 20% 80%, rgba(110,195,242,.05), transparent)',
      }}
    >
      <div style={{ flex: 1.1 }}>
        <div className="sl-kicker" style={{ color: 'var(--sl-amber)', marginBottom: 14 }}>
          The AI analyst desk for market movement
        </div>
        <h1 style={{ fontSize: 'clamp(30px, 4.5vw, 44px)', lineHeight: 1.12, fontWeight: 800, margin: 0 }}>
          Know why the market moves.
          <br />
          <span
            style={{
              background: 'linear-gradient(90deg, #ffd9a0, #ff8a4d)',
              WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
            }}
          >
            Before it moves.
          </span>
        </h1>
        <p className="sl-mut" style={{ fontSize: 16, lineHeight: 1.55, margin: '18px 0 24px', maxWidth: 440 }}>
          Solyra&rsquo;s agents read dealer positioning, options flow, and every catalyst on the
          calendar — then hand you a plain-language brief, live signals, and the reason behind
          every move. Learn it. Trade it. Review it.
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <a href="#waitlist" className="sl-cta">Join the waitlist</a>
          <a href="#learn" className="sl-cta2">See a live day ↓</a>
        </div>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 14 }}>
          Early access · no card required · built on institutional options &amp; 1-minute market data
        </div>
      </div>

      <div className="sl-panel" style={{ flex: 1, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,.5), 0 0 40px rgba(255,150,70,.06)' }}>
        <div
          style={{
            display: 'flex', justifyContent: 'space-between', padding: '10px 14px',
            borderBottom: '1px solid rgba(255,255,255,.07)', fontSize: 11,
          }}
        >
          <span className="sl-mut">solyra · agent desk</span>
          <span className="sl-bull">● sample premarket session</span>
        </div>
        <div className="sl-mono" style={{ padding: '14px 16px', fontSize: 12, lineHeight: 1.85, minHeight: 200 }}>
          {AGENT_LINES.slice(0, visible).map((line, i) => (
            <div key={i} className={line.tag ? undefined : 'sl-dim'}>
              {line.tag && <span className="sl-gold">{line.tag}</span>}
              {line.tag ? ' · ' : ''}
              {line.text}
            </div>
          ))}
          {visible >= AGENT_LINES.length && (
            <div style={{ marginTop: 8 }}>
              <span
                className="sl-bull"
                style={{
                  background: 'rgba(52,211,153,.1)', border: '1px solid rgba(52,211,153,.3)',
                  borderRadius: 6, padding: '3px 10px', fontSize: 11,
                }}
              >
                3 signals armed · watching every 1-min bar
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 6: Wire into the page**

Replace `platform/src/routes/LandingPage.tsx` with:

```tsx
/**
 * Solyra public landing page — spec:
 * docs/superpowers/specs/2026-07-05-solyra-landing-page-design.md
 * Rendered (a) at /welcome always, (b) by AuthGate for signed-out visitors
 * in firebase mode. Must not require auth or Firebase.
 */
import '@/components/landing/landing.css';
import { LandingNav } from '@/components/landing/LandingNav';
import { Hero } from '@/components/landing/Hero';

export default function LandingPage() {
  return (
    <main className="solyra-landing" data-testid="landing-page">
      <LandingNav />
      <Hero />
    </main>
  );
}
```

- [ ] **Step 7: Verify build + visual check**

Run (in `platform/`): `npm run build` → succeeds.
Run: `npm run dev` → open `http://localhost:5173/welcome`: nav + hero render, terminal lines type in one-by-one; with OS reduced-motion enabled they appear instantly.

- [ ] **Step 8: Commit**

```bash
git add platform/src/components/landing platform/src/routes/LandingPage.tsx
git commit -m "feat: landing foundation — tokens, fixtures, nav, hero agent terminal"
```

---

### Task 4: Command bento grid (section 03)

**Files:**
- Create: `platform/src/components/landing/BentoGrid.tsx`
- Modify: `platform/src/routes/LandingPage.tsx`

**Interfaces:**
- Consumes: `GAMMA_LADDER`, `SPOT_LABEL`, `BENTO` from `./fixtures`; CSS classes from Task 3.
- Produces: `<BentoGrid />` (section with id `modules`).

- [ ] **Step 1: Create `BentoGrid.tsx`**

```tsx
import { BENTO, GAMMA_LADDER, SPOT_LABEL } from './fixtures';

/** The diverging strike ladder — mirrors the app's Profiles tab (spec §5). */
function GammaLadderTile() {
  const markerLabel = { king: '★K', gate: '◆G', flip: '⇅F' } as const;
  const markerClass = { king: 'sl-gold', gate: 'sl-blue', flip: 'sl-viol' } as const;

  return (
    <div className="sl-tile" style={{ gridRow: 'span 2', position: 'relative' }}>
      <h4>Gamma Map</h4>
      <div className="sl-dim" style={{ fontSize: 11 }}>net dealer gamma by strike</div>
      <div style={{ marginTop: 12, position: 'relative' }}>
        <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, borderLeft: '1px dashed rgba(255,255,255,.18)' }} />
        {GAMMA_LADDER.map((row) => (
          <div
            key={row.strike}
            className="sl-mono"
            style={{
              display: 'grid', gridTemplateColumns: '40px 1fr 1fr 34px',
              alignItems: 'center', height: 17, fontSize: 9.5,
            }}
          >
            <span className={row.marker ? markerClass[row.marker] : 'sl-dim'}>{row.strike}</span>
            <span style={{ display: 'flex', justifyContent: 'flex-end' }}>
              {row.side === 'neg' && (
                <span style={{ height: 11, borderRadius: 2, width: `${row.pct}%`, background: row.pct > 55 ? '#8b5cf6' : '#7c5bb5' }} />
              )}
            </span>
            <span style={{ display: 'flex', justifyContent: 'flex-start' }}>
              {row.side === 'pos' && (
                <span
                  style={{
                    height: 11, borderRadius: 2, width: `${row.pct}%`,
                    background: row.marker === 'king'
                      ? 'linear-gradient(90deg,#34d399,#ffb800)'
                      : '#2bb381',
                    boxShadow: row.marker === 'king' ? '0 0 9px rgba(255,184,0,.45)' : undefined,
                  }}
                />
              )}
            </span>
            <span className={row.marker ? markerClass[row.marker] : 'sl-dim'}>
              {row.marker ? markerLabel[row.marker] : ''}
            </span>
          </div>
        ))}
        <div style={{ position: 'absolute', left: 0, right: 0, top: 79, borderTop: '1.5px dashed rgba(248,113,113,.8)' }} />
        <div className="sl-mono" style={{ position: 'absolute', right: -4, top: 70, fontSize: 9, color: 'var(--sl-bear)' }}>
          {SPOT_LABEL}
        </div>
      </div>
      <div className="sl-mono" style={{ display: 'flex', gap: 10, fontSize: 9.5, marginTop: 10 }}>
        <span className="sl-bull">■ +gamma</span>
        <span className="sl-viol">■ −gamma</span>
        <span className="sl-gold">★ King</span>
        <span className="sl-blue">◆ Gate</span>
        <span className="sl-viol">⇅ Flip</span>
      </div>
    </div>
  );
}

/** Section 03 — six real-product tiles (spec §4.3). */
export function BentoGrid() {
  const { verdict, catalysts, movementRead, signals, proof } = BENTO;
  const bullWidthPct = Math.round((verdict.bullScore / (verdict.bullScore + verdict.bearScore)) * 100);

  return (
    <section className="sl-sec" id="modules">
      <h2 className="sl-h2">Everything that moves the market. One surface.</h2>
      <p className="sl-mut" style={{ margin: '0 0 20px', fontSize: 14 }}>
        Six systems, one verdict — every tile is the real product&rsquo;s own visual, not marketing art.
      </p>
      <div
        style={{
          display: 'grid', gap: 12,
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gridAutoRows: 'minmax(118px, auto)',
        }}
      >
        <GammaLadderTile />
        <div className="sl-tile">
          <h4>Council · AI verdict</h4>
          <div className="sl-bull" style={{ fontSize: 22, fontWeight: 800, marginTop: 10 }}>{verdict.dir}</div>
          <div style={{ height: 8, borderRadius: 4, background: 'var(--sl-bear)', overflow: 'hidden', marginTop: 8 }}>
            <div style={{ width: `${bullWidthPct}%`, height: '100%', background: 'var(--sl-bull)' }} />
          </div>
          <div className="sl-dim" style={{ fontSize: 11, marginTop: 6 }}>
            bull {verdict.bullScore} · bear {verdict.bearScore} · 7 agents
          </div>
        </div>
        <div className="sl-tile">
          <h4>Catalysts · next up</h4>
          <div className="sl-mono" style={{ marginTop: 10, fontSize: 12 }}>
            {catalysts.map((c) => (
              <div key={c.label}>
                <span className={c.impact ? 'sl-gold' : 'sl-dim'}>{c.when}</span> {c.label}{' '}
                {c.impact && <span className="sl-bear">{c.impact}</span>}
              </div>
            ))}
          </div>
        </div>
        <div className="sl-tile">
          <h4>Movement Read</h4>
          <p className="sl-mut" style={{ fontSize: 12, lineHeight: 1.5, margin: '8px 0 0' }}>{movementRead}</p>
        </div>
        <div className="sl-tile">
          <h4>Signals · today</h4>
          <div className="sl-mono" style={{ marginTop: 10, fontSize: 12 }}>
            {signals.map((s) => (
              <div key={s.text} className={s.state === 'fired' ? 'sl-bull' : 'sl-dim'}>● {s.text}</div>
            ))}
          </div>
        </div>
        <div className="sl-tile">
          <h4>Proof · walk-forward</h4>
          {proof.hitRatePct !== null ? (
            <div style={{ fontSize: 20, fontWeight: 800, marginTop: 8 }}>
              {proof.hitRatePct}% <span className="sl-dim" style={{ fontSize: 11, fontWeight: 400 }}>hit rate</span>
            </div>
          ) : (
            <div style={{ fontSize: 14, fontWeight: 700, marginTop: 8 }}>Results published at launch</div>
          )}
          <div className="sl-dim" style={{ fontSize: 11, marginTop: 4 }}>{proof.caption}</div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Mount in `LandingPage.tsx`**

Add the import and render `<BentoGrid />` after `<Hero />`:

```tsx
import { BentoGrid } from '@/components/landing/BentoGrid';
// …inside <main>, after <Hero />:
<BentoGrid />
```

- [ ] **Step 3: Verify**

Run (in `platform/`): `npm run build` → succeeds. Dev-check `/welcome`: six tiles; gamma ladder shows the gold King bar at 592, purple bars left, red dashed spot line; proof tile shows "Results published at launch" (null fixture).

- [ ] **Step 4: Commit**

```bash
git add platform/src/components/landing/BentoGrid.tsx platform/src/routes/LandingPage.tsx
git commit -m "feat: landing command bento with real-visual gamma ladder tile"
```

---

### Task 5: Chart showcase (section 04)

**Files:**
- Create: `platform/src/components/landing/ChartShowcase.tsx`
- Modify: `platform/src/routes/LandingPage.tsx`

**Interfaces:**
- Consumes: `CANDLES` from `./fixtures`.
- Produces: `<ChartShowcase />`.

- [ ] **Step 1: Create `ChartShowcase.tsx`**

```tsx
import { CANDLES } from './fixtures';

const GREEN = '#34d399';
const RED = '#f87171';

/**
 * Section 04 — SPY sample chart with gamma levels in the app's EXACT
 * Charts-page line styles (spec §5): King solid gold #f59e0b w2,
 * Gate dotted blue #3b82f6, Flip dashed violet #a78bfa.
 */
export function ChartShowcase() {
  return (
    <section className="sl-sec">
      <h2 className="sl-h2">
        Charts that show the <em style={{ color: 'var(--sl-amber)' }}>why</em>.
      </h2>
      <p className="sl-mut" style={{ margin: '0 0 18px', fontSize: 14, maxWidth: 560 }}>
        Every level on a Solyra chart exists because dealers put it there. King, Gate, and Flip
        are drawn from live options positioning — not trendline art.
      </p>
      <div className="sl-panel" style={{ padding: '18px 20px', overflowX: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 10 }}>
          <span><b>SPY</b> <span className="sl-dim">· 5-min · gamma overlay · sample session</span></span>
          <span className="sl-mono sl-bull">590.61 ▲ +0.9%</span>
        </div>
        <svg viewBox="0 0 720 280" style={{ width: '100%', height: 'auto', display: 'block', minWidth: 560 }}>
          {[70, 140, 210].map((y) => (
            <line key={y} x1="0" y1={y} x2="720" y2={y} stroke="rgba(255,255,255,.04)" />
          ))}

          {/* KING — solid gold, width 2 (ChartsPage lineStyle 0) */}
          <line x1="0" y1="42" x2="640" y2="42" stroke="#f59e0b" strokeWidth="2" />
          <rect x="640" y="32" width="80" height="20" rx="4" fill="rgba(245,158,11,.12)" stroke="#f59e0b" strokeWidth=".7" />
          <text x="680" y="46" fill="#f59e0b" fontSize="11" textAnchor="middle" fontFamily="Consolas">★ KING 592</text>

          {/* GATE — dotted blue (ChartsPage lineStyle 2) */}
          <line x1="0" y1="154" x2="640" y2="154" stroke="#3b82f6" strokeWidth="1.2" strokeDasharray="2 4" />
          <rect x="640" y="144" width="80" height="20" rx="4" fill="rgba(59,130,246,.1)" stroke="#3b82f6" strokeWidth=".7" />
          <text x="680" y="158" fill="#60a5fa" fontSize="11" textAnchor="middle" fontFamily="Consolas">◆ GATE 588</text>

          {/* FLIP — dashed violet (ChartsPage lineStyle 1) */}
          <line x1="0" y1="238" x2="640" y2="238" stroke="#a78bfa" strokeWidth="2" strokeDasharray="8 5" />
          <rect x="640" y="228" width="80" height="20" rx="4" fill="rgba(167,139,250,.1)" stroke="#a78bfa" strokeWidth=".7" />
          <text x="680" y="242" fill="#a78bfa" fontSize="11" textAnchor="middle" fontFamily="Consolas">⇅ FLIP 585</text>

          {/* VWAP */}
          <path
            d="M 14 220 C 120 200, 200 150, 300 120 S 480 130, 560 100 S 640 80, 660 76"
            stroke="#6ec3f2" strokeWidth="1.3" fill="none" opacity=".75"
          />

          {/* candles */}
          {CANDLES.map((c, i) => {
            const x = 14 + i * 27;
            const color = c.up ? GREEN : RED;
            return (
              <g key={i} strokeWidth="1.4">
                <line x1={x + 7.5} y1={c.wickTop} x2={x + 7.5} y2={c.wickBot} stroke={color} />
                <rect x={x} y={c.bodyTop} width="15" height={c.bodyH} fill={color} />
              </g>
            );
          })}

          {/* signal marker */}
          <circle cx="487.5" cy="176" r="5" fill="none" stroke={GREEN} strokeWidth="1.5" />
          <line x1="487.5" y1="181" x2="487.5" y2="196" stroke={GREEN} strokeWidth="1" />
          <rect x="420" y="196" width="135" height="22" rx="5" fill="rgba(52,211,153,.1)" stroke="rgba(52,211,153,.4)" strokeWidth=".8" />
          <text x="487" y="211" fill={GREEN} fontSize="10.5" textAnchor="middle" fontFamily="Consolas">SIGNAL · gate-hold LONG</text>

          {/* rejection annotation */}
          <rect x="255" y="18" width="150" height="20" rx="5" fill="rgba(245,158,11,.08)" stroke="rgba(245,158,11,.35)" strokeWidth=".8" />
          <text x="330" y="32" fill="#f59e0b" fontSize="10.5" textAnchor="middle" fontFamily="Consolas">King rejection — dealers sell</text>
        </svg>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Mount in `LandingPage.tsx`** — add `<ChartShowcase />` after `<BentoGrid />` (import from `@/components/landing/ChartShowcase`).

- [ ] **Step 3: Verify** — `npm run build` passes; dev-check: chart renders, King line solid gold, Gate dotted blue, Flip dashed violet; container scrolls horizontally on a narrow window instead of overflowing the page.

- [ ] **Step 4: Commit**

```bash
git add platform/src/components/landing/ChartShowcase.tsx platform/src/routes/LandingPage.tsx
git commit -m "feat: landing chart showcase with app-faithful gamma level styles"
```

---

### Task 6: Module deep-dives + daily rhythm (sections 05–08)

**Files:**
- Create: `platform/src/components/landing/ModuleDives.tsx`
- Create: `platform/src/components/landing/DailyRhythm.tsx`
- Modify: `platform/src/routes/LandingPage.tsx`

**Interfaces:**
- Consumes: `HEAT_ROWS`, `HEAT_EXPIRIES`, `FLOW_ROWS`, `COUNCIL`, `RHYTHM` from `./fixtures`.
- Produces: `<ModuleDives />` (Gamma Map · Flow · Council) and `<DailyRhythm />` (section with id `learn`).

- [ ] **Step 1: Create `ModuleDives.tsx`**

```tsx
import { COUNCIL, FLOW_ROWS, HEAT_EXPIRIES, HEAT_ROWS } from './fixtures';

/** Section 05 — Gamma Map deep-dive: the Swing-Mode strike×expiry grid (spec §5). */
function GammaMapDive() {
  return (
    <section className="sl-sec sl-2col">
      <div style={{ flex: 1 }}>
        <div className="sl-kicker">Gamma Map · dealer positioning</div>
        <h3 style={{ fontSize: 22, fontWeight: 800, margin: '8px 0' }}>See the wall before price hits it.</h3>
        <p className="sl-mut" style={{ fontSize: 14, lineHeight: 1.6 }}>
          A strike-by-expiry grid of net dealer gamma, refreshed all session — green where calls
          dominate and dealers pin, red where puts dominate and moves accelerate. The gold cell is
          the King: the strike dealers defend hardest.
        </p>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 8 }}>
          ↳ replaces guesswork S/R lines · SPY · QQQ · IWM · SPX at launch
        </div>
      </div>
      <div className="sl-panel" style={{ flex: 1, padding: 16, width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 10 }}>
          <span className="sl-mut">net GEX · strike × expiry · sample session</span>
        </div>
        <div className="sl-mono" style={{ display: 'grid', gridTemplateColumns: '44px repeat(7, 1fr)', gap: 3, fontSize: 9.5 }}>
          {HEAT_ROWS.map((row) => {
            const rgb = row.kind === 'pos' ? '34,197,94' : '239,68,68';
            const labelClass = row.marker === 'king' ? 'sl-gold' : row.marker === 'flip' ? 'sl-viol' : 'sl-dim';
            const prefix = row.marker === 'king' ? '★' : row.marker === 'flip' ? '⇅' : '';
            return [
              <div key={`${row.strike}-l`} className={labelClass} style={{ alignSelf: 'center' }}>
                {prefix}{row.strike}
              </div>,
              ...row.alphas.map((a, i) => (
                <div
                  key={`${row.strike}-${i}`}
                  style={{
                    height: 22, borderRadius: 3, background: `rgba(${rgb},${a})`,
                    border:
                      row.marker === 'king' && i === 0 ? '1.5px solid #ffb800'
                      : row.marker === 'flip' ? '1px dashed rgba(167,139,250,.7)'
                      : undefined,
                    borderBottom: row.marker === 'spot' ? '1.5px dashed rgba(248,113,113,.8)' : undefined,
                    boxShadow: row.marker === 'king' && i === 0 ? '0 0 10px rgba(255,184,0,.5)' : undefined,
                  }}
                />
              )),
            ];
          })}
        </div>
        <div className="sl-dim sl-mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginTop: 8, paddingLeft: 47 }}>
          {HEAT_EXPIRIES.map((e) => <span key={e}>{e}</span>)}
        </div>
        <div className="sl-mono" style={{ display: 'flex', gap: 10, fontSize: 9.5, marginTop: 8, flexWrap: 'wrap' }}>
          <span className="sl-bull">■ call-dominant · pin</span>
          <span className="sl-bear">■ put-dominant · accelerate</span>
          <span className="sl-gold">★ King</span>
          <span className="sl-bear">┄ spot</span>
          <span className="sl-viol">┄ flip</span>
        </div>
      </div>
    </section>
  );
}

/** Section 06 — Flow deep-dive. */
function FlowDive() {
  return (
    <section className="sl-sec sl-2col">
      <div className="sl-panel" style={{ flex: 1.15, padding: '14px 16px', width: '100%', overflowX: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 8 }}>
          <span className="sl-mut">flow tape · smart-filtered · sample session</span>
        </div>
        <table className="sl-mono" style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse', minWidth: 480 }}>
          <thead>
            <tr className="sl-dim" style={{ textAlign: 'left' }}>
              <th style={{ padding: '4px 6px' }}>time</th><th>contract</th><th>size</th><th>prem</th><th>side</th><th>read</th>
            </tr>
          </thead>
          <tbody>
            {FLOW_ROWS.map((r) => (
              <tr
                key={r.time}
                style={{
                  background: r.flag ? 'rgba(52,211,153,.05)' : r.side === 'bid' ? 'rgba(248,113,113,.04)' : undefined,
                }}
              >
                <td style={{ padding: '5px 6px' }}>{r.time}</td>
                <td>{r.contract}</td>
                <td>{r.size}</td>
                <td>{r.prem}</td>
                <td className={r.side === 'ask' ? 'sl-bull' : 'sl-bear'}>{r.sideLabel}</td>
                <td className={r.flag ? 'sl-gold' : 'sl-dim'}>{r.read}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ flex: 1 }}>
        <div className="sl-kicker">Flow · the tape, filtered</div>
        <h3 style={{ fontSize: 22, fontWeight: 800, margin: '8px 0' }}>Flow without the firehose.</h3>
        <p className="sl-mut" style={{ fontSize: 14, lineHeight: 1.6 }}>
          Raw tape is noise. Solyra clusters sweeps, tags likely opens vs. closes, and only flags
          flow that agrees — or violently disagrees — with dealer positioning. When three ask-side
          sweeps hit the same strike dealers are short, you get one clear flag, not 400 rows.
        </p>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 8 }}>↳ coming to early access</div>
      </div>
    </section>
  );
}

/** Section 07 — Council deep-dive. */
function CouncilDive() {
  return (
    <section className="sl-sec sl-2col">
      <div style={{ flex: 1 }}>
        <div className="sl-kicker">Council · seven agents, one verdict</div>
        <h3 style={{ fontSize: 22, fontWeight: 800, margin: '8px 0' }}>
          Your own research desk, arguing so you don&rsquo;t have to.
        </h3>
        <p className="sl-mut" style={{ fontSize: 14, lineHeight: 1.6 }}>
          A bull and a bear debate every ticker with live evidence. A risk officer stress-tests
          the loser&rsquo;s best point. Personas — scalper, swing, income — each get their own plan.
          You read one page: verdict, levels, plan, and what would change the Council&rsquo;s mind.
        </p>
        <div className="sl-dim" style={{ fontSize: 12, marginTop: 8 }}>
          ↳ every debate archived · every verdict graded against what actually happened
        </div>
      </div>
      <div className="sl-panel" style={{ flex: 1, padding: 16, width: '100%' }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 180, background: 'rgba(52,211,153,.06)', border: '1px solid rgba(52,211,153,.25)', borderRadius: 9, padding: 10 }}>
            <div className="sl-bull" style={{ fontSize: 10, letterSpacing: '1.5px' }}>BULL · {COUNCIL.bull.score}</div>
            <div className="sl-mut" style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 5 }}>{COUNCIL.bull.quote}</div>
          </div>
          <div style={{ flex: 1, minWidth: 180, background: 'rgba(248,113,113,.05)', border: '1px solid rgba(248,113,113,.25)', borderRadius: 9, padding: 10 }}>
            <div className="sl-bear" style={{ fontSize: 10, letterSpacing: '1.5px' }}>BEAR · {COUNCIL.bear.score}</div>
            <div className="sl-mut" style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 5 }}>{COUNCIL.bear.quote}</div>
          </div>
        </div>
        <div style={{ border: '1px solid rgba(255,184,92,.3)', background: 'rgba(255,184,92,.05)', borderRadius: 9, padding: '10px 12px' }}>
          <div className="sl-gold" style={{ fontSize: 10, letterSpacing: '1.5px' }}>VERDICT · RISK-CHECKED</div>
          <div style={{ fontSize: 12.5, marginTop: 4 }}>{COUNCIL.verdict}</div>
        </div>
        <div className="sl-dim sl-mono" style={{ display: 'flex', gap: 6, marginTop: 12, fontSize: 10, flexWrap: 'wrap' }}>
          {COUNCIL.personas.map((p) => (
            <span key={p} style={{ border: '1px solid rgba(255,255,255,.12)', borderRadius: 99, padding: '2px 9px' }}>{p}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

export function ModuleDives() {
  return (
    <>
      <GammaMapDive />
      <FlowDive />
      <CouncilDive />
    </>
  );
}
```

- [ ] **Step 2: Create `DailyRhythm.tsx`**

```tsx
import { RHYTHM } from './fixtures';

/** Section 08 — Learn → Do → Act, one market day (spec §4.8). */
export function DailyRhythm() {
  return (
    <section className="sl-sec" id="learn" style={{ background: 'linear-gradient(180deg, transparent, rgba(255,150,70,.03))' }}>
      <h2 className="sl-h2">One market day with Solyra.</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, marginTop: 20 }}>
        {RHYTHM.map((card) => (
          <div
            key={card.phase}
            className="sl-tile"
            style={{ padding: 18, borderColor: card.phase === 'DO' ? 'rgba(255,184,92,.3)' : undefined }}
          >
            <div className="sl-gold sl-mono" style={{ fontSize: 12 }}>{card.time} · {card.phase}</div>
            <h3 style={{ fontSize: 16, margin: '8px 0' }}>{card.title}</h3>
            <p className="sl-mut" style={{ fontSize: 13, lineHeight: 1.55, margin: 0 }}>{card.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Mount in `LandingPage.tsx`** — after `<ChartShowcase />` add `<ModuleDives />` then `<DailyRhythm />` (imports from `@/components/landing/ModuleDives` and `@/components/landing/DailyRhythm`).

- [ ] **Step 4: Verify** — `npm run build` passes. Dev-check: heatmap shows green rows above red rows with a gold-bordered King cell; flow table shows the ⚑ cluster row highlighted; Council shows bull/bear/verdict cards; rhythm shows three cards. Flow dive shows "coming to early access" (spec §6 honesty rule).

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/landing/ModuleDives.tsx platform/src/components/landing/DailyRhythm.tsx platform/src/routes/LandingPage.tsx
git commit -m "feat: landing module deep-dives (gamma map, flow, council) + daily rhythm"
```

---

### Task 7: Waitlist form (TDD), FAQ + footer, final page assembly

**Files:**
- Create: `platform/src/components/landing/waitlist.ts`
- Test: `platform/src/components/landing/waitlist.test.ts`
- Create: `platform/src/components/landing/WaitlistSection.tsx`
- Create: `platform/src/components/landing/LandingFAQ.tsx`
- Modify: `platform/src/routes/LandingPage.tsx` (final composition)

**Interfaces:**
- Consumes: `POST /api/waitlist` (Task 1 contract), `FAQ` fixture.
- Produces: `validateEmail(email: string): boolean`; `submitWaitlist(email: string, source: string): Promise<void>` (throws `Error` with a user-readable message on any failure); `<WaitlistSection />` (id `waitlist`); `<LandingFAQ />` (id `faq`).

- [ ] **Step 1: Write the failing tests**

Create `platform/src/components/landing/waitlist.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { submitWaitlist, validateEmail } from './waitlist';

describe('validateEmail', () => {
  it('accepts a normal address', () => {
    expect(validateEmail('trader@example.com')).toBe(true);
  });
  it('rejects garbage', () => {
    expect(validateEmail('not-an-email')).toBe(false);
    expect(validateEmail('a@b')).toBe(false);
    expect(validateEmail('')).toBe(false);
  });
});

describe('submitWaitlist', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('POSTs email + source + empty honeypot and resolves on 200', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await submitWaitlist('Trader@Example.com', 'landing-hero');

    expect(fetchMock).toHaveBeenCalledWith('/api/waitlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'trader@example.com', source: 'landing-hero', website: '' }),
    });
  });

  it('throws the server detail on a non-2xx response (loud failure)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'too many attempts — try again later' }), { status: 429 }),
    ));
    await expect(submitWaitlist('a@b.co', 'landing')).rejects.toThrow(/too many attempts/);
  });

  it('throws a readable message on network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(submitWaitlist('a@b.co', 'landing')).rejects.toThrow(/could not reach/i);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (in `platform/`): `npx vitest run src/components/landing/waitlist.test.ts`
Expected: FAIL — cannot resolve `./waitlist`.

- [ ] **Step 3: Implement `waitlist.ts`**

```ts
/** Waitlist client for POST /api/waitlist. All failures throw a
 *  user-readable Error — the form must SHOW it (Rule 3.7: no fake success). */

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

export function validateEmail(email: string): boolean {
  return EMAIL_RE.test(email.trim());
}

export async function submitWaitlist(email: string, source: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch('/api/waitlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim().toLowerCase(), source, website: '' }),
    });
  } catch {
    throw new Error('Could not reach the server — check your connection and retry.');
  }
  if (!res.ok) {
    let detail = `signup failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body — keep the status-code message
    }
    throw new Error(detail);
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/components/landing/waitlist.test.ts`
Expected: 5 passed.

- [ ] **Step 5: Create `WaitlistSection.tsx`**

```tsx
import { useState, type FormEvent } from 'react';
import { submitWaitlist, validateEmail } from './waitlist';

type Status = 'idle' | 'submitting' | 'done';

/** Section 09 — waitlist capture. Errors are always VISIBLE (Rule 3.7). */
export function WaitlistSection() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!validateEmail(email)) {
      setError('Enter a valid email address.');
      return;
    }
    setStatus('submitting');
    try {
      await submitWaitlist(email, 'landing');
      setStatus('done');
    } catch (err) {
      setStatus('idle');
      setError((err as Error).message);
    }
  }

  return (
    <section
      className="sl-sec"
      id="waitlist"
      style={{ textAlign: 'center', background: 'radial-gradient(ellipse 60% 80% at 50% 100%, rgba(255,150,70,.1), transparent)' }}
    >
      <div
        aria-hidden
        style={{
          width: 74, height: 37, margin: '6px auto 14px', borderRadius: '74px 74px 0 0',
          background: 'radial-gradient(ellipse at 50% 100%, #ffd9a0, #ff8a4d 60%, transparent 78%)',
        }}
      />
      <h2 style={{ fontSize: 'clamp(22px, 3vw, 28px)', fontWeight: 800, margin: 0 }}>Be there at first light.</h2>
      <p className="sl-mut" style={{ fontSize: 15, margin: '10px auto 20px', maxWidth: 480 }}>
        Early access opens in small cohorts. Founding members shape the modules — and keep
        founder pricing for life.
      </p>
      {status === 'done' ? (
        <div className="sl-bull" style={{ fontSize: 15, fontWeight: 600 }} data-testid="waitlist-success">
          You&rsquo;re on the list. One email when your cohort opens.
        </div>
      ) : (
        <form onSubmit={onSubmit} style={{ display: 'inline-flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@email.com"
            aria-label="Email address"
            data-testid="waitlist-email"
            style={{
              border: '1px solid rgba(255,255,255,.15)', background: 'var(--sl-panel)',
              borderRadius: 8, padding: '10px 18px', fontSize: 13, color: 'var(--sl-text)', minWidth: 240,
            }}
          />
          <button type="submit" className="sl-cta" disabled={status === 'submitting'} data-testid="waitlist-submit">
            {status === 'submitting' ? 'Joining…' : 'Join the waitlist'}
          </button>
        </form>
      )}
      {error && (
        <div className="sl-bear" role="alert" data-testid="waitlist-error" style={{ fontSize: 13, marginTop: 10 }}>
          {error}
        </div>
      )}
      <div className="sl-dim" style={{ fontSize: 12, marginTop: 12 }}>No spam. One email when your cohort opens.</div>
    </section>
  );
}
```

- [ ] **Step 6: Create `LandingFAQ.tsx`**

```tsx
import { FAQ } from './fixtures';

/** Section 10 — FAQ + footer. */
export function LandingFAQ() {
  return (
    <section className="sl-sec" id="faq">
      <div style={{ display: 'flex', gap: 40, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 280 }}>
          {FAQ.map((item) => (
            <div key={item.q} style={{ borderTop: '1px solid rgba(255,255,255,.07)', padding: '13px 0', fontSize: 13 }}>
              <b>{item.q}</b>
              <div className="sl-mut" style={{ marginTop: 4 }}>{item.a}</div>
            </div>
          ))}
        </div>
        <div className="sl-dim" style={{ width: 220 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <div className="sl-sun" style={{ width: 16, height: 16 }} />
            <span style={{ fontWeight: 800, letterSpacing: '2px', color: 'var(--sl-text)' }}>SOLYRA</span>
          </div>
          <div style={{ fontSize: 12, lineHeight: 2 }}>
            <a href="#modules" style={{ color: 'inherit', textDecoration: 'none' }}>Modules</a> ·{' '}
            <a href="#learn" style={{ color: 'inherit', textDecoration: 'none' }}>Learn</a> ·{' '}
            <a href="#faq" style={{ color: 'inherit', textDecoration: 'none' }}>FAQ</a>
            <br />Privacy · Terms · Disclosures
            <br />© 2026 Solyra
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 7: Final `LandingPage.tsx` composition**

```tsx
/**
 * Solyra public landing page — spec:
 * docs/superpowers/specs/2026-07-05-solyra-landing-page-design.md
 * Rendered (a) at /welcome always, (b) by AuthGate for signed-out visitors
 * in firebase mode. Must not require auth or Firebase.
 */
import '@/components/landing/landing.css';
import { LandingNav } from '@/components/landing/LandingNav';
import { Hero } from '@/components/landing/Hero';
import { BentoGrid } from '@/components/landing/BentoGrid';
import { ChartShowcase } from '@/components/landing/ChartShowcase';
import { ModuleDives } from '@/components/landing/ModuleDives';
import { DailyRhythm } from '@/components/landing/DailyRhythm';
import { WaitlistSection } from '@/components/landing/WaitlistSection';
import { LandingFAQ } from '@/components/landing/LandingFAQ';

export default function LandingPage() {
  return (
    <main className="solyra-landing" data-testid="landing-page">
      <LandingNav />
      <Hero />
      <BentoGrid />
      <ChartShowcase />
      <ModuleDives />
      <DailyRhythm />
      <WaitlistSection />
      <LandingFAQ />
    </main>
  );
}
```

- [ ] **Step 8: Verify** — `npx vitest run` (all platform unit tests pass) and `npm run build` (passes). Dev-check `/welcome` end-to-end scroll: 10 sections in spec order; submitting a bad email shows the inline error; submitting a good one against the running dev API shows the success state.

- [ ] **Step 9: Commit**

```bash
git add platform/src/components/landing platform/src/routes/LandingPage.tsx
git commit -m "feat: landing waitlist form, FAQ, and full page assembly"
```

---

### Task 8: E2E smoke, lint, proof-number fill, PR

**Files:**
- Create: `platform/tests/landing.spec.ts`
- Possibly modify: `platform/src/components/landing/fixtures.ts` (proof number)

**Interfaces:**
- Consumes: `data-testid="landing-page"`, `waitlist-email`, `waitlist-submit`, `waitlist-error` from Tasks 2/7.

- [ ] **Step 1: Write the e2e spec**

Create `platform/tests/landing.spec.ts`:

```ts
import { expect, test } from '@playwright/test';

// Landing page smoke — runs against the dev server (open auth mode), where
// /welcome is the always-public preview route.
test.describe('Solyra landing page', () => {
  test('renders all key sections at /welcome', async ({ page }) => {
    await page.goto('/welcome');
    await expect(page.getByTestId('landing-page')).toBeVisible();
    await expect(page.getByRole('heading', { name: /know why the market moves/i })).toBeVisible();
    await expect(page.getByText('Everything that moves the market. One surface.')).toBeVisible();
    await expect(page.getByText(/charts that show the/i)).toBeVisible();
    await expect(page.getByText('One market day with Solyra.')).toBeVisible();
    await expect(page.getByText('Be there at first light.')).toBeVisible();
    // Public module names only — competitor names must never appear.
    await expect(page.getByText(/heatseeker|flowseeker|skylit/i)).toHaveCount(0);
  });

  test('waitlist form rejects an invalid email with a visible error', async ({ page }) => {
    await page.goto('/welcome');
    await page.getByTestId('waitlist-email').fill('not-an-email');
    await page.getByTestId('waitlist-submit').click();
    await expect(page.getByTestId('waitlist-error')).toContainText(/valid email/i);
  });
});
```

- [ ] **Step 2: Run the e2e**

Run (in `platform/`, with `npm run dev` running in another shell — or `PLAYWRIGHT_START_VITE=1`): `npx playwright test tests/landing.spec.ts --project=chromium`
Expected: 2 passed.

- [ ] **Step 3: Fill the proof number from real data (spec §6)**

Run from repo root:

```bash
./scripts/db_query_cr.sh -q "SELECT ROUND(100.0 * SUM(CASE WHEN outcome = 'HIT' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 0) AS hit_pct, COUNT(*) AS graded FROM signal_metrics WHERE outcome IN ('HIT','WRONG')"
```

- If the query returns a non-null `hit_pct` with a meaningful sample (`graded` ≥ 100): set `BENTO.proof.hitRatePct` in `fixtures.ts` to that integer and append the sample size to `proof.caption` (e.g. `'… · N graded signals'`). Commit message: `chore: fill landing proof tile from signal_metrics`.
- If unavailable/small sample: leave `hitRatePct: null` (the tile already renders honestly without a number). Do not invent a value.
- Column-name check: if `signal_metrics` uses a different outcome column, inspect with `./scripts/db_query_cr.sh -q "SELECT column_name FROM information_schema.columns WHERE table_name='signal_metrics'"` and adapt — the rule is HIT / (HIT+WRONG), NOISE excluded.

- [ ] **Step 4: Full gate**

Run: `make test` (repo root) → passes.
Run (in `platform/`): `npm run lint` → clean. `npm run build` → passes. `npx vitest run` → passes.

- [ ] **Step 5: Commit + PR**

```bash
git add platform/tests/landing.spec.ts platform/src/components/landing/fixtures.ts
git commit -m "test: landing page e2e smoke + proof tile data"
git push -u origin feature/solyra-landing
gh pr create --base main --title "feat: Solyra public landing page + waitlist API" --body "Implements docs/superpowers/specs/2026-07-05-solyra-landing-page-design.md — public /welcome landing route, signed-out front door, waitlist endpoint + table, 10 marketing sections with app-faithful gamma visuals. Deployment note: apply gcp/schema.sql (waitlist_signups) via the apply-schema-migrations Cloud Run job before flipping firebase-mode traffic."
```

PR description must include the capacity note (Rule 0): waitlist endpoint = 1 INSERT per request, rate-limited 5/10min/IP, no scheduled jobs, no new Cloud Run resources → no capacity/cost impact.

---

## Deployment notes (post-merge, not part of this plan's tasks)

1. Apply schema: run the `apply-schema-migrations` Cloud Run job so `waitlist_signups` exists BEFORE the new image serves traffic (the endpoint 503s loudly until then).
2. The landing page goes live for signed-out visitors only when the service runs `AUTH_MODE=firebase`. In `iap` mode the edge still blocks anonymous visitors — exposing the landing publicly on the IAP service requires an IAP exception and is out of scope here.
3. Before any public marketing push: register `solyra.ai`/`.com`, USPTO check (spec §2), and rename the internal Heatseeker/Flowseeker tabs (spec §8, tracked separately).

## Self-review notes

- Spec coverage: §2 naming (Global Constraints + e2e negative check), §3 direction (Tasks 3–6), §4 sections 01–10 (Tasks 3–7), §5 fidelity (Tasks 4–6 exact colors/styles), §6 honesty (null proof tile + "coming to early access" Flow label + "sample session" labels), §7 architecture (Tasks 1–2: public route, waitlist API/table, no Firebase requirement, reduced motion in Task 3), §9 success criteria (Task 8 e2e).
- Types consistent: `WaitlistBody{email,source,website}` ↔ `submitWaitlist` body ↔ tests; fixture shapes ↔ component consumption; testids ↔ e2e.
- No placeholders: every file's full content is present; the one data-dependent value (proof %) has an explicit two-branch procedure, not a TBD.
