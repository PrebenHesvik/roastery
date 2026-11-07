import { Link, NavLink, Outlet } from 'react-router-dom';
import { t } from './i18n/t';
import { useCart } from './lib/cart';
import { useTheme } from './lib/theme';

export default function Layout() {
  const { count } = useCart();
  const { theme, toggle } = useTheme();
  return (
    <>
      <header>
        <Link to="/">{t('brand.name')}</Link>
        <nav aria-label={t('nav.main')}>
          <NavLink to="/shop">{t('nav.shop')}</NavLink>
          <NavLink to="/visit">{t('nav.visit')}</NavLink>
          <NavLink to="/cart">
            {t('nav.cart')} ({count})
          </NavLink>
        </nav>
        <button type="button" onClick={toggle}>
          {t(theme === 'dark' ? 'theme.to_light' : 'theme.to_dark')}
        </button>
      </header>
      <main>
        <Outlet />
      </main>
    </>
  );
}
