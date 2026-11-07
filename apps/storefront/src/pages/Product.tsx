import { useParams } from 'react-router-dom';
import { t } from '../i18n/t';

export default function Product() {
  const { id } = useParams();
  return (
    <section>
      <h1>{t('page.product')}</h1>
      <p>{id}</p>
    </section>
  );
}
