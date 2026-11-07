import { useEffect, useState } from 'react';
import { t } from '../i18n/t';
import { useCart } from '../lib/cart';
import { Icon } from './Icon';

interface Props {
  productId: string;
  name: string;
  qty?: number;
  variant?: 'primary' | 'line' | 'ink';
  size?: 'small' | 'normal';
  label?: string;
  wide?: boolean;
}

/** Add to the bag, with a short "added" acknowledgement that a screen reader hears too. */
export function AddButton({
  productId,
  name,
  qty = 1,
  variant = 'line',
  size = 'normal',
  label,
  wide = false,
}: Props) {
  const { add } = useCart();
  const [added, setAdded] = useState(0);

  useEffect(() => {
    if (added === 0) return;
    const timer = window.setTimeout(() => {
      setAdded(0);
    }, 1800);
    return () => {
      window.clearTimeout(timer);
    };
  }, [added]);

  const classes = ['btn', `btn--${variant}`];
  if (size === 'small') classes.push('btn--small');
  if (wide) classes.push('btn--wide');

  return (
    <>
      <button
        type="button"
        className={classes.join(' ')}
        aria-label={label === undefined ? t('add.named', { name }) : undefined}
        onClick={() => {
          add(productId, qty);
          setAdded((count) => count + 1);
        }}
      >
        {added > 0 ? <Icon name="check" /> : null}
        {added > 0 ? t('add.added') : (label ?? t('add.short'))}
      </button>
      <span className="visually-hidden" role="status">
        {added > 0 ? t('add.announce', { name }) : ''}
      </span>
    </>
  );
}
