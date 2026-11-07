/**
 * One idempotency key per attempt (ADR 0019). The key is kept in `sessionStorage` with a hash of
 * the body it was made for, so a reload or a second click resends the same key, and a changed body
 * is a new attempt. The body itself is never kept: it holds the guest's contact.
 */

interface Stored {
  key: string;
  digest: string;
}

const PREFIX = 'sydvest.attempt.';

function read(slot: string): Stored | null {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + slot);
    if (raw === null) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== 'object' || value === null) return null;
    const { key, digest } = value as Record<string, unknown>;
    return typeof key === 'string' && typeof digest === 'string' ? { key, digest } : null;
  } catch {
    return null;
  }
}

function write(slot: string, stored: Stored): void {
  try {
    window.sessionStorage.setItem(PREFIX + slot, JSON.stringify(stored));
  } catch {
    // the key lasts for this call only
  }
}

/** A hex SHA-256 of the body's JSON. */
export async function digestOf(body: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(body));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** The key for this body: the stored one if it was made for the same body, else a new one. */
export async function keyFor(slot: string, body: unknown): Promise<string> {
  const digest = await digestOf(body);
  const stored = read(slot);
  if (stored !== null && stored.digest === digest) return stored.key;
  const key = crypto.randomUUID();
  write(slot, { key, digest });
  return key;
}

/** Forget the attempt: the server stored its reply, so the next try is a new attempt. */
export function dropKey(slot: string): void {
  try {
    window.sessionStorage.removeItem(PREFIX + slot);
  } catch {
    // nothing kept
  }
}
