import { useCallback, useMemo, useSyncExternalStore } from 'react';

/** The cart in `localStorage` (ADR 0019): ids and quantities only, never a price. */
export const CART_KEY = 'sydvest.cart';
export const CART_VERSION = 1;
export const COUNTRIES = ['NO', 'SE', 'DK', 'FI'] as const;
export type Country = (typeof COUNTRIES)[number];

export interface CartItem {
  productId: string;
  qty: number;
}
export interface Cart {
  version: typeof CART_VERSION;
  country: Country;
  items: CartItem[];
}

export const emptyCart = (): Cart => ({ version: CART_VERSION, country: 'NO', items: [] });

const isCountry = (value: unknown): value is Country =>
  COUNTRIES.some((country) => country === value);

function asItem(value: unknown): CartItem | null {
  if (typeof value !== 'object' || value === null) return null;
  const { productId, qty } = value as Record<string, unknown>;
  if (typeof productId !== 'string' || productId === '') return null;
  if (typeof qty !== 'number' || !Number.isInteger(qty) || qty < 1) return null;
  return { productId, qty };
}

/** The stored text as a cart; anything that does not parse or has another version is dropped. */
export function parseCart(raw: string | null): Cart {
  if (raw === null) return emptyCart();
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== 'object' || value === null) return emptyCart();
    const { version, country, items } = value as Record<string, unknown>;
    if (version !== CART_VERSION || !isCountry(country) || !Array.isArray(items)) {
      return emptyCart();
    }
    const list: CartItem[] = [];
    for (const each of items as unknown[]) {
      const item = asItem(each);
      if (item === null) return emptyCart();
      list.push(item);
    }
    return { version: CART_VERSION, country, items: list };
  } catch {
    return emptyCart();
  }
}

// Storage that throws (a private window, blocked site data) leaves the cart in memory for the
// visit.
let memory: string | null = null;
let useMemory = false;
const listeners = new Set<() => void>();

function readRaw(): string | null {
  if (useMemory) return memory;
  try {
    return window.localStorage.getItem(CART_KEY);
  } catch {
    useMemory = true;
    return memory;
  }
}

function writeRaw(raw: string): void {
  if (!useMemory) {
    try {
      window.localStorage.setItem(CART_KEY, raw);
    } catch {
      useMemory = true;
    }
  }
  if (useMemory) memory = raw;
  listeners.forEach((listener) => {
    listener();
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener('storage', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
}

export interface CartApi {
  cart: Cart;
  count: number;
  add: (productId: string, qty?: number) => void;
  setQty: (productId: string, qty: number) => void;
  remove: (productId: string) => void;
  setCountry: (country: Country) => void;
  clear: () => void;
}

export function useCart(): CartApi {
  const raw = useSyncExternalStore(subscribe, readRaw, () => null);
  const cart = useMemo(() => parseCart(raw), [raw]);

  // Edits start from the stored text, not from a render's snapshot, so two quick clicks add up.
  const edit = useCallback((change: (current: Cart) => Cart) => {
    writeRaw(JSON.stringify(change(parseCart(readRaw()))));
  }, []);

  return {
    cart,
    count: cart.items.reduce((sum, item) => sum + item.qty, 0),
    add: (productId, qty = 1) => {
      edit((current) => {
        const found = current.items.some((item) => item.productId === productId);
        const items = found
          ? current.items.map((item) =>
              item.productId === productId ? { ...item, qty: item.qty + qty } : item,
            )
          : [...current.items, { productId, qty }];
        return { ...current, items };
      });
    },
    setQty: (productId, qty) => {
      edit((current) => ({
        ...current,
        items:
          qty > 0
            ? current.items.map((item) => (item.productId === productId ? { ...item, qty } : item))
            : current.items.filter((item) => item.productId !== productId),
      }));
    },
    remove: (productId) => {
      edit((current) => ({
        ...current,
        items: current.items.filter((item) => item.productId !== productId),
      }));
    },
    setCountry: (country) => {
      edit((current) => ({ ...current, country }));
    },
    clear: () => {
      edit((current) => ({ ...current, items: [] }));
    },
  };
}
