import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CART_KEY, MAX_QTY, parseCart, useCart } from './cart';

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

  it('holds a quantity over 999 to 999', () => {
    const raw = JSON.stringify({
      version: 1,
      country: 'NO',
      items: [{ productId: 'P-10', qty: 1000 }],
    });
    expect(parseCart(raw).items).toEqual([{ productId: 'P-10', qty: MAX_QTY }]);
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

  it('holds a set or added quantity to 1..999', () => {
    const { result } = renderHook(() => useCart());
    act(() => {
      result.current.add('P-10', 5000);
      result.current.add('P-20');
    });
    expect(result.current.cart.items).toEqual([
      { productId: 'P-10', qty: 999 },
      { productId: 'P-20', qty: 1 },
    ]);
    act(() => {
      result.current.add('P-10');
      result.current.setQty('P-20', 1000);
    });
    expect(result.current.cart.items).toEqual([
      { productId: 'P-10', qty: 999 },
      { productId: 'P-20', qty: 999 },
    ]);
    act(() => {
      result.current.setQty('P-20', 0);
    });
    expect(result.current.cart.items).toEqual([{ productId: 'P-10', qty: 999 }]);
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
