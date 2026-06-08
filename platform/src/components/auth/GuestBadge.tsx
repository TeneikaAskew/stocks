import { useQueryClient } from '@tanstack/react-query';
import { LogOut } from 'lucide-react';
import { GUEST_EMAIL, useUser } from '@/hooks/useUser';

/**
 * Small "Staging · guest" pill with an exit affordance. Renders ONLY when the
 * current identity is the staging guest sentinel, so it never appears in prod
 * (real Google email) or local dev (null). Exiting clears the bypass cookie
 * and returns the user to the passcode screen.
 */
export function GuestBadge() {
  const qc = useQueryClient();
  const { email } = useUser();
  if (email !== GUEST_EMAIL) return null;

  const exit = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } finally {
      await qc.invalidateQueries({ queryKey: ['me'] });
    }
  };

  return (
    <div
      data-testid="guest-badge"
      className="flex items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[11px] text-[var(--on-surface-variant)]"
    >
      <span className="font-medium uppercase tracking-[0.06em]">Staging · guest</span>
      <button
        type="button"
        onClick={exit}
        data-testid="guest-exit"
        aria-label="Exit staging"
        title="Exit staging"
        className="flex items-center gap-1 text-[var(--on-surface-variant)] hover:text-[var(--on-surface)]"
      >
        <LogOut size={12} />
      </button>
    </div>
  );
}
