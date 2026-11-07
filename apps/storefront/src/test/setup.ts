import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom draws nothing: the rain canvas gets no context and stays empty.
HTMLCanvasElement.prototype.getContext = () => null;
// jsdom does not scroll; the layout scrolls to the top on each route.
window.scrollTo = () => undefined;

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  document.documentElement.setAttribute('data-theme', 'dark');
});
