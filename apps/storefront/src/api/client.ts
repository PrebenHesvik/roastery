import createClient from 'openapi-fetch';
import type { paths } from './schema';

/**
 * The one client (ADR 0019). Its base is `/api` on this origin: Vite's dev proxy strips the
 * prefix. It is resolved against the origin because `Request` takes no relative URL outside a
 * browser page (the tests).
 */
export const API_BASE = '/api';

export const api = createClient<paths>({
  // Looked up per call, so a test's network mock (MSW) that patches fetch later is used.
  fetch: (request) => globalThis.fetch(request),
  baseUrl: new URL(API_BASE, window.location.origin).href.replace(/\/$/, ''),
});
