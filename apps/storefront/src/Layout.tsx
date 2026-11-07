import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { Icon } from './components/Icon';
import { t } from './i18n/t';
import { COUNTRIES, useCart, type Country } from './lib/cart';
import { PLACES } from './lib/catalogue';
import { useTheme } from './lib/theme';

function CountryPicker() {
  const { cart, setCountry } = useCart();
  const place = PLACES[cart.country];
  return (
    <div className="country">
      <span aria-hidden="true">
        {cart.country} · {place.currency}
      </span>
      <Icon name="down" />
      <select
        aria-label={t('country.label')}
        value={cart.country}
        onChange={(event) => {
          setCountry(event.target.value as Country);
        }}
      >
        {COUNTRIES.map((country) => (
          <option key={country} value={country}>
            {t('country.option', {
              name: t(PLACES[country].name),
              currency: PLACES[country].currency,
            })}
          </option>
        ))}
      </select>
    </div>
  );
}

function BagChip() {
  const { count } = useCart();
  const previous = useRef(count);
  const [bump, setBump] = useState(false);

  useEffect(() => {
    if (count > previous.current) setBump(true);
    previous.current = count;
    const timer = window.setTimeout(() => {
      setBump(false);
    }, 450);
    return () => {
      window.clearTimeout(timer);
    };
  }, [count]);

  return (
    <Link
      to="/cart"
      className="bag-chip"
      data-bump={bump}
      aria-label={t(count === 1 ? 'nav.bag_one' : 'nav.bag_many', { count })}
    >
      <Icon name="bag" />
      <span>{t('nav.cart')}</span>
      <span className="bag-chip__count num">{count}</span>
    </Link>
  );
}

function ShelfLink({ shelf, children }: { shelf: string; children: string }) {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const current = pathname === '/shop' && params.get('shelf') === shelf;
  return (
    <Link to={`/shop?shelf=${shelf}`} aria-current={current ? 'page' : undefined}>
      {children}
    </Link>
  );
}

export default function Layout() {
  const { theme, toggle } = useTheme();
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t('nav.skip')}
      </a>
      <header className="site-header">
        <Link to="/" className="wordmark">
          {t('brand.name')}
        </Link>
        <div className="site-header__right">
          <nav className="site-nav" aria-label={t('nav.main')}>
            <ShelfLink shelf="beans">{t('nav.beans')}</ShelfLink>
            <ShelfLink shelf="equipment">{t('nav.gear')}</ShelfLink>
            <NavLink to="/visit">{t('nav.visit')}</NavLink>
          </nav>
          <div className="site-tools">
            <CountryPicker />
            <button
              type="button"
              className="icon-button"
              onClick={toggle}
              aria-label={t(theme === 'dark' ? 'theme.to_light' : 'theme.to_dark')}
              title={t(theme === 'dark' ? 'theme.to_light' : 'theme.to_dark')}
            >
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
            <BagChip />
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="site-footer">
        <div className="wrap site-footer__inner">
          <p>
            <b>{t('brand.full')}</b> · {t('footer.where')}
          </p>
          <p>
            <Link to="/visit">{t('footer.counter')}</Link>
          </p>
          <p>{t('footer.sandbox')}</p>
        </div>
      </footer>
    </div>
  );
}
