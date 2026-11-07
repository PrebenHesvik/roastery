import { Link } from 'react-router-dom';
import { useProducts } from '../api/queries';
import { t } from '../i18n/t';
import { useCart } from '../lib/cart';

export default function Shop() {
  const { cart } = useCart();
  const products = useProducts(cart.country);
  return (
    <section>
      <h1>{t('page.shop')}</h1>
      {products.isPending && <p>{t('state.loading')}</p>}
      {products.isError && <p>{t('state.error', { code: products.error.message })}</p>}
      {products.data && (
        <ul>
          {products.data.products.map(({ product }) => (
            <li key={product.product_id}>
              <Link to={`/shop/${product.product_id}`}>{product.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
