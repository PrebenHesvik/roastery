import { useQuery } from '@tanstack/react-query';
import type { Country } from '../lib/cart';
import { api } from './client';

/** The catalogue for a country; a problem+json reply throws, carrying its `code`. */
export function useProducts(country: Country) {
  return useQuery({
    queryKey: ['products', country],
    queryFn: async () => {
      const { data, error } = await api.GET('/products', { params: { query: { country } } });
      if (data === undefined) throw new Error(error.code);
      return data;
    },
  });
}
