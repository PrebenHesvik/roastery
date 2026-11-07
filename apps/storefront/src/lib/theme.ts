import { useCallback, useSyncExternalStore } from 'react';

export const THEME_KEY = 'sydvest.theme';
export type Theme = 'dark' | 'light';

const listeners = new Set<() => void>();

function current(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Sets the theme on the page and remembers it; a blocked store only loses the memory. */
export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // the choice lasts for this visit
  }
  listeners.forEach((listener) => {
    listener();
  });
}

/** The theme on the page (index.html's inline script set it before paint) and a toggle. */
export function useTheme(): { theme: Theme; toggle: () => void; set: (theme: Theme) => void } {
  const theme = useSyncExternalStore<Theme>(subscribe, current, () => 'dark');
  const toggle = useCallback(() => {
    applyTheme(current() === 'dark' ? 'light' : 'dark');
  }, []);
  return { theme, toggle, set: applyTheme };
}
