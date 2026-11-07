import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { CartItem, Country } from '../lib/cart';
import { api } from './client';
import type { components } from './schema';

export type Schemas = components['schemas'];
export type Listed = Schemas['ListedProduct'];
export type QuoteBody = Schemas['Quote'];
export type OrderBody = Schemas['Order'];
export type BeanDetails = Schemas['BeanDetails'];
export type EquipmentDetails = Schemas['EquipmentDetails'];

/** A problem+json reply, as an error the pages switch on by `code` (ADR 0016). */
export class Problem extends Error {
  readonly code: string;
  readonly status: number;
  readonly body: Readonly<Record<string, unknown>>;

  constructor(body: unknown, status: number) {
    const fields = (typeof body === 'object' && body !== null ? body : {}) as Record<
      string,
      unknown
    >;
    const code = typeof fields['code'] === 'string' ? fields['code'] : 'NetworkError';
    super(code);
    this.name = 'Problem';
    this.code = code;
    this.status = status;
    this.body = fields;
  }
}

export const isBeans = (details: Listed['details']): details is BeanDetails => 'roast' in details;

/** A 4xx is an answer, not a hiccup: only a network error or a 5xx is tried again. */
const retry = (count: number, error: Error) =>
  count < 2 && (!(error instanceof Problem) || error.status >= 500);

export function useProducts(country: Country) {
  return useQuery({
    queryKey: ['products', country],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/products', {
        params: { query: { country } },
      });
      if (data === undefined) throw new Problem(error, response.status);
      return data;
    },
    placeholderData: keepPreviousData,
    retry,
  });
}

export function useProduct(id: string, country: Country) {
  return useQuery({
    queryKey: ['product', id, country],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/products/{product_id}', {
        params: { path: { product_id: id }, query: { country } },
      });
      if (data === undefined) throw new Problem(error, response.status);
      return data;
    },
    placeholderData: keepPreviousData,
    retry,
  });
}

export const quoteKey = (country: Country, items: readonly CartItem[]) => [
  'quote',
  country,
  items.map((item) => `${item.productId}x${String(item.qty)}`).join(','),
];

/** The server's price for the cart (ADR 0017): the page never adds a price up itself. */
export function useQuote(country: Country, items: readonly CartItem[]) {
  return useQuery({
    queryKey: quoteKey(country, items),
    queryFn: async () => {
      const { data, error, response } = await api.POST('/quote', {
        body: {
          country,
          items: items.map((item) => ({ product_id: item.productId, qty: item.qty })),
        },
      });
      if (data === undefined) throw new Problem(error, response.status);
      return data;
    },
    enabled: items.length > 0,
    placeholderData: keepPreviousData,
    retry,
  });
}

export const orderKey = (token: string) => ['order', token];

export function useOrder(token: string) {
  return useQuery({
    queryKey: orderKey(token),
    queryFn: async () => {
      const { data, error, response } = await api.GET('/orders/{token}', {
        params: { path: { token } },
      });
      if (data === undefined) throw new Problem(error, response.status);
      return data;
    },
    retry,
  });
}
