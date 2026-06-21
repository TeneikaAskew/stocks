import { AlertTriangle } from 'lucide-react';

interface DemoDataBannerProps {
  /** Optional second line explaining what's mock and what (if anything) is real. */
  detail?: string;
  className?: string;
}

/**
 * Prominent, consistent "this surface is not live" disclaimer.
 *
 * Render at the TOP of any page/section whose data is mock/placeholder, right
 * where the live word/icons would otherwise imply real data. One shared banner
 * keeps the disclaimer unmistakable and uniform across every demo surface.
 */
export function DemoDataBanner({ detail, className = '' }: DemoDataBannerProps) {
  return (
    <div
      role="status"
      className={`flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-[var(--warn)] ${className}`}
    >
      <AlertTriangle size={14} className="shrink-0" />
      <span className="font-semibold">Demo data — not live.</span>
      {detail && <span className="text-[var(--warn)]/80">{detail}</span>}
    </div>
  );
}
