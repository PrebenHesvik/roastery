import type { Key } from '../i18n/t';
import type { Country } from './cart';

/**
 * The shop's category tree, by the ids the API sends. The API gives a product's category id and
 * no tree, so the tree is kept here: Beans (Filter, Espresso), Equipment (Kettles, Grinders, with
 * Hand grinders under Grinders).
 */
export interface Shelf {
  slug: string;
  label: Key;
  parent: string | null;
  categories: readonly string[];
}

export const SHELVES: readonly Shelf[] = [
  { slug: 'beans', label: 'shelf.beans', parent: null, categories: ['CAT-11', 'CAT-12'] },
  { slug: 'filter', label: 'shelf.filter', parent: 'beans', categories: ['CAT-11'] },
  { slug: 'espresso', label: 'shelf.espresso', parent: 'beans', categories: ['CAT-12'] },
  {
    slug: 'equipment',
    label: 'shelf.equipment',
    parent: null,
    categories: ['CAT-21', 'CAT-22', 'CAT-23'],
  },
  { slug: 'kettles', label: 'shelf.kettles', parent: 'equipment', categories: ['CAT-23'] },
  {
    slug: 'grinders',
    label: 'shelf.grinders',
    parent: 'equipment',
    categories: ['CAT-21', 'CAT-22'],
  },
];

export function shelfNamed(slug: string | null): Shelf | null {
  return SHELVES.find((shelf) => shelf.slug === slug) ?? null;
}

/** The deepest shelf that holds the category, for a product's crumbs. */
export function shelfOf(categoryId: string): Shelf | null {
  const holding = SHELVES.filter((shelf) => shelf.categories.includes(categoryId));
  return holding.find((shelf) => shelf.parent !== null) ?? holding[0] ?? null;
}

export interface Place {
  name: Key;
  currency: 'NOK' | 'SEK' | 'DKK' | 'EUR';
}

export const PLACES: Readonly<Record<Country, Place>> = {
  NO: { name: 'country.NO', currency: 'NOK' },
  SE: { name: 'country.SE', currency: 'SEK' },
  DK: { name: 'country.DK', currency: 'DKK' },
  FI: { name: 'country.FI', currency: 'EUR' },
};

/** The roast as a step range on the seven-step scale, light to dark. */
export function roastSteps(roast: string): readonly [number, number] | null {
  switch (roast) {
    case 'light':
      return [0, 1];
    case 'medium-light':
      return [1, 2];
    case 'medium':
      return [2, 3];
    case 'medium-dark':
      return [3, 4];
    case 'dark':
      return [5, 6];
    default:
      return null;
  }
}
