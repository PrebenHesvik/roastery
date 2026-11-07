import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import App from './App';

const server = setupServer(
  http.get('/api/products', () =>
    HttpResponse.json({
      country: 'NO',
      currency: 'NOK',
      price_label: 'incl_vat',
      products: [
        {
          product: {
            product_id: 'P-10',
            name: 'Morning roast',
            kind: 'beans',
            category_id: 'C-1',
            weight_g: 250,
          },
          details: { weight_g: 250, origin: 'Colombia', roast: 'medium', process: 'washed' },
          unit_price: { amount: '129.00', currency: 'NOK' },
          percent: 15,
          in_stock: true,
          display_price: { amount: '129.00', currency: 'NOK' },
        },
      ],
    }),
  ),
);

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});
afterEach(() => {
  server.resetHandlers();
});
afterAll(() => {
  server.close();
});

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('the app shell', () => {
  it('shows the wordmark, the nav and the products from /api/products', async () => {
    renderAt('/shop');
    expect(screen.getByRole('link', { name: 'Sydvest' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Morning roast' })).toHaveAttribute(
      'href',
      '/shop/P-10',
    );
  });

  it('has a not-found route', () => {
    renderAt('/nowhere');
    expect(screen.getByRole('heading', { name: 'This page does not exist.' })).toBeInTheDocument();
  });
});
