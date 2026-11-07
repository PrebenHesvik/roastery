import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { CART_KEY } from '../lib/cart';
import { norwegianQuote, productList, renderAt, storeCart } from '../test/fixtures';

interface Sent {
  key: string | null;
  body: { total: { amount: string }; items: unknown[] } & Record<string, unknown>;
}

const sent: Sent[] = [];
const order = {
  order_id: 'O-000001',
  status: 'placed',
  country: 'NO',
  day: '2026-11-07',
  lines: [],
  total: { amount: '139.00', currency: 'NOK' },
  currency: 'NOK',
  display_total: { amount: '139.00', currency: 'NOK' },
};

const server = setupServer(
  http.get('/api/products', () => HttpResponse.json(productList('NO'))),
  http.post('/api/quote', () => HttpResponse.json(norwegianQuote(1, '129.00', '129.00'))),
  http.post('/api/checkout', async ({ request }) => {
    const body = (await request.json()) as Sent['body'];
    sent.push({ key: request.headers.get('Idempotency-Key'), body });
    if (body.total.amount === '129.00') {
      // The campaign ended between the bag and the click.
      return HttpResponse.json(
        {
          type: 'about:blank',
          title: 'Price changed',
          status: 409,
          code: 'PriceChanged',
          confirmed: { amount: '129.00', currency: 'NOK' },
          quote: norwegianQuote(1, '139.00', '139.00'),
        },
        { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
      );
    }
    return HttpResponse.json(
      {
        order_id: 'O-000001',
        country: 'NO',
        total: { amount: '139.00', currency: 'NOK' },
        token: 'tok-1',
        currency: 'NOK',
        display_total: { amount: '139.00', currency: 'NOK' },
      },
      { status: 201 },
    );
  }),
  http.get('/api/orders/tok-1', () => HttpResponse.json(order)),
);

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  sent.length = 0;
});
afterAll(() => {
  server.close();
});

describe('checkout', () => {
  it('shows a changed price, and confirming it is a new attempt at the new total', async () => {
    const user = userEvent.setup();
    storeCart({ country: 'NO', items: [{ productId: 'P-10', qty: 1 }] });
    renderAt('/checkout');

    expect(await screen.findByRole('radio', { name: /Norway/ })).toBeChecked();
    await user.type(screen.getByLabelText('Full name'), 'Kari Nordmann');
    await user.type(screen.getByLabelText('E-mail'), 'kari@example.invalid');
    await user.type(screen.getByLabelText('Street address'), 'Strandkaien 1');
    await user.type(screen.getByLabelText('Postal code'), '5003');
    await user.type(screen.getByLabelText('City'), 'Bergen');
    await user.click(await screen.findByRole('button', { name: /Place order/ }));

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('The price has changed.')).toBeInTheDocument();
    expect(alert).toHaveTextContent('The total is now NOK 139.00');
    // The summary follows the server's new quote.
    const summary = screen.getByRole('complementary', { name: 'Your order' });
    expect(within(summary).getAllByText('139.00 Norwegian kroner').length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: 'Place the order at the new total' }));
    expect(
      await screen.findByRole('heading', { name: 'A test payment. No money moves.' }),
    ).toBeInTheDocument();

    expect(sent.map((each) => each.body.total.amount)).toEqual(['129.00', '139.00']);
    const [first, second] = sent;
    expect(first?.key).toBeTruthy();
    expect(second?.key).toBeTruthy();
    expect(second?.key).not.toBe(first?.key);
    // The cart holds no price, and is emptied once the order is placed.
    expect(JSON.parse(window.localStorage.getItem(CART_KEY) ?? '{}')).toMatchObject({ items: [] });
  });

  it('asks for what is missing before it calls the shop', async () => {
    const user = userEvent.setup();
    storeCart({ country: 'NO', items: [{ productId: 'P-10', qty: 1 }] });
    renderAt('/checkout');

    await user.click(await screen.findByRole('button', { name: /Place order/ }));
    expect(screen.getByLabelText('Full name')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Full name')).toHaveFocus();
    expect(sent).toHaveLength(0);
  });
});
