import { Link, useSearchParams } from 'react-router-dom';
import { useProducts } from '../api/queries';
import { ProductCard } from '../components/ProductCard';
import { ErrorState, Loading } from '../components/States';
import { t } from '../i18n/t';
import { useCart } from '../lib/cart';
import { PLACES, SHELVES, shelfNamed } from '../lib/catalogue';

function ShelfFilter({ current }: { current: string | null }) {
  const parents = SHELVES.filter((shelf) => shelf.parent === null);
  const link = (slug: string | null, label: string, child = false) => (
    <Link
      key={slug ?? 'all'}
      to={slug === null ? '/shop' : `/shop?shelf=${slug}`}
      className={child ? 'shelves__link shelves__link--child' : 'shelves__link'}
      aria-current={current === slug ? 'page' : undefined}
    >
      {label}
    </Link>
  );
  return (
    <nav className="shelves" aria-label={t('shop.filter')}>
      <div className="shelves__group">{link(null, t('shelf.all'))}</div>
      {parents.map((parent) => (
        <div key={parent.slug} className="shelves__group">
          {link(parent.slug, t(parent.label))}
          {SHELVES.filter((shelf) => shelf.parent === parent.slug).map((shelf) =>
            link(shelf.slug, t(shelf.label), true),
          )}
        </div>
      ))}
    </nav>
  );
}

export default function Shop() {
  const { cart } = useCart();
  const products = useProducts(cart.country);
  const [params] = useSearchParams();
  const shelf = shelfNamed(params.get('shelf'));
  const shown = (products.data?.products ?? []).filter(
    (each) => shelf === null || shelf.categories.includes(each.product.category_id),
  );
  const label = products.data?.price_label;

  return (
    <div className="page wrap shop">
      <div className="shop__head">
        <h1 className="page-title">{shelf === null ? t('page.shop') : t(shelf.label)}</h1>
        <p className="page-lede">
          {t('shop.lede', { currency: PLACES[cart.country].currency })}
          {label === undefined ? null : ` · ${t(label)}`}
          {label === undefined || cart.country === 'NO' ? null : ` · ${t('shop.approx')}`}
        </p>
      </div>
      <div className="shop__body">
        <ShelfFilter current={shelf?.slug ?? null} />
        <div className="shop__list">
          {products.isPending ? <Loading lines={4} /> : null}
          {products.isError ? (
            <ErrorState
              error={products.error}
              onRetry={() => {
                void products.refetch();
              }}
            />
          ) : null}
          {products.isSuccess && shown.length === 0 ? (
            <p className="shop__empty">{t('shop.empty')}</p>
          ) : null}
          {shown.length > 0 ? (
            <ul className="shop__grid">
              {shown.map((each) => (
                <li key={each.product.product_id}>
                  <ProductCard listed={each} headingLevel={2} />
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  );
}
