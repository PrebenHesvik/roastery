import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { productList, renderAt } from '../test/fixtures';

interface Attempt {
  key: string | null;
  outcome: string;
}

const attempts: Attempt[] = [];
let status: 'placed' | 'paid' = 'placed';

const problem = (code: string, statusCode: number) =>
  HttpResponse.json(
    { type: 'about:blank', title: code, status: statusCode, code },
    { status: statusCode, headers: { 'Content-Type': 'application/problem+json' } },
  );

const server = setupServer(
  http.get('/api/products', () => HttpResponse.json(productList('NO'))),
  http.get('/api/orders/tok-1', () =>
    HttpResponse.json({
      order_id: 'O-000001',
      status,
      country: 'NO',
      day: '2026-11-07',
      lines: [
        {
          line_id: 'L-1',
          product_id: 'P-10',
          qty: 1,
          unit_price: { amount: '129.00', currency: 'NOK' },
          display_unit_price: { amount: '129.00', currency: 'NOK' },
        },
      ],
      total: { amount: '129.00', currency: 'NOK' },
      currency: 'NOK',
      display_total: { amount: '129.00', currency: 'NOK' },
    }),
  ),
  http.post('/api/sandbox/payments', async ({ request }) => {
    const { outcome } = (await request.json()) as { outcome: string };
    attempts.push({ key: request.headers.get('Idempotency-Key'), outcome });
    if (outcome === 'decline') return problem('ProviderRefused', 402);
    if (outcome === 'outage') return problem('ProviderUnavailable', 503);
    status = 'paid';
    return HttpResponse.json(
      {
        payment_id: 'PAY-1',
        order_id: 'O-000001',
        status: 'paid',
        amount: { amount: '129.00', currency: 'NOK' },
      },
      { status: 201 },
    );
  }),
);

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  attempts.length = 0;
  status = 'placed';
});
afterAll(() => {
  server.close();
});

describe('the test payment', () => {
  it('takes a new key for each attempt after a stored reply, and keeps it through an outage', async () => {
    const user = userEvent.setup();
    renderAt('/pay/tok-1');

    expect(
      await screen.findByRole('heading', { name: 'A test payment. No money moves.' }),
    ).toBeInTheDocument();

    await user.click(await screen.findByRole('button', { name: 'Decline' }));
    expect(await screen.findByText('The payment was declined.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Decline' }));
    expect(await screen.findByText('The payment was declined.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Simulate outage' }));
    expect(await screen.findByText('The payment service did not answer.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('The payment service did not answer.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByRole('heading', { name: 'Status: Paid' })).toBeInTheDocument();

    expect(attempts.map((each) => each.outcome)).toEqual([
      'decline',
      'decline',
      'outage',
      'outage',
      'approve',
    ]);
    const [decline1, decline2, outage1, outage2, approve] = attempts.map((each) => each.key);
    // A declined reply is stored under its key, so the second decline is a new attempt.
    expect(decline2).not.toBe(decline1);
    // An outage is not stored: "try again" resends the same key.
    expect(outage2).toBe(outage1);
    expect(new Set([decline1, decline2, outage1, approve]).size).toBe(4);
  });

  it('says plainly when no order has the link', async () => {
    server.use(http.get('/api/orders/nope', () => problem('UnknownToken', 404)));
    renderAt('/orders/nope');
    expect(
      await screen.findByRole('heading', { name: 'No order has this link.' }),
    ).toBeInTheDocument();
  });
});
