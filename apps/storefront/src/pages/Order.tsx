import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useOrder, useProducts, type OrderBody } from '../api/queries';
import { Icon } from '../components/Icon';
import { Price } from '../components/Price';
import { codeOf, EmptyState, ErrorState, Loading } from '../components/States';
import { t, type Key } from '../i18n/t';

const TRACK: readonly { status: OrderBody['status']; label: Key }[] = [
  { status: 'placed', label: 'order.status.placed' },
  { status: 'paid', label: 'order.status.paid' },
  { status: 'shipped', label: 'order.status.shipped' },
  { status: 'delivered', label: 'order.status.delivered' },
];

/** Where the order is on the track; invoiced counts as paid. */
function reached(status: OrderBody['status']): number {
  if (status === 'invoiced') return 1;
  return TRACK.findIndex((step) => step.status === status);
}

const SAYS: Record<OrderBody['status'], Key> = {
  placed: 'order.says.placed',
  paid: 'order.says.paid',
  invoiced: 'order.says.paid',
  shipped: 'order.says.shipped',
  delivered: 'order.says.delivered',
  cancelled: 'order.says.cancelled',
};

function KeepLink() {
  const [copied, setCopied] = useState(false);
  const href = window.location.href;
  return (
    <div className="keep">
      <label htmlFor="order-link" className="keep__label">
        {t('order.keep')}
      </label>
      <div className="keep__row">
        <input
          id="order-link"
          readOnly
          value={href}
          onFocus={(event) => {
            event.target.select();
          }}
        />
        <button
          type="button"
          className="btn btn--quiet btn--small"
          onClick={() => {
            void navigator.clipboard.writeText(href).then(() => {
              setCopied(true);
            });
          }}
        >
          {copied ? <Icon name="check" /> : null}
          {t(copied ? 'order.copied' : 'order.copy')}
        </button>
      </div>
    </div>
  );
}

function Track({ status }: { status: OrderBody['status'] }) {
  const at = reached(status);
  return (
    <ol className="track" aria-label={t('order.track')}>
      {TRACK.map((step, index) => (
        <li
          key={step.status}
          className="track__step"
          data-done={index <= at}
          aria-current={index === at ? 'step' : undefined}
        >
          <span className="track__mark" aria-hidden="true" />
          <span>{t(step.label)}</span>
        </li>
      ))}
    </ol>
  );
}

function Lines({ order }: { order: OrderBody }) {
  const products = useProducts(order.country);
  const name = (id: string) =>
    products.data?.products.find((each) => each.product.product_id === id)?.product.name ?? id;
  return (
    <table className="order-lines">
      <caption className="visually-hidden">{t('order.lines')}</caption>
      <thead>
        <tr>
          <th scope="col">{t('order.col.item')}</th>
          <th scope="col">{t('order.col.qty')}</th>
          <th scope="col">{t('order.col.each')}</th>
        </tr>
      </thead>
      <tbody>
        {order.lines.map((line) => (
          <tr key={line.line_id}>
            <th scope="row">
              <Link to={`/shop/${line.product_id}`}>{name(line.product_id)}</Link>
            </th>
            <td className="num">{line.qty}</td>
            <td>
              <Price value={line.display_unit_price} />
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" colSpan={2}>
            {t('totals.total')}
          </th>
          <td>
            <Price value={order.display_total} />
          </td>
        </tr>
        {order.country === 'NO' ? null : (
          <tr className="order-lines__nok">
            <th scope="row" colSpan={2}>
              {t('totals.charged')}
            </th>
            <td>
              <Price value={order.total} />
            </td>
          </tr>
        )}
      </tfoot>
    </table>
  );
}

export default function Order() {
  const { token = '' } = useParams();
  const order = useOrder(token);

  if (order.isPending) {
    return (
      <div className="page wrap">
        <Loading lines={4} />
      </div>
    );
  }
  if (order.isError) {
    return (
      <div className="page wrap">
        {codeOf(order.error) === 'UnknownToken' ? (
          <>
            <h1 className="page-title">{t('page.order')}</h1>
            <EmptyState
              title={t('order.unknown.title')}
              action={{ to: '/', label: t('order.unknown.action') }}
            >
              {t('order.unknown.body')}
            </EmptyState>
          </>
        ) : (
          <ErrorState
            error={order.error}
            onRetry={() => {
              void order.refetch();
            }}
          />
        )}
      </div>
    );
  }

  const data = order.data;
  return (
    <div className="page wrap order">
      <h1 className="page-title">
        <span className="visually-hidden">{t('order.status_label')}</span>{' '}
        {t(`order.status.${data.status}` as Key)}
      </h1>
      <p className="page-lede">{t(SAYS[data.status])}</p>
      <p className="order__id">{t('order.id', { id: data.order_id, day: data.day })}</p>
      {data.status === 'cancelled' ? null : <Track status={data.status} />}
      {data.status === 'placed' ? (
        <Link className="btn btn--primary order__pay" to={`/pay/${token}`}>
          {t('order.pay')}
          <Icon name="arrow" />
        </Link>
      ) : null}
      <div className="order__grid">
        <Lines order={data} />
        <KeepLink />
      </div>
    </div>
  );
}
