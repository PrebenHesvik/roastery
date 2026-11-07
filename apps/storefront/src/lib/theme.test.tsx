import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import html from '../../index.html?raw';
import { productList, renderAt } from '../test/fixtures';
import { THEME_KEY } from './theme';

/** Runs index.html's inline script, the one that sets the theme before the first paint. */
function runFirstPaintScript(): void {
  const script = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1];
  if (script === undefined) throw new Error('index.html has no inline script');
  document.documentElement.removeAttribute('data-theme');
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  const run = new Function(script) as () => void;
  run();
}

const server = setupServer(http.get('/api/products', () => HttpResponse.json(productList('NO'))));

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});
afterEach(() => {
  server.resetHandlers();
  vi.unstubAllGlobals();
});
afterAll(() => {
  server.close();
});

describe('the theme', () => {
  it('is dark by default, even when the system asks for light', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('light'),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    runFirstPaintScript();
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('keeps a saved light theme, and anything else is dark', () => {
    window.localStorage.setItem(THEME_KEY, 'light');
    runFirstPaintScript();
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');

    window.localStorage.setItem(THEME_KEY, 'sepia');
    runFirstPaintScript();
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('switches from the header and remembers the choice', async () => {
    const user = userEvent.setup();
    renderAt('/visit');
    await user.click(screen.getByRole('button', { name: 'Switch to the light theme' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    expect(window.localStorage.getItem(THEME_KEY)).toBe('light');
    await user.click(screen.getByRole('button', { name: 'Switch to the dark theme' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });
});
