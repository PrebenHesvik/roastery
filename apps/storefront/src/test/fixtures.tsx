import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import type { Schemas } from '../api/queries';
import { CART_KEY, type Cart } from '../lib/cart';

const amount = (value: string, currency = 'NOK') => ({ amount: value, currency });

export const MORNING: Schemas['ProductInfo'] = {
  product_id: 'P-10',
  name: 'Morning roast',
  kind: 'beans',
  category_id: 'CAT-11',
  weight_g: 250,
};

export const GRINDER: Schemas['ProductInfo'] = {
  product_id: 'P-20',
  name: 'Hand grinder',
  kind: 'equipment',
  category_id: 'CAT-22',
  weight_g: null,
};

/** The catalogue as the API lists it for Sweden. */
export function productList(country: Schemas['ProductList']['country'] = 'SE') {
  const currency = country === 'NO' ? 'NOK' : 'SEK';
  const list: Schemas['ProductList'] = {
    country,
    currency,
    price_label: country === 'NO' ? 'incl_vat' : 'no_norwegian_vat',
    products: [
      {
        product: MORNING,
        details: { weight_g: 250, origin: 'Ethiopia', roast: 'light', process: 'washed' },
        unit_price: amount('129.00'),
        percent: country === 'NO' ? 15 : 0,
        in_stock: true,
        display_price: amount(country === 'NO' ? '129.00' : '121.47', currency),
      },
      {
        product: GRINDER,
        details: { warranty_months: 24, material: 'wood' },
        unit_price: amount('899.00'),
        percent: country === 'NO' ? 25 : 0,
        in_stock: true,
        display_price: amount(country === 'NO' ? '899.00' : '846.52', currency),
      },
    ],
  };
  return list;
}

/** A Norwegian quote for `qty` Morning roasts at `price` kroner each. */
export function norwegianQuote(qty: number, price: string, gross: string): Schemas['Quote'] {
  return {
    country: 'NO',
    currency: 'NOK',
    day: '2026-11-07',
    scheme: 'domestic',
    lines: [
      {
        product: MORNING,
        qty,
        unit_price: amount(price),
        percent: 15,
        gross: amount(gross),
        vat: amount('16.83'),
        rate: null,
        on_hand: 55,
        display_unit_price: amount(price),
        display_gross: amount(gross),
      },
    ],
    gross: amount(gross),
    vat: amount('16.83'),
    display_gross: amount(gross),
    vat_display: {
      price_label: 'incl_vat',
      due_on_delivery: 'nothing',
      norwegian_vat: amount('16.83'),
      import_vat: null,
      display_import_vat: null,
    },
  };
}

export function storeCart(cart: Omit<Cart, 'version'>): void {
  window.localStorage.setItem(CART_KEY, JSON.stringify({ version: 1, ...cart }));
}

export function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
