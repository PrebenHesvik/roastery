import { describe, expect, it } from 'vitest';
import { t } from './t';

describe('t', () => {
  it('returns the copy', () => {
    expect(t('incl_vat')).toBe('incl. VAT');
    expect(t('vat_excise_and_fees')).toContain('excise');
  });

  it('fills {name} from vars', () => {
    expect(t('import_vat_estimate', { country: 'Sweden', amount: 'SEK 12.00' })).toContain(
      'Sweden is due on delivery: about SEK 12.00.',
    );
  });
});
