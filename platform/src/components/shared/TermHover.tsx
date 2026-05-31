import { useState } from 'react';
import { useGammaTerm } from '../../hooks/useGammaGlossary';

interface TermHoverProps {
  /**
   * Key into the gamma glossary (e.g. 'king', 'flip', 'vex'). Must
   * match a key in `lib/gamma_glossary.GAMMA_TERMS`. Unknown keys
   * render the wrapped text plain — no tooltip, no error.
   */
  term: string;
  /**
   * The text the user sees inline. Usually the term's canonical name
   * (`<TermHover term="king">King</TermHover>`), but can also be a
   * narrative phrase (`<TermHover term="flip">regime divider</TermHover>`).
   */
  children: React.ReactNode;
  /**
   * Optional className for the wrapping span. The component supplies
   * the default dotted-underline styling; passing className extends it.
   */
  className?: string;
}

/**
 * Inline tooltip that surfaces the canonical definition of a gamma
 * term on hover.
 *
 * Loads the full glossary once at app boot via `useGammaGlossary`
 * (zero per-hover network calls). The tooltip card shows the
 * canonical name + short_definition + long_definition + math when
 * the user hovers; click also opens it so touch devices work.
 *
 * IMPORTANT — what's NOT shown: cross-framework aliases (Stratalyst,
 * Heatseeker, SqueezeMetrics, SpotGamma). Those live in the Python
 * `GAMMA_TERMS` dict for internal use only and are stripped by the
 * `/api/glossary/gamma` endpoint server-side. The public UI speaks
 * our canonical vocabulary only — see Phase 0 of
 * docs/plans/HEATSEEKER_STYLE_GAMMA_PLAN.md §1.7.5.
 *
 * Usage:
 *   <TermHover term="king">King</TermHover>
 *   <TermHover term="flip">Gamma Flip</TermHover>
 *   <TermHover term="vex">VEX</TermHover>
 */
export function TermHover({ term, children, className }: TermHoverProps) {
  const definition = useGammaTerm(term);
  const [open, setOpen] = useState(false);

  // No glossary loaded yet OR unknown key → render plain text.
  // This is the load-bearing graceful-degrade path — a page should
  // never block on the glossary fetch, and a typo in the term key
  // should surface as "no underline" rather than a runtime error.
  if (!definition) {
    return <span className={className}>{children}</span>;
  }

  return (
    <span
      className={`relative inline-block cursor-help border-b border-dotted border-current/40 ${className ?? ''}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={() => setOpen((v) => !v)}
      tabIndex={0}
      role="button"
      aria-describedby={open ? `termhover-${term}` : undefined}
    >
      {children}
      {open && (
        <span
          id={`termhover-${term}`}
          role="tooltip"
          className="
            absolute left-1/2 z-50 -translate-x-1/2
            mt-2 w-80 max-w-[90vw] rounded-lg
            border border-[var(--border)]
            bg-[var(--surface-2)] p-3 text-left
            text-sm font-normal text-[var(--text)]
            shadow-xl
          "
          style={{ top: '100%' }}
          // Stop the click from bubbling so clicking inside the tooltip
          // doesn't immediately close it.
          onClick={(e) => e.stopPropagation()}
        >
          <div className="mb-1 font-semibold text-[var(--text)]">
            {definition.canonical}
          </div>
          <div className="mb-2 text-[var(--text-muted)]">
            {definition.short_definition}
          </div>
          {definition.long_definition !== definition.short_definition && (
            <div className="mb-2 text-xs text-[var(--text-muted)] leading-relaxed">
              {definition.long_definition}
            </div>
          )}
          {definition.math && (
            <div className="mt-2 rounded bg-[var(--surface)] p-2 font-mono text-xs text-[var(--text-muted)]">
              {definition.math}
            </div>
          )}
        </span>
      )}
    </span>
  );
}
