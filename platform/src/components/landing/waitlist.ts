/** Waitlist client for POST /api/waitlist. All failures throw a
 *  user-readable Error — the form must SHOW it (Rule 3.7: no fake success). */

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

export function validateEmail(email: string): boolean {
  return EMAIL_RE.test(email.trim());
}

export async function submitWaitlist(email: string, source: string, website = ''): Promise<void> {
  let res: Response;
  try {
    res = await fetch('/api/waitlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim().toLowerCase(), source, website }),
    });
  } catch {
    throw new Error('Could not reach the server — check your connection and retry.');
  }
  if (!res.ok) {
    let detail = `signup failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // non-JSON error body — keep the status-code message
    }
    throw new Error(detail);
  }
}
