import type { QuoteBody } from '../api/queries';
import { t } from '../i18n/t';
import { PLACES } from '../lib/catalogue';
import type { Amount } from '../lib/money';
import { Price } from './Price';

/** The import VAT sentence, with the estimate set as a price where the copy names {amount}. */
function Estimate({ country, amount }: { country: string; amount: Amount }) {
  const [before = '', after = ''] = t('import_vat_estimate', { country }).split('{amount}');
  return (
    <p className="totals__note">
      {before}
      <Price value={amount} />
      {after}
    </p>
  );
}

/**
 * The total and what VAT it holds, in the buyer's country's words (ADR 0018). Every amount is the
 * server's; the page adds nothing up.
 */
export function Totals({ quote }: { quote: QuoteBody }) {
  const { vat_display: vat } = quote;
  const abroad = quote.country !== 'NO';
  return (
    <div className="totals">
      <dl className="totals__rows">
        <div className="totals__total">
          <dt>{t('totals.total')}</dt>
          <dd>
            <Price value={quote.display_gross} />
          </dd>
        </div>
        {vat.norwegian_vat === null ? (
          <div>
            <dt>{t('totals.vat')}</dt>
            <dd>{t('no_norwegian_vat')}</dd>
          </div>
        ) : (
          <div>
            <dt>{t('totals.vat_included')}</dt>
            <dd>
              <Price value={vat.norwegian_vat} />
            </dd>
          </div>
        )}
        {abroad ? (
          <div>
            <dt>{t('totals.charged')}</dt>
            <dd>
              <Price value={quote.gross} />
            </dd>
          </div>
        ) : null}
      </dl>
      {vat.due_on_delivery === 'import_vat_estimate' && vat.display_import_vat !== null ? (
        <Estimate country={t(PLACES[quote.country].name)} amount={vat.display_import_vat} />
      ) : null}
      {vat.due_on_delivery === 'import_vat_estimate' && vat.display_import_vat === null ? (
        <p className="totals__note">{t('totals.import_vat_unknown')}</p>
      ) : null}
      {vat.due_on_delivery === 'vat_excise_and_fees' ? (
        <p className="totals__note">{t('vat_excise_and_fees')}</p>
      ) : null}
      {abroad ? <p className="totals__note">{t('totals.approx')}</p> : null}
    </div>
  );
}
