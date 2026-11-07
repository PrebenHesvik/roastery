import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { isBeans, useProduct } from '../api/queries';
import { AddButton } from '../components/AddButton';
import { Icon } from '../components/Icon';
import { Price } from '../components/Price';
import { RoastScale } from '../components/RoastScale';
import { codeOf, EmptyState, ErrorState, Loading } from '../components/States';
import { copyFor } from '../content/products';
import { t } from '../i18n/t';
import { useCart } from '../lib/cart';
import { shelfOf } from '../lib/catalogue';

export default function Product() {
  const { id = '' } = useParams();
  const { cart } = useCart();
  const query = useProduct(id, cart.country);
  const [qty, setQty] = useState(1);

  if (query.isPending) {
    return (
      <div className="page wrap">
        <Loading lines={5} />
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="page wrap">
        {codeOf(query.error) === 'UnknownId' ? (
          <EmptyState
            title={t('product.unknown.title')}
            action={{ to: '/shop', label: t('product.unknown.action') }}
          >
            {t('product.unknown.body')}
          </EmptyState>
        ) : (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        )}
      </div>
    );
  }

  const page = query.data;
  const { product, details } = page;
  const copy = copyFor(product.product_id);
  const shelf = shelfOf(product.category_id);
  const priced = page.display_price;

  return (
    <div className="page wrap product">
      <nav className="crumbs" aria-label={t('product.crumbs')}>
        <Link to="/shop">{t('page.shop')}</Link>
        {shelf === null ? null : (
          <>
            <span aria-hidden="true">/</span>
            <Link to={`/shop?shelf=${shelf.slug}`}>{t(shelf.label)}</Link>
          </>
        )}
      </nav>
      <div className="product__grid">
        <div className="product__main">
          <h1 className="page-title">{product.name}</h1>
          <p className="product__use">{copy.use}</p>
          <div className="product__copy">
            {copy.body.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
        </div>
        <aside className="product__side" aria-label={t('product.buy')}>
          {isBeans(details) ? (
            <div className="product__scale">
              <RoastScale roast={details.roast} size="large" />
            </div>
          ) : null}
          <dl className="facts">
            {isBeans(details) ? (
              <>
                <div>
                  <dt>{t('facts.origin')}</dt>
                  <dd>{details.origin}</dd>
                </div>
                <div>
                  <dt>{t('facts.process')}</dt>
                  <dd>{details.process}</dd>
                </div>
                <div>
                  <dt>{t('facts.roast')}</dt>
                  <dd>{details.roast}</dd>
                </div>
                <div>
                  <dt>{t('facts.weight')}</dt>
                  <dd className="num">{t('facts.grams', { weight: details.weight_g })}</dd>
                </div>
              </>
            ) : (
              <>
                <div>
                  <dt>{t('facts.material')}</dt>
                  <dd>{details.material}</dd>
                </div>
                <div>
                  <dt>{t('facts.warranty')}</dt>
                  <dd className="num">{t('facts.months', { months: details.warranty_months })}</dd>
                </div>
              </>
            )}
          </dl>
          {priced === null ? (
            <div className="product__buy">
              <p className="product__soon">{t('product.soon')}</p>
              <p className="product__note">{t('product.soon_body')}</p>
            </div>
          ) : (
            <div className="product__buy">
              <p className="product__price">
                <Price value={priced} />
              </p>
              <p className="product__note">
                {page.price_label === 'incl_vat' && page.percent !== null
                  ? t('product.incl_vat_percent', { percent: page.percent })
                  : t(page.price_label)}
                {page.unit_price === null || page.country === 'NO' ? null : (
                  <>
                    {' · '}
                    {t('product.charged')} <Price value={page.unit_price} />
                  </>
                )}
              </p>
              {page.in_stock ? (
                <div className="product__add">
                  <div className="qty" role="group" aria-label={t('qty.label')}>
                    <button
                      type="button"
                      aria-label={t('qty.less')}
                      disabled={qty <= 1}
                      onClick={() => {
                        setQty((value) => Math.max(1, value - 1));
                      }}
                    >
                      <Icon name="minus" />
                    </button>
                    <output aria-live="polite" className="num">
                      {qty}
                    </output>
                    <button
                      type="button"
                      aria-label={t('qty.more')}
                      onClick={() => {
                        setQty((value) => value + 1);
                      }}
                    >
                      <Icon name="plus" />
                    </button>
                  </div>
                  <AddButton
                    productId={product.product_id}
                    name={product.name}
                    qty={qty}
                    variant="primary"
                    label={t('product.add')}
                  />
                </div>
              ) : (
                <p className="product__out">{t('product.out_long')}</p>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
