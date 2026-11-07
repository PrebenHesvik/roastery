/** An amount as the API sends it: the number as text, and its currency. */
export interface Amount {
  amount: string;
  currency: string;
}

const DECIMAL = /^-?\d+(\.\d+)?$/;
const formats = new Map<string, Intl.NumberFormat>();

function formatFor(currency: string, display: 'symbol' | 'name'): Intl.NumberFormat {
  const id = `${currency}:${display}`;
  let format = formats.get(id);
  if (format === undefined) {
    format = new Intl.NumberFormat('en', { style: 'currency', currency, currencyDisplay: display });
    formats.set(id, format);
  }
  return format;
}

function checked(amount: string): `${number}` {
  if (!DECIMAL.test(amount)) throw new RangeError(`not a decimal amount: ${amount}`);
  return amount as `${number}`;
}

/**
 * The amount for the page. The decimal string goes to Intl as text, so no float is made and
 * nothing is rounded here (ADR 0018, 0019).
 */
export function formatMoney({ amount, currency }: Amount): string {
  return formatFor(currency, 'symbol').format(checked(amount));
}

/** The amount as it is read aloud: "129.00 Norwegian kroner". */
export function spokenMoney({ amount, currency }: Amount): string {
  return formatFor(currency, 'name').format(checked(amount));
}

/** The formatted amount in parts, so the page can set the digits tabular and the rest as is. */
export function moneyParts({ amount, currency }: Amount): Intl.NumberFormatPart[] {
  return formatFor(currency, 'symbol').formatToParts(checked(amount));
}
