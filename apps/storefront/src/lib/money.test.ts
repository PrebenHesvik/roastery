import { describe, expect, it } from 'vitest';
import { formatMoney } from './money';

describe('formatMoney', () => {
  it('formats the decimal text with the currency', () => {
    expect(formatMoney({ amount: '129.00', currency: 'NOK' })).toBe('NOK\u00a0129.00');
    expect(formatMoney({ amount: '11.09', currency: 'EUR' })).toBe('€11.09');
  });

  it('does not lose digits a float would', () => {
    expect(formatMoney({ amount: '9007199254740993.10', currency: 'NOK' })).toContain(
      '9,007,199,254,740,993.10',
    );
  });

  it('refuses text that is not a decimal', () => {
    expect(() => formatMoney({ amount: '1e3', currency: 'NOK' })).toThrow(RangeError);
  });
});
