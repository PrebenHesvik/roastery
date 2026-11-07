import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CART_KEY, parseCart, useCart } from './cart';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('parseCart', () => {
  it('reads a good cart', () => {
    const raw = JSON.stringify({
      version: 1,
      country: 'SE',
      items: [{ productId: 'P-10', qty: 2 }],
    });
    expect(parseCart(raw).items).toEqual([{ productId: 'P-10', qty: 2 }]);
  });

  it.each([
    ['null', null],
    ['not json', '{'],
    ['another version', JSON.stringify({ version: 2, country: 'NO', items: [] })],
    ['an unknown country', JSON.stringify({ version: 1, country: 'US', items: [] })],
    [
      'a zero qty',
      JSON.stringify({ version: 1, country: 'NO', items: [{ productId: 'P-1', qty: 0 }] }),
    ],
    [
      'a fractional qty',
      JSON.stringify({ version: 1, country: 'NO', items: [{ productId: 'P-1', qty: 1.5 }] }),
    ],
  ])('drops %s', (_, raw) => {
    expect(parseCart(raw)).toEqual({ version: 1, country: 'NO', items: [] });
  });
});

describe('useCart', () => {
  it('adds, counts and stores ids and quantities only', () => {
    const { result } = renderHook(() => useCart());
    act(() => {
      result.current.add('P-10');
      result.current.add('P-10');
      result.current.add('P-20');
    });
    expect(result.current.count).toBe(3);
    expect(JSON.parse(window.localStorage.getItem(CART_KEY) ?? 'null')).toEqual({
      version: 1,
      country: 'NO',
      items: [
        { productId: 'P-10', qty: 2 },
        { productId: 'P-20', qty: 1 },
      ],
    });
  });

  it('still works for the visit when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const { result } = renderHook(() => useCart());
    act(() => {
      result.current.add('P-10');
    });
    expect(result.current.count).toBe(1);
  });
});
