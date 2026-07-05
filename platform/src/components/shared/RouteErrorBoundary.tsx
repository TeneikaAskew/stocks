/**
 * Per-route error boundary.
 *
 * Wired into every route via React Router's ``errorElement`` prop so a
 * crash on one page (e.g. DashboardPage's ``reference.high.toFixed`` when
 * the API returns a partial payload) shows a contained, recoverable
 * fallback instead of nuking the whole app and the sidebar with it.
 *
 * The default React Router boundary dumps the raw stack into the page —
 * fine for development but ugly for users. This component:
 *   - keeps the AppShell (sidebar + header stay rendered)
 *   - shows a small, themed error card with the route's name
 *   - exposes a "Try again" that pops the user back to the dashboard
 *   - only reveals the technical details behind a "Show details" toggle
 */
import { useState } from 'react';
import { useRouteError, useNavigate, isRouteErrorResponse } from 'react-router-dom';
import { AlertTriangle, RefreshCw, ChevronRight } from 'lucide-react';

export function RouteErrorBoundary() {
  const error = useRouteError();
  const navigate = useNavigate();
  const [showDetails, setShowDetails] = useState(false);

  const { title, message, stack } = describeError(error);

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-2xl rounded-xl border border-amber-500/30 bg-[var(--surface-2)] p-6">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-1 shrink-0 text-[var(--warn)]" size={20} />
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
              {title}
            </h2>
            <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
              This page crashed before it could render. The rest of the
              app is unaffected — try reloading or going back to the
              dashboard.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                onClick={() => window.location.reload()}
                className="flex items-center gap-1.5 rounded bg-[var(--color-accent-blue)] px-3 py-1.5 text-xs font-medium text-[var(--on-brand)] hover:opacity-90"
              >
                <RefreshCw size={12} />
                Reload page
              </button>
              <button
                onClick={() => navigate('/dashboard')}
                className="flex items-center gap-1.5 rounded border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
              >
                Go to dashboard
              </button>
            </div>

            <button
              onClick={() => setShowDetails((s) => !s)}
              className="mt-4 flex items-center gap-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
            >
              <ChevronRight
                size={12}
                className={`transition-transform ${showDetails ? 'rotate-90' : ''}`}
              />
              {showDetails ? 'Hide' : 'Show'} technical details
            </button>

            {showDetails && (
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-[var(--surface-lowest)] p-3 text-[10px] text-[var(--color-text-muted)]">
                {message}
                {stack ? `\n\n${stack}` : ''}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function describeError(error: unknown): { title: string; message: string; stack?: string } {
  // React Router thrown response (404, 401, etc.)
  if (isRouteErrorResponse(error)) {
    return {
      title: `${error.status} ${error.statusText}`,
      message: typeof error.data === 'string' ? error.data : JSON.stringify(error.data, null, 2),
    };
  }
  if (error instanceof Error) {
    return { title: 'Page error', message: error.message, stack: error.stack };
  }
  return { title: 'Page error', message: String(error) };
}
