import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { pay, type Outcome, type Paid } from '../api/actions';
import { orderKey, useOrder, type OrderBody } from '../api/queries';
import { Price } from '../components/Price';
import { codeOf, EmptyState, ErrorState, Loading } from '../components/States';
import { t, type Key } from '../i18n/t';

const OUTCOMES: readonly { outcome: Outcome; label: Key; variant: string }[] = [
  { outcome: 'approve', label: 'pay.approve', variant: 'btn--primary' },
  { outcome: 'decline', label: 'pay.decline', variant: 'btn--quiet' },
  { outcome: 'outage', label: 'pay.outage', variant: 'btn--quiet' },
];

type Shown = Exclude<Paid, { kind: 'paid' }>;

function Result({ result, onRetry, busy }: { result: Shown; onRetry: () => void; busy: boolean }) {
  switch (result.kind) {
    case 'declined':
      return (
        <div className="notice notice--danger" role="alert">
          <p>
            <strong>{t('pay.declined.title')}</strong>
          </p>
          <p>{t('pay.declined.body')}</p>
        </div>
      );
    case 'outage':
      return (
        <div className="notice notice--danger" role="alert">
          <p>
            <strong>{t('pay.down.title')}</strong>
          </p>
          <p>{t('pay.down.body')}</p>
          <button
            type="button"
            className="btn btn--quiet btn--small notice__action"
            onClick={onRetry}
            disabled={busy}
          >
            {t('pay.down.retry')}
          </button>
        </div>
      );
    case 'already_paid':
      return (
        <div className="notice" role="status">
          <p>{t('pay.settled')}</p>
        </div>
      );
    case 'problem':
      return <ErrorState error={result.problem} />;
  }
}

function Sandbox({ order, token }: { order: OrderBody; token: string }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<Outcome | null>(null);
  const [result, setResult] = useState<Shown | null>(null);
  const [last, setLast] = useState<Outcome>('approve');

  const attempt = async (outcome: Outcome) => {
    setBusy(outcome);
    setLast(outcome);
    setResult(null);
    const paid = await pay(token, outcome);
    setBusy(null);
    if (paid.kind === 'paid') {
      client.setQueryData<OrderBody>(orderKey(token), { ...order, status: paid.payment.status });
      void navigate(`/orders/${token}`);
      return;
    }
    if (paid.kind === 'already_paid') void client.invalidateQueries({ queryKey: orderKey(token) });
    setResult(paid);
  };

  return (
    <div className="sandbox">
      <div className="sandbox__amount">
        <p className="sandbox__label">{t('pay.amount')}</p>
        <p className="sandbox__total">
          <Price value={order.display_total} />
        </p>
        {order.country === 'NO' ? null : (
          <p className="sandbox__nok">
            {t('pay.charged')} <Price value={order.total} />
          </p>
        )}
        <p className="sandbox__order">{t('pay.order', { id: order.order_id })}</p>
      </div>
      <section className="sandbox__panel" aria-labelledby="sandbox-title">
        <h2 id="sandbox-title" className="sandbox__badge">
          {t('pay.badge')}
        </h2>
        <p className="sandbox__explain">{t('pay.explain')}</p>
        <div className="sandbox__actions">
          {OUTCOMES.map(({ outcome, label, variant }) => (
            <button
              key={outcome}
              type="button"
              className={`btn ${variant}`}
              disabled={busy !== null}
              data-busy={busy === outcome}
              onClick={() => {
                void attempt(outcome);
              }}
            >
              {busy === outcome ? t('pay.waiting') : t(label)}
            </button>
          ))}
        </div>
        <div aria-live="polite">
          {result === null ? null : (
            <Result
              result={result}
              busy={busy !== null}
              onRetry={() => {
                void attempt(last);
              }}
            />
          )}
        </div>
      </section>
    </div>
  );
}

export default function Pay() {
  const { token = '' } = useParams();
  const order = useOrder(token);

  return (
    <div className="page wrap pay">
      <h1 className="page-title">{t('pay.title')}</h1>
      <p className="page-lede">{t('pay.lede')}</p>
      {order.isPending ? <Loading lines={3} /> : null}
      {order.isError ? (
        codeOf(order.error) === 'UnknownToken' ? (
          <EmptyState
            title={t('order.unknown.title')}
            action={{ to: '/', label: t('order.unknown.action') }}
          >
            {t('order.unknown.body')}
          </EmptyState>
        ) : (
          <ErrorState
            error={order.error}
            onRetry={() => {
              void order.refetch();
            }}
          />
        )
      ) : null}
      {order.data === undefined ? null : order.data.status === 'placed' ? (
        <Sandbox order={order.data} token={token} />
      ) : (
        <div className="state">
          <h2>{t('pay.done.title')}</h2>
          <p>{t('pay.done.body')}</p>
          <Link className="btn btn--primary" to={`/orders/${token}`}>
            {t('pay.done.action')}
          </Link>
        </div>
      )}
    </div>
  );
}
