/**
 * Global `window.fetch` wrapper that attaches the Firebase ID token to every
 * same-origin `/api/*` request.
 *
 * Why a global monkeypatch: the app makes ~60 backend calls across ~30 files as
 * bare relative `fetch('/api/...')` with no central client and no
 * WebSocket/EventSource. Wrapping the one network primitive covers every call
 * site (current and future) with zero per-file edits. It is a strict no-op
 * unless auth mode is `firebase`, so iap/open/local behaviour is unchanged.
 */
import { getIdToken } from './firebase';
import { getAuthMode } from './runtimeConfig';

// Reachable pre-auth — must match api/auth._OPEN_API_PREFIXES.
const OPEN_PREFIXES = ['/api/health', '/api/me', '/api/config/firebase'];

let _installed = false;
let _onUnauthorized: (() => void) | null = null;

/** Register a callback invoked when a gated /api/* call returns 401. */
export function setOnUnauthorized(cb: () => void): void {
  _onUnauthorized = cb;
}

function pathOf(input: RequestInfo | URL): string {
  try {
    if (typeof input === 'string') {
      return input.startsWith('http') ? new URL(input).pathname : input;
    }
    if (input instanceof URL) return input.pathname;
    if (input instanceof Request) return new URL(input.url, window.location.origin).pathname;
  } catch {
    /* fall through */
  }
  return '';
}

function isGatedApiPath(path: string): boolean {
  if (!path.startsWith('/api/')) return false;
  return !OPEN_PREFIXES.some((p) => path === p || path.startsWith(p));
}

export function installAuthFetch(): void {
  if (_installed || typeof window === 'undefined') return;
  _installed = true;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    if (getAuthMode() !== 'firebase' || !isGatedApiPath(pathOf(input))) {
      return nativeFetch(input, init);
    }

    const token = await getIdToken().catch(() => null);
    let nextInit = init;
    if (token) {
      // Merge onto existing headers (preserve X-Admin-Token, Content-Type, …).
      const headers = new Headers(
        init?.headers ?? (input instanceof Request ? input.headers : undefined),
      );
      headers.set('Authorization', `Bearer ${token}`);
      nextInit = { ...init, headers };
    }

    const resp = await nativeFetch(input, nextInit);
    if (resp.status === 401 && _onUnauthorized) _onUnauthorized();
    return resp;
  };
}
