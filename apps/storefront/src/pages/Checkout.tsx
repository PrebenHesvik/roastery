import { useQueryClient } from '@tanstack/react-query';
import { useState, type SyntheticEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { placeOrder, type Placed } from '../api/actions';
import { quoteKey, useProducts, useQuote, type QuoteBody } from '../api/queries';
import { Icon } from '../components/Icon';
import { Price } from '../components/Price';
import { EmptyState, ErrorState, Loading } from '../components/States';
import { Totals } from '../components/Totals';
import { t, type Key } from '../i18n/t';
import { COUNTRIES, useCart, type CartItem } from '../lib/cart';
import { PLACES } from '../lib/catalogue';

type FieldName = 'name' | 'email' | 'street' | 'postal_code' | 'city';
type Contact = Record<FieldName, string>;

const FIELDS: readonly {
  name: FieldName;
  label: Key;
  type: string;
  auto: string;
  hint?: Key;
}[] = [
  { name: 'name', label: 'checkout.field.name', type: 'text', auto: 'name' },
  {
    name: 'email',
    label: 'checkout.field.email',
    type: 'email',
    auto: 'email',
    hint: 'checkout.hint.email',
  },
  { name: 'street', label: 'checkout.field.street', type: 'text', auto: 'street-address' },
  { name: 'postal_code', label: 'checkout.field.postal_code', type: 'text', auto: 'postal-code' },
  { name: 'city', label: 'checkout.field.city', type: 'text', auto: 'address-level2' },
];

const EMPTY: Contact = { name: '', email: '', street: '', postal_code: '', city: '' };

function problemsIn(contact: Contact): Partial<Record<FieldName, Key>> {
  const found: Partial<Record<FieldName, Key>> = {};
  for (const field of FIELDS) {
    if (contact[field.name].trim() === '') found[field.name] = 'checkout.error.required';
  }
  if (found.email === undefined && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact.email.trim())) {
    found.email = 'checkout.error.email';
  }
  return found;
}

type Refusal = Exclude<Placed, { kind: 'placed' }>;

function RefusalNotice({
  refusal,
  names,
  onAccept,
  busy,
}: {
  refusal: Refusal;
  names: (id: string) => string;
  onAccept: () => void;
  busy: boolean;
}) {
  if (refusal.kind === 'price_changed') {
    return (
      <div className="notice notice--danger" role="alert">
        <p>
          <strong>{t('checkout.changed.title')}</strong>
        </p>
        <p>
          {t('checkout.changed.body')} <Price value={refusal.quote.display_gross} />.
        </p>
        <button
          type="button"
          className="btn btn--primary notice__action"
          onClick={onAccept}
          disabled={busy}
        >
          {t('checkout.changed.accept')}
        </button>
      </div>
    );
  }
  if (refusal.kind === 'out_of_stock') {
    return (
      <div className="notice notice--danger" role="alert">
        <p>
          <strong>{t('checkout.stock.title')}</strong>
        </p>
        <p>
          {refusal.onHand === 0
            ? t('cart.sold_out', { name: names(refusal.productId) })
            : t('cart.only_left', { count: refusal.onHand, name: names(refusal.productId) })}{' '}
          <Link to="/cart">{t('checkout.stock.action')}</Link>
        </p>
      </div>
    );
  }
  return <ErrorState error={refusal.problem} />;
}

function Summary({ quote, items }: { quote: QuoteBody; items: readonly CartItem[] }) {
  return (
    <div className="summary">
      <h2 className="summary__title">{t('checkout.summary')}</h2>
      <ul className="summary__lines">
        {quote.lines.map((line) => (
          <li key={line.product.product_id}>
            <span>
              {line.product.name} <span className="summary__qty num">× {line.qty}</span>
            </span>
            <Price value={line.display_gross} />
          </li>
        ))}
      </ul>
      <Totals quote={quote} />
      <p className="summary__edit">
        <Link to="/cart">{t(items.length === 1 ? 'checkout.edit_one' : 'checkout.edit_many')}</Link>
      </p>
    </div>
  );
}

export default function Checkout() {
  const { cart, setCountry, clear } = useCart();
  const products = useProducts(cart.country);
  const listed = products.data?.products ?? [];
  const items = products.isSuccess
    ? cart.items.filter((item) =>
        listed.some((each) => each.product.product_id === item.productId && each.display_price),
      )
    : [];
  const quote = useQuote(cart.country, items);
  const client = useQueryClient();
  const navigate = useNavigate();
  const [contact, setContact] = useState<Contact>(EMPTY);
  const [shown, setShown] = useState<Partial<Record<FieldName, Key>>>({});
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [busy, setBusy] = useState(false);

  const names = (id: string) =>
    listed.find((each) => each.product.product_id === id)?.product.name ?? id;

  const submit = async (confirmed: QuoteBody) => {
    const found = problemsIn(contact);
    setShown(found);
    const first = FIELDS.find((field) => found[field.name] !== undefined);
    if (first !== undefined) {
      document.getElementById(`field-${first.name}`)?.focus();
      return;
    }
    setBusy(true);
    setRefusal(null);
    const result = await placeOrder({
      country: cart.country,
      items: items.map((item) => ({ product_id: item.productId, qty: item.qty })),
      total: confirmed.gross,
      name: contact.name.trim(),
      email: contact.email.trim(),
      street: contact.street.trim(),
      postal_code: contact.postal_code.trim(),
      city: contact.city.trim(),
    });
    setBusy(false);
    if (result.kind === 'placed') {
      clear();
      void navigate(`/pay/${result.order.token}`);
      return;
    }
    if (result.kind === 'price_changed') {
      client.setQueryData(quoteKey(cart.country, items), result.quote);
    } else if (result.kind === 'out_of_stock') {
      void client.invalidateQueries({ queryKey: ['quote'] });
      void client.invalidateQueries({ queryKey: ['products'] });
    }
    setRefusal(result);
  };

  if (cart.items.length === 0) {
    return (
      <div className="page wrap">
        <h1 className="page-title">{t('page.checkout')}</h1>
        <EmptyState
          title={t('cart.empty.title')}
          action={{ to: '/shop?shelf=beans', label: t('cart.empty.action') }}
        >
          {t('checkout.empty')}
        </EmptyState>
      </div>
    );
  }

  const onSubmit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (quote.data !== undefined && !busy) void submit(quote.data);
  };

  const short = quote.data?.lines.some((line) => line.qty > line.on_hand) ?? false;

  return (
    <div className="page wrap checkout">
      <h1 className="page-title">{t('page.checkout')}</h1>
      <p className="page-lede">{t('checkout.lede')}</p>
      <form className="checkout__grid" onSubmit={onSubmit} noValidate>
        <div className="checkout__form">
          <fieldset className="choice">
            <legend className="choice__legend">{t('checkout.country')}</legend>
            <p className="field__hint">{t('checkout.country_hint')}</p>
            <div className="choice__options">
              {COUNTRIES.map((country) => (
                <label key={country} className="choice__option">
                  <input
                    type="radio"
                    name="country"
                    value={country}
                    checked={cart.country === country}
                    onChange={() => {
                      setCountry(country);
                      setRefusal(null);
                    }}
                  />
                  <span className="choice__name">{t(PLACES[country].name)}</span>
                  <span className="choice__currency">{PLACES[country].currency}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="contact">
            <legend className="choice__legend">{t('checkout.contact')}</legend>
            <p className="field__hint">{t('checkout.contact_hint')}</p>
            <div className="contact__fields">
              {FIELDS.map((field) => {
                const error = shown[field.name];
                const described = [
                  field.hint === undefined ? null : `hint-${field.name}`,
                  error === undefined ? null : `error-${field.name}`,
                ]
                  .filter((each) => each !== null)
                  .join(' ');
                return (
                  <div key={field.name} className={`field field--${field.name}`}>
                    <label htmlFor={`field-${field.name}`}>{t(field.label)}</label>
                    <input
                      id={`field-${field.name}`}
                      name={field.name}
                      type={field.type}
                      autoComplete={field.auto}
                      required
                      aria-invalid={error === undefined ? undefined : true}
                      aria-describedby={described === '' ? undefined : described}
                      value={contact[field.name]}
                      onChange={(event) => {
                        const value = event.target.value;
                        setContact((current) => ({ ...current, [field.name]: value }));
                        if (error !== undefined) {
                          setShown((current) => ({ ...current, [field.name]: undefined }));
                        }
                      }}
                    />
                    {field.hint === undefined ? null : (
                      <span id={`hint-${field.name}`} className="field__hint">
                        {t(field.hint)}
                      </span>
                    )}
                    {error === undefined ? null : (
                      <span id={`error-${field.name}`} className="field__error">
                        {t(error)}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </fieldset>
        </div>

        <aside className="checkout__side" aria-label={t('checkout.summary')}>
          {products.isError || quote.isError ? (
            <ErrorState
              error={products.isError ? products.error : quote.error}
              onRetry={() => {
                void products.refetch();
                void quote.refetch();
              }}
            />
          ) : null}
          {quote.data === undefined ? (
            products.isError || quote.isError ? null : (
              <Loading lines={4} />
            )
          ) : (
            <>
              <Summary quote={quote.data} items={items} />
              {refusal === null ? null : (
                <RefusalNotice
                  refusal={refusal}
                  names={names}
                  busy={busy}
                  onAccept={() => {
                    if (refusal.kind === 'price_changed') void submit(refusal.quote);
                  }}
                />
              )}
              {short ? <p className="cart__blocked">{t('cart.blocked')}</p> : null}
              {refusal?.kind === 'price_changed' ? null : (
                <button
                  type="submit"
                  className="btn btn--primary btn--wide"
                  disabled={busy || short || quote.isFetching}
                  data-busy={busy}
                >
                  {busy ? t('checkout.placing') : t('checkout.place')}
                  {busy ? null : <Price value={quote.data.display_gross} />}
                  {busy ? null : <Icon name="arrow" />}
                </button>
              )}
              <p className="checkout__then">{t('checkout.then')}</p>
            </>
          )}
        </aside>
      </form>
    </div>
  );
}
