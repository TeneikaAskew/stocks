# Solyra Landing Page — Design Spec

**Date:** 2026-07-05
**Status:** Approved in brainstorm (visual companion session, mockup `full-landing-v3.html`)
**Scope:** Public marketing/landing page. The in-app dashboard (`/`) refresh is a follow-up
project with its own spec — this document covers the landing page only.

## 1. Context & goals

The platform (React app in `platform/`) is a deep trading-intelligence product with no public
front door — sign-in drops straight into the auth-gated dashboard. Inspired by skylit.ai
(agent-first trading terminal marketing site), we are adding a public landing page that:

- tells the **learn → do → act** story of acting on market movement,
- showcases the platform's real capabilities (gamma positioning, options flow, 7-agent AI
  insights, signals, catalysts, movement explanation),
- captures **waitlist signups** (future-product framing; no pricing tiers yet),
- is **not** a skylit replica — same genre, own identity.

## 2. Brand decision

- **Working name: Solyra** — sol (sun) + lyra (constellation). Verified via web search
  2026-07-05: no company, product, or domain collision found (nearest: Solara, Solira,
  Solaya, Sola — all distinct). **Before public launch:** register `solyra.ai` /
  `solyra.com` and run a USPTO trademark search. Rename is a wordmark swap if needed.
- **Rejected directions** (user feedback): trading-jargon names (Confluence, Catalyst),
  soft-literal nature names (Dawnlit, Skyglow), names with death/medical connotations
  (Vigil, Murmur). Liked-but-taken: Velio, Skyra.
- **Logo mark:** radial-gradient sun disc (amber → deep orange) + `SOLYRA` wordmark,
  letter-spaced caps. Waitlist section reuses a rising-sun half-disc motif.
- **Tagline family:** "Know why the market moves. Before it moves." (hero) ·
  "Be there at first light." (waitlist).

### Module naming (public ↔ internal)

Plain descriptive names — **no themed name family** (user decision). "Heatseeker" /
"Flowseeker" cannot be used publicly (Skylit's module names; internal tabs that borrow
them should be renamed before launch).

| Public name | Internal feature |
|---|---|
| The Brief | premarket brief (`/api/dashboard/brief`) |
| Gamma Map | gamma levels + Swing-Mode grid + Profiles ladder (`/api/options/*/levels`, grid endpoints) |
| Flow | options flow tape (currently mock — see §6 honesty rules) |
| Council | 7-agent insight pipeline (`/api/insights/report/*`) |
| Movement Read | movement statement (`/api/movement-statement`, flag-gated) |
| Playbook / Signals | playbook cards + signal monitor (`/api/playbook/*`, `/api/signals/*`) |

## 3. Design direction

Hybrid of two explored directions ("Living Terminal" hero × "Command Bento" body), chosen
over a story-scroll alternative. Core principles:

1. **The product is the hero.** A live-looking agent terminal types out a premarket
   sequence in the hero. No abstract illustrations.
2. **Real product visuals only.** Every chart/tile on the page mirrors the app's actual
   visual language (see §5). A visitor who joins sees the app they were promised.
3. **Obsidian Analyst base + dawn accent.** Existing dark token system
   (`platform/src/index.css`) with a new Solyra accent: amber→orange gradient
   (`#ffb85c → #ff7a4d`), used for CTAs, section chips, module labels, hero glow.
   Existing semantic colors unchanged (bull green, bear red, King gold `#ffb800`,
   Gate blue, Flip violet).
4. **Learn is first-class.** Education framing (plain-language, glossary-linked) is a
   selling point, not a help page.

## 4. Page structure (10 sections, approved order)

1. **Nav** — sun-disc + SOLYRA; links: Platform, Modules, Learn, FAQ; Sign in; amber
   "Request access" button.
2. **Hero** — kicker "THE AI ANALYST DESK FOR MARKET MOVEMENT"; H1 "Know why the market
   moves. **Before it moves.**" (gradient on second line); subcopy naming dealer
   positioning, flow, catalysts → brief, signals, reasons; CTAs "Join the waitlist" +
   "See a live day ↓" (scrolls to §8); trust microcopy. Right: **live agent terminal**
   panel — timestamped lines from `brief`, `gamma`, `flow`, `council`, `catalyst` agents
   ending in "your brief is ready"; typing animation on scroll-into-view.
3. **Command bento** — "Everything that moves the market. One surface." 6 tiles:
   - **Gamma Map** (2-row tile): diverging horizontal strike ladder — center zero line,
     green bars right (+γ), purple bars left (−γ), red dashed spot line, ★K/◆G/⇅F row
     markers (mirrors Profiles tab).
   - **Council · AI verdict**: LONG/SHORT + bull-vs-bear score bar.
   - **Catalysts · next up**: time-ranked events with impact tags.
   - **Movement Read**: one-sentence excerpt.
   - **Signals · today**: fired/armed list with R multiples.
   - **Proof · walk-forward**: out-of-sample hit rate + grading note.
4. **The chart view** — "Charts that show the **why**." Full-width SPY candlestick chart
   with gamma levels in the app's exact line styles: **solid gold King, dotted blue Gate,
   dashed violet Flip**, VWAP curve, King-rejection annotation, signal marker with
   entry flag.
5. **Module deep-dive: Gamma Map** — copy ("See the wall before price hits it") + visual:
   strike × expiry **Swing-Mode grid** in true colors (green call-dominant, red
   put-dominant, gold-bordered King cell, dashed spot/flip rows) with legend.
6. **Module deep-dive: Flow** — "Flow without the firehose." Smart-filtered tape table
   (time, contract, size, premium, side, read) with sweep-cluster flags.
7. **Module deep-dive: Council** — "Your own research desk, arguing so you don't have
   to." Bull card vs Bear card with scores, risk-checked verdict box (entry/target/
   invalidation/sizing), persona plan chips (scalper/swing/income). Note: debates
   archived, verdicts graded.
8. **Learn → Do → Act** — "One market day with Solyra." Three cards: 07:00 The Brief
   (learn), 09:30 the open/signals (do), 16:00 Movement Read + journal (act).
9. **Waitlist capture** — rising-sun motif; "Be there at first light."; cohort framing +
   founder-pricing promise; email input + submit; anti-spam microcopy.
10. **FAQ + footer** — 3 starter QAs (not advice; no options experience needed; data
    provenance/graded signals) + minimal footer (Privacy, Terms, Disclosures).

## 5. Real-visual fidelity map

Landing visuals must match these app surfaces (verified in code 2026-07-05):

| Landing element | App source of truth |
|---|---|
| Bento Gamma Map ladder | `platform/src/components/options/ProfilesTab.tsx` D3 diverging bars (green +/purple −, red dashed spot, King/Gate badges) |
| Deep-dive gamma grid | `platform/src/components/options/SwingMode.tsx` strike×expiry CSS grid (green/red cells, gold King cell, dashed spot & flip rows) |
| Chart overlay styles | `platform/src/routes/ChartsPage.tsx:283-319` — King solid gold `#f59e0b` w2, Gate dotted blue `#3b82f6`, Flip dashed violet `#a78bfa` |
| Ladder alternative (if needed) | `platform/src/components/options/TrinityTab.tsx` put/call ladders |

## 6. Content honesty rules (Rule 3.7 alignment)

- Marketing numbers shown (hit rate, premium totals, verdict scores) must be **real,
  reproducible values** from the platform's data (e.g., actual walk-forward results) or
  clearly representative sample-day data — never fabricated claims. Copy that promises
  "we publish the hit rates" creates an obligation: the page's proof numbers must trace
  to `walk_forward_results` / `signal_metrics`.
- **Flow module caveat:** the in-app flow tape is currently mock (no tick feed). Landing
  copy must not promise live flow until the feed ships — either label Flow "coming to
  early access" or gate that section until real.
- Static marketing page: no silent-fallback risk, but the waitlist endpoint must fail
  loudly (user sees an error, not a fake success).

## 7. Architecture & implementation constraints

- **Placement:** public route inside `platform/` (served to signed-out visitors; "Sign in"
  routes into the existing AuthGate flow). Rationale: reuses the token system, fonts, and
  primitives so landing and app can't drift; avoids a second deploy surface. The exact
  route/auth wiring (e.g., `/` public + `/app` gated, vs `/welcome`) is decided in the
  implementation plan.
- **Waitlist capture:** `POST /api/waitlist` → new `waitlist_signups` table (email,
  created_at, source, user_agent; unique on email; idempotent upsert). Basic abuse
  guards (rate limit per IP, honeypot field). No third-party form service.
- **No new financial math on the page** — all numbers come from existing `lib/`-backed
  endpoints or are baked static sample data clearly marked in code as marketing fixtures.
- **Performance:** landing must load fast logged-out (no Firebase init, no React Query
  towers) — lazy-load the app bundle only after sign-in.
- Typing animation and scroll effects: CSS/light JS only; respect `prefers-reduced-motion`.

## 8. Out of scope (deferred)

- In-app dashboard (`/`) refresh — separate follow-up spec.
- Pricing tiers/plan comparison (waitlist stage only).
- Renaming internal Heatseeker/Flowseeker tabs (required before public launch; tracked
  separately).
- Real flow data feed; sector rotation; testimonials/partners (no users yet).
- Final trademark/domain registration (user action).

## 9. Success criteria

- A first-time visitor can say what Solyra does within 5 seconds (hero) and name two
  concrete capabilities within 30 (bento).
- Every visual on the page is recognizable inside the product after sign-up.
- Waitlist signup works end-to-end and failures are visible.
- Page renders correctly logged-out, on mobile, and honors reduced motion.

## 10. Reference

- Approved mockup: `.superpowers/brainstorm/8724-1783282547/content/full-landing-v3.html`
  (session artifact, gitignored — layout/copy/colors in this spec are the durable record).
- Comparables reviewed: skylit.ai (structure inspiration), SpotGamma, Tradytics
  (standard SaaS shape to differentiate from).
