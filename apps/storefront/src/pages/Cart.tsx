import { Link } from 'react-router-dom';
import { useProducts, useQuote, type Listed, type Schemas } from '../api/queries';
import { Icon } from '../components/Icon';
import { Price } from '../components/Price';
import { factsLine } from '../components/ProductCard';
import { EmptyState, ErrorState, Loading } from '../components/States';
import { Totals } from '../components/Totals';
import { t } from '../i18n/t';
import { useCart, type CartItem } from '../lib/cart';

function Stepper({ item, name }: { item: CartItem; name: string }) {
  const { setQty } = useCart();
  return (
    <div className="qty" role="group" aria-label={t('qty.label_for', { name })}>
      <button
        type="button"
        aria-label={t('qty.less_for', { name })}
        disabled={item.qty <= 1}
        onClick={() => {
          setQty(item.productId, item.qty - 1);
        }}
      >
        <Icon name="minus" />
      </button>
      <output className="num" aria-live="polite">
        {item.qty}
      </output>
      <button
        type="button"
        aria-label={t('qty.more_for', { name })}
        onClick={() => {
          setQty(item.productId, item.qty + 1);
        }}
      >
        <Icon name="plus" />
      </button>
    </div>
  );
}

function Remove({ productId, name }: { productId: string; name: string }) {
  const { remove } = useCart();
  return (
    <button
      type="button"
      className="line__remove"
      onClick={() => {
        remove(productId);
      }}
    >
      {t('cart.remove')}
      <span className="visually-hidden"> {name}</span>
    </button>
  );
}

function Line({
  line,
  item,
  listed,
}: {
  line: Schemas['QuotedLine'];
  item: CartItem;
  listed: Listed | undefined;
}) {
  const { setQty } = useCart();
  const { product } = line;
  const short = line.qty > line.on_hand;
  return (
    <li className="line" data-short={short}>
      <div className="line__what">
        <h2 className="line__name">
          <Link to={`/shop/${product.product_id}`}>{product.name}</Link>
        </h2>
        {listed === undefined ? null : <p className="line__facts">{factsLine(listed)}</p>}
        <p className="line__each">
          <Price value={line.display_unit_price} /> {t('cart.each')}
        </p>
      </div>
      <Stepper item={item} name={product.name} />
      <p className="line__sum">
        <Price value={line.display_gross} />
      </p>
      <Remove productId={product.product_id} name={product.name} />
      {short ? (
        <div className="line__short" role="alert">
          <p>
            {line.on_hand === 0
              ? t('cart.sold_out', { name: product.name })
              : t('cart.only_left', { count: line.on_hand, name: product.name })}
          </p>
          {line.on_hand > 0 ? (
            <button
              type="button"
              className="btn btn--quiet btn--small"
              onClick={() => {
                setQty(product.product_id, line.on_hand);
              }}
            >
              {t('cart.take_left', { count: line.on_hand })}
            </button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export default function Cart() {
  const { cart } = useCart();
  const products = useProducts(cart.country);
  const listed = products.data?.products ?? [];
  const known = (id: string) => listed.find((each) => each.product.product_id === id);
  // Only what has a price can be quoted; anything else is shown apart, to be removed.
  const priced = (item: CartItem) => (known(item.productId)?.display_price ?? null) !== null;
  const priceable = products.isSuccess ? cart.items.filter(priced) : [];
  const stray = products.isSuccess ? cart.items.filter((item) => !priced(item)) : [];
  const quote = useQuote(cart.country, priceable);
  const short =
    (quote.data?.lines.some((line) => line.qty > line.on_hand) ?? false) || stray.length > 0;

  if (cart.items.length === 0) {
    return (
      <div className="page wrap">
        <h1 className="page-title">{t('page.cart')}</h1>
        <EmptyState
          title={t('cart.empty.title')}
          action={{ to: '/shop?shelf=beans', label: t('cart.empty.action') }}
        >
          {t('cart.empty.body')}
        </EmptyState>
      </div>
    );
  }

  const failed = products.isError ? products.error : quote.isError ? quote.error : null;

  return (
    <div className="page wrap cart">
      <h1 className="page-title">{t('page.cart')}</h1>
      <div className="cart__grid">
        <div className="cart__lines">
          {failed !== null ? (
            <ErrorState
              error={failed}
              onRetry={() => {
                void products.refetch();
                void quote.refetch();
              }}
            />
          ) : null}
          {failed === null && (products.isPending || (quote.isPending && priceable.length > 0)) ? (
            <Loading lines={3} />
          ) : null}
          {quote.data === undefined || priceable.length === 0 ? null : (
            <ul className="lines" aria-busy={quote.isFetching}>
              {quote.data.lines.map((line) => {
                const item = cart.items.find((each) => each.productId === line.product.product_id);
                return item === undefined ? null : (
                  <Line
                    key={line.product.product_id}
                    line={line}
                    item={item}
                    listed={known(line.product.product_id)}
                  />
                );
              })}
            </ul>
          )}
          {stray.length > 0 ? (
            <ul className="lines lines--stray">
              {stray.map((item) => {
                const name = known(item.productId)?.product.name ?? item.productId;
                return (
                  <li key={item.productId} className="line">
                    <div className="line__what">
                      <h2 className="line__name">{name}</h2>
                      <p className="line__facts">{t('cart.stray')}</p>
                    </div>
                    <Remove productId={item.productId} name={name} />
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
        <aside className="cart__side" aria-label={t('cart.summary')}>
          {quote.data === undefined || priceable.length === 0 ? null : (
            <>
              <Totals quote={quote.data} />
              {short ? <p className="cart__blocked">{t('cart.blocked')}</p> : null}
              {short ? (
                <button type="button" className="btn btn--primary btn--wide" disabled>
                  {t('cart.checkout')}
                </button>
              ) : (
                <Link className="btn btn--primary btn--wide" to="/checkout">
                  {t('cart.checkout')}
                  <Icon name="arrow" />
                </Link>
              )}
            </>
          )}
          <Link className="text-link cart__more" to="/shop">
            {t('cart.more')}
          </Link>
        </aside>
      </div>
    </div>
  );
}
