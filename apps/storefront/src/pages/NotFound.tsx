import { Link } from 'react-router-dom';
import { t } from '../i18n/t';

export default function NotFound() {
  return (
    <div className="page wrap lost">
      <h1 className="page-title">{t('page.not_found')}</h1>
      <p className="page-lede">{t('lost.body')}</p>
      <div className="lost__actions">
        <Link className="btn btn--primary" to="/shop">
          {t('lost.shop')}
        </Link>
        <Link className="btn btn--quiet" to="/">
          {t('lost.home')}
        </Link>
      </div>
    </div>
  );
}
