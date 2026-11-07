import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import type { Schemas } from '../api/queries';
import { GRINDER, MORNING, productList, renderAt, storeCart } from '../test/fixtures';

const sek = (amount: string) => ({ amount, currency: 'SEK' });
const nok = (amount: string) => ({ amount, currency: 'NOK' });

function swedishQuote(onHand = 55): Schemas['Quote'] {
  return {
    country: 'SE',
    currency: 'SEK',
    day: '2026-11-07',
    scheme: 'export',
    lines: [
      {
        product: MORNING,
        qty: 2,
        unit_price: nok('129.00'),
        percent: 0,
        gross: nok('258.00'),
        vat: nok('0.00'),
        rate: '6',
        on_hand: onHand,
        display_unit_price: sek('121.47'),
        display_gross: sek('242.94'),
      },
      {
        product: GRINDER,
        qty: 1,
        unit_price: nok('899.00'),
        percent: 0,
        gross: nok('899.00'),
        vat: nok('0.00'),
        rate: '25',
        on_hand: 6,
        display_unit_price: sek('846.52'),
        display_gross: sek('846.52'),
      },
    ],
    gross: nok('1157.00'),
    vat: nok('0.00'),
    display_gross: sek('1089.45'),
    vat_display: {
      price_label: 'no_norwegian_vat',
      due_on_delivery: 'import_vat_estimate',
      norwegian_vat: null,
      import_vat: nok('240.23'),
      display_import_vat: sek('226.21'),
    },
  };
}

const quoted: unknown[] = [];
let quote = swedishQuote();

const server = setupServer(
  http.get('/api/products', () => HttpResponse.json(productList('SE'))),
  http.post('/api/quote', async ({ request }) => {
    quoted.push(await request.json());
    return HttpResponse.json(quote);
  }),
);

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  quoted.length = 0;
  quote = swedishQuote();
});
afterAll(() => {
  server.close();
});

describe('the bag', () => {
  it('shows the server’s amounts and sends only ids and quantities', async () => {
    storeCart({
      country: 'SE',
      items: [
        { productId: 'P-10', qty: 2 },
        { productId: 'P-20', qty: 1 },
      ],
    });
    renderAt('/cart');

    const lines = await screen.findAllByRole('listitem');
    const morning = lines.find(
      (line) => within(line).queryByRole('link', { name: 'Morning roast' }) !== null,
    );
    expect(morning).toBeDefined();
    // The line total is the server's, not 2 × 121.47 worked out here.
    expect(within(morning as HTMLElement).getByText('242.94 Swedish kronor')).toBeInTheDocument();
    expect(within(morning as HTMLElement).getByText('121.47 Swedish kronor')).toBeInTheDocument();

    const summary = screen.getByRole('complementary', { name: 'Summary' });
    // Set with its symbol, read aloud with the currency's name.
    expect(within(summary).getByText('1,089.45 Swedish kronor').previousSibling).toHaveTextContent(
      'SEK 1,089.45',
    );
    expect(within(summary).getByText('No Norwegian VAT')).toBeInTheDocument();
    expect(within(summary).getByText('1,157.00 Norwegian kroner')).toBeInTheDocument();
    expect(
      within(summary).getByText(/Import VAT in Sweden is due on delivery: about/),
    ).toHaveTextContent('about SEK 226.21');
    expect(within(summary).getByRole('link', { name: /Check out/ })).toHaveAttribute(
      'href',
      '/checkout',
    );

    expect(quoted).toEqual([
      {
        country: 'SE',
        items: [
          { product_id: 'P-10', qty: 2 },
          { product_id: 'P-20', qty: 1 },
        ],
      },
    ]);
  });

  it('holds checkout back while a line is short of stock', async () => {
    quote = swedishQuote(1);
    storeCart({
      country: 'SE',
      items: [
        { productId: 'P-10', qty: 2 },
        { productId: 'P-20', qty: 1 },
      ],
    });
    renderAt('/cart');

    expect(await screen.findByText('Only 1 of Morning roast left.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check out' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Take 1' })).toBeEnabled();
  });

  it('holds a stored quantity to 999 and stops "+" there', async () => {
    storeCart({
      country: 'SE',
      items: [
        { productId: 'P-10', qty: 5000 },
        { productId: 'P-20', qty: 1 },
      ],
    });
    renderAt('/cart');

    expect(await screen.findByRole('button', { name: 'One more Morning roast' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'One more Hand grinder' })).toBeEnabled();
    expect(quoted).toEqual([
      {
        country: 'SE',
        items: [
          { product_id: 'P-10', qty: 999 },
          { product_id: 'P-20', qty: 1 },
        ],
      },
    ]);
  });

  it('says so when the bag is empty', () => {
    renderAt('/cart');
    expect(screen.getByRole('heading', { name: 'Your bag is empty.' })).toBeInTheDocument();
  });
});
