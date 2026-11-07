import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Problem } from '../api/queries';
import { t } from '../i18n/t';

export function Loading({ lines = 3 }: { lines?: number }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="visually-hidden">{t('state.loading')}</span>
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} className="skeleton loading__bar" aria-hidden="true" />
      ))}
    </div>
  );
}

export function codeOf(error: unknown): string {
  return error instanceof Problem ? error.code : 'NetworkError';
}

/** Something went wrong that no page has a story for: say so plainly, with the code. */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const code = codeOf(error);
  return (
    <div className="state state--error" role="alert">
      <h2>{t(code === 'NetworkError' ? 'state.offline.title' : 'state.error.title')}</h2>
      <p>
        {t(code === 'NetworkError' ? 'state.offline.body' : 'state.error.body')} <code>{code}</code>
      </p>
      {onRetry === undefined ? null : (
        <button type="button" className="btn btn--quiet" onClick={onRetry}>
          {t('state.retry')}
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: { to: string; label: string };
}) {
  return (
    <div className="state">
      <h2>{title}</h2>
      <p>{children}</p>
      {action === undefined ? null : (
        <Link className="btn btn--primary" to={action.to}>
          {action.label}
        </Link>
      )}
    </div>
  );
}
