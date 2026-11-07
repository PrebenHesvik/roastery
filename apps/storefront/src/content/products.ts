/**
 * The words for each product, by id (ADR 0019). The API gives the facts (name, origin, process,
 * roast, weight, material, warranty, price, stock); these give the words, from those facts only.
 * Nothing here names a price or a stock level.
 */
export interface ProductCopy {
  /** One line, for a card. */
  line: string;
  /** The product page's paragraphs. */
  body: readonly string[];
  /** How it is brewed or used, in a few words. */
  use: string;
}

export const PRODUCT_COPY: Readonly<Record<string, ProductCopy>> = {
  'P-10': {
    line: 'Ethiopian, washed and light: a bright cup for the dark mornings.',
    body: [
      'Coffee from Ethiopia, washed at the mill and roasted light here in Bergen.',
      'Washing takes the fruit off the bean before it dries, and a light roast leaves the cup clear and bright. It is the one we would put in a filter brewer before the sun is up, which in November is most of the morning.',
      'A 250 g bag.',
    ],
    use: 'For filter and pour-over',
  },
  'P-11': {
    line: 'Brazilian, natural and dark: heavy enough for milk, steady under the tamper.',
    body: [
      'Coffee from Brazil, dried in the whole fruit and roasted dark.',
      'A natural process dries the cherry around the bean, and a dark roast takes that into a heavy, round cup that holds its own under milk. It comes in a 1000 g bag, for the machine that runs every day.',
      'At the counter in Bergen the same coffee is sold loose, weighed out by the gram.',
    ],
    use: 'For espresso',
  },
  'P-12': {
    line: 'Colombian, washed, a medium roast. Not ready to sell yet.',
    body: [
      'Coffee from Colombia, washed, roasted to the middle of the scale, without the caffeine.',
      'It has no price yet, so it cannot be ordered. It will be in the shop when it does.',
      'A 250 g bag.',
    ],
    use: 'For filter, in the evening',
  },
  'P-20': {
    line: 'A hand grinder in wood. Grind just before you brew.',
    body: [
      'A hand grinder with a wooden body. Beans keep longer whole, so grind what the next cup needs and no more.',
      'It carries a 24-month warranty.',
    ],
    use: 'For grinding by hand',
  },
  'P-21': {
    line: 'A steel kettle for pour-over, poured slowly.',
    body: [
      'A pour-over kettle in steel. Heat the water, then pour over the cone at your own pace.',
      'It carries a 12-month warranty.',
    ],
    use: 'For pour-over',
  },
};

const FALLBACK: ProductCopy = { line: '', body: [], use: '' };

export function copyFor(productId: string): ProductCopy {
  return PRODUCT_COPY[productId] ?? FALLBACK;
}
