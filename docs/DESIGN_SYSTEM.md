# Design System Document

## 1. Overview & Creative North Star: "The Obsidian Analyst"

The creative direction for this design system is **"The Obsidian Analyst."** Unlike generic fintech dashboards that rely on cluttered grids and neon distractions, this system treats data as a high-value asset curated within a premium, architectural space.

By moving away from the bright greens of the reference material and adopting a sophisticated **Vibrant Blue (`#8bceff`)** core, we shift the brand narrative from "algorithmic noise" to "authoritative intelligence." The layout breaks the traditional "box-in-a-box" template by utilizing intentional asymmetry — where sidebar navigation and content cards breathe through whitespace rather than rigid lines. This is a system of depth, layering, and editorial precision designed for the high-stakes world of AI-driven trading.

---

## 2. Colors & Surface Philosophy

The palette is anchored in deep charcoals and obsidian blacks, providing a high-contrast stage for critical data points.

### The Palette

- **Primary (Vibrant Blue):** `#8bceff` (Primary) / `#00b2ff` (Container). Used for active states, CTAs, and primary brand accents.
- **Surface Background:** `#111318`. The base "canvas" of the application.
- **Functional Semantics:**
    - **Positive (Bullish):** Standard green — use sparingly and only for market indicators.
    - **Negative (Bearish):** Error (`#ffb4ab`) or standard red.
    - **Warning / Amber:** Tertiary (`#ffb86b`) for previous low markers, neutral zones.
    - *Note: These semantic colors are reserved strictly for market indicators, never for UI decoration.*

### The "No-Line" Rule

Sectioning must **not** be achieved with 1px solid borders. To create a premium, seamless feel, boundaries are defined by tonal shifts.

- Use `surface-container-low` (`#1a1c20`) for secondary panels.
- Use `surface-container-high` (`#282a2e`) for active cards.
- Use `surface-container-highest` (`#333539`) for hover / emphasis.
- Separation is felt through value change, not drawn with lines.

### Signature Textures & Glassmorphism

To avoid a flat "Bootstrap" appearance, use **Glassmorphism** for floating elements like dropdowns or tooltips. Utilize the `surface` color at 60% opacity with a `20px` backdrop-blur.

- **CTAs:** Use a subtle linear gradient from `primary` (`#8bceff`) to `primary-container` (`#00b2ff`) at 135 degrees to add "soul" and dimension.

---

## 3. Typography: Editorial Authority

We use a dual-typeface system to balance technical precision with human readability.

- **Display & Headlines (Space Grotesk):** This typeface provides a technical, "engineered" aesthetic. Use `display-lg` (`3.5rem`) for hero data and `headline-sm` (`1.5rem`) for card titles. Its geometric nature signals modern AI sophistication.
- **Body & Labels (Manrope):** A highly legible sans-serif used for insights and data values. `body-md` (`0.875rem`) is the workhorse for analysis reports.
- **Contrast as Hierarchy:** High-value data (tickers, prices) should always use `on-surface` (`#e2e2e8`) for maximum impact, while metadata uses `on-surface-variant` (`#bdc8d2`).

### Type Scale

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| `display-lg` | 3.5rem (56px) | 700 | Hero prices, tickers |
| `display-md` | 2.5rem (40px) | 700 | Section heroes |
| `display-sm` | 1.75rem (28px) | 700 | KPI values |
| `headline-lg` | 1.5rem (24px) | 600 | Page titles |
| `headline-sm` | 1.125rem (18px) | 600 | Card titles |
| `body-lg` | 1rem (16px) | 400 | Primary body |
| `body-md` | 0.875rem (14px) | 400 | Secondary body |
| `label-md` | 0.75rem (12px) | 500 | Form labels |
| `label-sm` | 0.625rem (10px) | 500 | Uppercase micro-labels, tracking-wider |

---

## 4. Elevation & Depth: Tonal Layering

Traditional shadows feel "muddy" in dark mode. Instead, we use **Tonal Layering** to convey hierarchy.

### The Layering Principle

1. **Level 0 (Base):** `surface` (`#111318`) — app background
2. **Level 1 (Sections):** `surface-container-low` (`#1a1c20`) — sidebar, header
3. **Level 2 (Cards):** `surface-container-high` (`#282a2e`) — KPI cards, panels
4. **Level 3 (Emphasis):** `surface-container-highest` (`#333539`) — active / hover

### Ambient Shadows

For floating modals, use a large `48px` blur with 8% opacity, tinted with the `surface-tint` (`#8bceff`) color. This mimics the "glow" of a high-end monitor rather than a physical shadow.

### The Ghost Border

For accessibility on interactive inputs, use a 1px border with `outline-variant` (`#3e4851`) at **20% opacity**. It should be felt, not seen.

---

## 5. Components

### Buttons

- **Primary:** Gradient fill (`primary` → `primary-container`), `on-primary` text. Border-radius: `md` (`0.375rem`).
- **Secondary:** Ghost style. Transparent fill, `ghost-border` (20% opacity primary color).
- **Tertiary:** Text-only, using `label-md` weight.

### Cards & Data Lists

- **Rule:** Absolute prohibition of divider lines.
- Separate data points using the **Spacing Scale** (8px, 16px, 24px) or by alternating background tones between `surface-container-low` and `surface-container-lowest`.
- **Layout:** Cards should use the `xl` (`0.75rem`) roundedness for a modern, approachable feel.

### KPI Card Anatomy

```
┌─────────────────────────┐
│ MAR 24 CLOSE            │  ← label-sm, uppercase, tracking-wider, on-surface-variant
│                         │
│ $175.31                 │  ← display-sm, Space Grotesk, on-surface
│                         │
│ Regular market close    │  ← body-md, on-surface-variant
└─────────────────────────┘
  Background: surface-container-high (#282a2e)
  Padding: 24px
  Radius: 12px (xl)
  No visible border
```

### Input Fields

- Background: `surface-container-lowest` (`#0c0e12`).
- Focus State: Transition the "Ghost Border" from 20% to 100% `primary` opacity.
- Typography: `body-md` for user input, `label-sm` for floating labels.

### Custom Component: The Agent Pulse

A custom status indicator for AI agents. Instead of a static green dot, use a `primary` blue ring with a soft outer glow (10px blur) to signify "Processing."

---

## 6. Light Mode

The system supports a light mode variant that preserves the Obsidian Analyst philosophy with inverted surfaces.

### Light Mode Palette

- **Surface Background:** `#f8f9fb`
- **Surface Container Low:** `#f0f2f6`
- **Surface Container High:** `#e4e7ee`
- **Surface Container Highest:** `#d8dde6`
- **On-Surface (primary text):** `#1a1c20`
- **On-Surface-Variant (secondary text):** `#485661`
- **Primary Brand (blue):** `#0072c6` (darker for contrast on light)
- **Outline (ghost border):** `#c8cfd8`

### Light Mode Rules

- Same "no-line" rule applies — use tonal shifts between `surface-container-*` levels
- Semantic green / red stay the same (bullish / bearish)
- Charts darken grid lines to `#e4e7ee` for subtlety
- Glass elements use light-tinted blur

---

## 7. Do's and Don'ts

### Do

- **Do** use large amounts of padding (24px+) between cards to ensure complex AI insights don't feel claustrophobic.
- **Do** use `Space Grotesk` for all numerical data to emphasize the technical nature of the platform.
- **Do** use semi-transparent overlays (Glassmorphism) for sidebar navigation to keep the background context visible.
- **Do** support light mode via a theme toggle. Persist preference in `localStorage`.

### Don't

- **Don't** use 100% white (`#FFFFFF`) for text; it causes "halogen glow" eye strain in dark mode. Stick to `on-surface` (`#e2e2e8`).
- **Don't** use green or red for UI elements (buttons, icons, toggles). These colors are strictly reserved for financial performance indicators.
- **Don't** use sharp corners. Every container must follow the roundedness scale to maintain the "premium software" aesthetic.
- **Don't** use standard 1px borders to separate the sidebar from the main content. Use a `surface` to `surface-container-low` transition instead.

---

## 8. Implementation Notes

- All color tokens live in `platform/src/index.css` as CSS custom properties under `:root` (dark) and `[data-theme="light"]` (light).
- Theme state is managed by `platform/src/stores/themeStore.ts` (Zustand) and applied by setting `data-theme` on the `<html>` element.
- Fonts are loaded via Google Fonts CDN at the top of `index.css`: Space Grotesk (700) and Manrope (400, 500, 600).
- Back-compat aliases keep existing `var(--color-accent-blue)` etc. working while the codebase migrates to the new token names.
