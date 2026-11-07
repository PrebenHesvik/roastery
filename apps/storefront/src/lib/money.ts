/** An amount as the API sends it: the number as text, and its currency. */
export interface Amount {
  amount: string;
  currency: string;
}

const DECIMAL = /^-?\d+(\.\d+)?$/;
const formats = new Map<string, Intl.NumberFormat>();

function formatFor(currency: string): Intl.NumberFormat {
  let format = formats.get(currency);
  if (format === undefined) {
    format = new Intl.NumberFormat('en', { style: 'currency', currency });
    formats.set(currency, format);
  }
  return format;
}

/**
 * The amount for the page. The decimal string goes to Intl as text, so no float is made and
 * nothing is rounded here (ADR 0018, 0019).
 */
export function formatMoney({ amount, currency }: Amount): string {
  if (!DECIMAL.test(amount)) throw new RangeError(`not a decimal amount: ${amount}`);
  return formatFor(currency).format(amount as `${number}`);
}
