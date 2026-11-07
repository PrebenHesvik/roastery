import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { pay, placeOrder, type CheckoutBody } from './actions';

const keys: (string | null)[] = [];
const statuses: number[] = [];

const problem = (code: string, status: number) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status, code },
    { status, headers: { 'Content-Type': 'application/problem+json' } },
  );

const placed = {
  order_id: 'O-000001',
  country: 'NO',
  total: { amount: '129.00', currency: 'NOK' },
  token: 'tok-1',
  currency: 'NOK',
  display_total: { amount: '129.00', currency: 'NOK' },
};

const paid = {
  payment_id: 'PAY-1',
  order_id: 'O-000001',
  status: 'paid',
  amount: { amount: '129.00', currency: 'NOK' },
};

const server = setupServer(
  http.post('/api/checkout', ({ request }) => {
    keys.push(request.headers.get('Idempotency-Key'));
    const status = statuses.shift() ?? 201;
    return status === 201
      ? HttpResponse.json(placed, { status })
      : problem('InternalError', status);
  }),
  http.post('/api/sandbox/payments', ({ request }) => {
    keys.push(request.headers.get('Idempotency-Key'));
    const status = statuses.shift() ?? 201;
    switch (status) {
      case 201:
        return HttpResponse.json(paid, { status });
      case 402:
        return problem('ProviderRefused', status);
      case 503:
        return problem('ProviderUnavailable', status);
      default:
        return problem('InternalError', status);
    }
  }),
);

const body: CheckoutBody = {
  country: 'NO',
  items: [{ product_id: 'P-10', qty: 1 }],
  total: { amount: '129.00', currency: 'NOK' },
  name: 'Kari Nordmann',
  email: 'kari@example.invalid',
  street: 'Strandkaien 1',
  postal_code: '5003',
  city: 'Bergen',
};

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  keys.length = 0;
  statuses.length = 0;
});
afterAll(() => {
  server.close();
});

describe('placeOrder', () => {
  it('keeps the key after a 500, so the retry replays the kept reply, not a second order', async () => {
    statuses.push(500, 500, 201);
    expect((await placeOrder(body)).kind).toBe('problem');
    expect((await placeOrder(body)).kind).toBe('problem');
    expect((await placeOrder(body)).kind).toBe('placed');
    expect(keys).toHaveLength(3);
    expect(new Set(keys).size).toBe(1);
    // placed: the key is dropped, so the next order is a new attempt
    await placeOrder(body);
    expect(keys[3]).not.toBe(keys[0]);
  });
});

describe('pay', () => {
  it('drops the key on a decline, and keeps it on an outage or any other 5xx', async () => {
    statuses.push(402, 503, 500, 201);
    expect((await pay('tok-1', 'approve')).kind).toBe('declined');
    expect((await pay('tok-1', 'approve')).kind).toBe('outage');
    expect((await pay('tok-1', 'approve')).kind).toBe('problem');
    expect((await pay('tok-1', 'approve')).kind).toBe('paid');
    const [declined, outage, failed, approved] = keys;
    expect(outage).not.toBe(declined);
    expect(failed).toBe(outage);
    expect(approved).toBe(outage);
  });
});
