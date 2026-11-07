import { Link } from 'react-router-dom';
import { useProducts, type Listed } from '../api/queries';
import { AddButton } from '../components/AddButton';
import { Price } from '../components/Price';
import { ProductCard } from '../components/ProductCard';
import { RainCanvas } from '../components/RainCanvas';
import { ErrorState } from '../components/States';
import { copyFor } from '../content/products';
import { t, type Key } from '../i18n/t';
import { COUNTRIES, useCart, type Country } from '../lib/cart';
import { PLACES } from '../lib/catalogue';
import { counterOpenOn } from '../lib/counter';

const HERO = 'P-10';

function HeroBuy({ hero, pending }: { hero: Listed | undefined; pending: boolean }) {
  const name = hero?.product.name ?? t('home.hero_name');
  if (hero === undefined || hero.display_price === null) {
    return (
      <div className="coat__buy">
        <button type="button" className="btn btn--ink coat__add" disabled>
          {t('home.add', { name })}
        </button>
        {pending ? <span className="skeleton coat__price-wait" aria-hidden="true" /> : null}
      </div>
    );
  }
  return (
    <div className="coat__buy">
      {hero.in_stock ? (
        <AddButton
          productId={hero.product.product_id}
          name={name}
          variant="ink"
          label={t('home.add', { name })}
        />
      ) : (
        <span className="coat__out">{t('home.hero_out', { name })}</span>
      )}
      <span className="coat__price">
        <Price value={hero.display_price} />
      </span>
    </div>
  );
}

function CounterLine() {
  const open = counterOpenOn(new Date());
  return (
    <p className="counter-line">
      <span>
        <b>{t(open ? 'counter.open_today' : 'counter.closed_today')}</b>
        <span aria-hidden="true"> · </span>
        <span className="counter-line__days">{t('counter.days')}</span>
      </span>
      <Link to="/visit">{t('counter.by_the_gram')}</Link>
    </p>
  );
}

const MONEY_ROWS: Record<Country, Key> = {
  NO: 'home.money.NO',
  SE: 'home.money.SE',
  DK: 'home.money.DK',
  FI: 'home.money.FI',
};

function MoneyWhereYouAre() {
  const { cart, setCountry } = useCart();
  return (
    <section className="money wrap" aria-labelledby="money-title">
      <div className="money__intro">
        <h2 id="money-title" className="section-title">
          {t('home.money.title')}
        </h2>
        <p>{t('home.money.lede')}</p>
      </div>
      <ul className="money__rows">
        {COUNTRIES.map((country) => {
          const place = PLACES[country];
          const here = country === cart.country;
          return (
            <li key={country} className="money__row" data-here={here}>
              <div className="money__where">
                <span className="money__country">{t(place.name)}</span>
                <span className="money__currency">{place.currency}</span>
              </div>
              <p>{t(MONEY_ROWS[country])}</p>
              {here ? (
                <span className="money__here">{t('home.money.here')}</span>
              ) : (
                <button
                  type="button"
                  className="btn btn--quiet btn--small"
                  onClick={() => {
                    setCountry(country);
                  }}
                >
                  {t('home.money.switch', { currency: place.currency })}
                  <span className="visually-hidden">
                    {' '}
                    {t('home.money.switch_for', { name: t(place.name) })}
                  </span>
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function Home() {
  const { cart } = useCart();
  const products = useProducts(cart.country);
  const listed = products.data?.products ?? [];
  const hero = listed.find((each) => each.product.product_id === HERO);
  const beans = listed.filter(
    (each) => each.product.kind === 'beans' && each.product.product_id !== HERO,
  );
  const gear = listed.filter((each) => each.product.kind === 'equipment');
  const label = products.data?.price_label;

  return (
    <div className="home">
      <section className="stage" aria-labelledby="home-title">
        <RainCanvas />
        <div className="coat">
          <div>
            <h1 id="home-title" className="coat__title">
              <span>{t('home.title_rain')}</span> <span>{t('home.title_coffee')}</span>
            </h1>
            <p className="coat__lede">
              {t('home.lede')} {copyFor(HERO).line}
            </p>
          </div>
          <div>
            <HeroBuy hero={hero} pending={products.isPending} />
            {label === undefined ? null : (
              <p className="coat__note">
                {t(label)}
                {cart.country === 'NO' ? null : ` · ${t('home.approx')}`}
              </p>
            )}
          </div>
        </div>
        <div className="street">
          <h2 className="section-label">{t('home.shelf')}</h2>
          {products.isError ? (
            <ErrorState
              error={products.error}
              onRetry={() => {
                void products.refetch();
              }}
            />
          ) : (
            <div className="street__cards" aria-busy={products.isPending}>
              {products.isPending
                ? [0, 1].map((index) => (
                    <div key={index} className="card card--wait" aria-hidden="true">
                      <span className="skeleton" />
                      <span className="skeleton" />
                      <span className="skeleton" />
                    </div>
                  ))
                : beans.map((each) => <ProductCard key={each.product.product_id} listed={each} />)}
            </div>
          )}
          <CounterLine />
        </div>
      </section>

      <section className="gear wrap" aria-labelledby="gear-title">
        <div className="gear__intro">
          <h2 id="gear-title" className="section-title">
            {t('home.gear.title')}
          </h2>
          <p>{t('home.gear.lede')}</p>
          <Link className="text-link" to="/shop?shelf=equipment">
            {t('home.gear.all')}
          </Link>
        </div>
        <div className="gear__cards">
          {gear.map((each) => (
            <ProductCard key={each.product.product_id} listed={each} />
          ))}
        </div>
      </section>

      <section className="window wrap" aria-labelledby="window-title">
        <div className="window__pane">
          <h2 id="window-title" className="window__title">
            {t('home.window.title')}
          </h2>
          <p className="window__lede">{t('home.window.lede')}</p>
          <dl className="window__facts">
            <div>
              <dt>{t('home.window.hours_label')}</dt>
              <dd>{t('home.window.hours')}</dd>
            </div>
            <div>
              <dt>{t('home.window.loose_label')}</dt>
              <dd>{t('home.window.loose')}</dd>
            </div>
            <div>
              <dt>{t('home.window.club_label')}</dt>
              <dd>{t('home.window.club')}</dd>
            </div>
          </dl>
          <Link className="btn btn--line" to="/visit">
            {t('home.window.more')}
          </Link>
        </div>
      </section>

      <MoneyWhereYouAre />

      <section className="close wrap" aria-labelledby="close-title">
        <h2 id="close-title" className="close__title">
          <span>{t('home.close.rain')}</span> <span>{t('home.close.coffee')}</span>
        </h2>
        <div className="close__actions">
          <Link className="btn btn--primary" to="/shop">
            {t('home.close.shop')}
          </Link>
          <Link className="btn btn--quiet" to="/cart">
            {t('home.close.bag')}
          </Link>
        </div>
      </section>
    </div>
  );
}
