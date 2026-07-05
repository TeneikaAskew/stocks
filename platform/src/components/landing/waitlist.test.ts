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
