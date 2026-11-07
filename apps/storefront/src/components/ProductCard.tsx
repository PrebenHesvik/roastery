import { Link } from 'react-router-dom';
import { isBeans, type Listed } from '../api/queries';
import { copyFor } from '../content/products';
import { t } from '../i18n/t';
import { AddButton } from './AddButton';
import { Price } from './Price';
import { RoastScale } from './RoastScale';

/** A product's facts in a line: origin, process, weight; or material and warranty. */
export function factsLine(listed: Pick<Listed, 'details'>): string {
  const { details } = listed;
  if (isBeans(details)) {
    return t('facts.beans', {
      origin: details.origin,
      process: details.process,
      weight: String(details.weight_g),
    });
  }
  return t('facts.equipment', {
    material: details.material,
    months: String(details.warranty_months),
  });
}

/** Coming soon (no price), out of stock, or addable, with its price. */
export function Buy({ listed, compact = false }: { listed: Listed; compact?: boolean }) {
  const { product } = listed;
  if (listed.display_price === null) {
    return (
      <div className="buy-row">
        <span className="buy-row__note">{t('product.soon')}</span>
        <button type="button" className="btn btn--soon btn--small" disabled>
          {t('product.soon_short')}
        </button>
      </div>
    );
  }
  return (
    <div className="buy-row">
      <Price value={listed.display_price} className="buy-row__price" />
      {listed.in_stock ? (
        <AddButton
          productId={product.product_id}
          name={product.name}
          size={compact ? 'small' : 'normal'}
        />
      ) : (
        <span className="buy-row__note">{t('product.out')}</span>
      )}
    </div>
  );
}

export function ProductCard({
  listed,
  headingLevel = 3,
}: {
  listed: Listed;
  headingLevel?: 2 | 3;
}) {
  const { product, details } = listed;
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <article className="card" data-kind={product.kind}>
      <Heading className="card__name">
        <Link to={`/shop/${product.product_id}`}>{product.name}</Link>
      </Heading>
      <p className="card__facts">{factsLine(listed)}</p>
      {isBeans(details) ? (
        <RoastScale roast={details.roast} />
      ) : (
        <p className="card__line">{copyFor(product.product_id).line}</p>
      )}
      <Buy listed={listed} compact />
    </article>
  );
}
