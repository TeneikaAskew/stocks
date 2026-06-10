import { useQueryClient } from '@tanstack/react-query';
import { LogOut } from 'lucide-react';
import { useUser } from '@/hooks/useUser';
import { firebaseSignOut } from '@/lib/firebase';

/**
 * Sign-out control in the header. Renders only in `firebase` mode for a
 * signed-in user (never in iap/open). Signing out triggers Firebase's
 * auth-state change → `<AuthGate>` returns to the login screen.
 */
export function SignOutButton() {
  const qc = useQueryClient();
  const { authMode, email, isSignedIn } = useUser();
  if (authMode !== 'firebase' || !isSignedIn) return null;

  const onSignOut = async () => {
    try {
      await firebaseSignOut();
    } finally {
      qc.clear(); // drop cached data tied to the previous identity
    }
  };

  return (
    <div className="flex items-center gap-2 text-[11px] text-[var(--on-surface-variant)]">
      {email && <span className="hidden max-w-[160px] truncate sm:inline">{email}</span>}
      <button
        type="button"
        onClick={onSignOut}
        data-testid="sign-out"
        aria-label="Sign out"
        title="Sign out"
        className="flex items-center gap-1 hover:text-[var(--on-surface)]"
      >
        <LogOut size={13} />
      </button>
    </div>
  );
}
