import { Link } from 'react-router-dom';
import { t } from '../i18n/t';
import { counterOpenOn } from '../lib/counter';

const WEEK = [
  'visit.day.mon',
  'visit.day.tue',
  'visit.day.wed',
  'visit.day.thu',
  'visit.day.fri',
  'visit.day.sat',
  'visit.day.sun',
] as const;

export default function Visit() {
  const open = counterOpenOn(new Date());
  return (
    <div className="page wrap visit">
      <div className="visit__grid">
        <div className="visit__main">
          <h1 className="page-title">{t('page.visit')}</h1>
          <p className="page-lede">{t('visit.lede')}</p>
          <p className="visit__today" data-open={open}>
            {t(open ? 'counter.open_today' : 'counter.closed_today')}
          </p>
          <section className="visit__part" aria-labelledby="visit-loose">
            <h2 id="visit-loose">{t('visit.loose.title')}</h2>
            <p>{t('visit.loose.body')}</p>
            <Link className="text-link" to="/shop/P-11">
              {t('visit.loose.link')}
            </Link>
          </section>
          <section className="visit__part" aria-labelledby="visit-club">
            <h2 id="visit-club">{t('visit.club.title')}</h2>
            <p>{t('visit.club.body')}</p>
          </section>
          <section className="visit__part" aria-labelledby="visit-till">
            <h2 id="visit-till">{t('visit.till.title')}</h2>
            <p>{t('visit.till.body')}</p>
          </section>
        </div>
        <aside className="hours" aria-labelledby="hours-title">
          <h2 id="hours-title" className="hours__title">
            {t('visit.hours')}
          </h2>
          <ul className="hours__days">
            {WEEK.map((day, index) => (
              <li key={day} data-closed={index === 6}>
                <span>{t(day)}</span>
                <span>{t(index === 6 ? 'visit.closed' : 'visit.open')}</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
