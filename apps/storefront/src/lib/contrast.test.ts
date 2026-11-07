import { describe, expect, it } from 'vitest';
import css from '../styles/tokens.css?raw';

function tokens(selector: string): Record<string, string> {
  const block = new RegExp(selector + String.raw`\s*\{([^}]*)\}`).exec(css);
  if (block?.[1] === undefined) throw new Error(`no block for ${selector}`);
  return Object.fromEntries(
    [...block[1].matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]),
  ) as Record<string, string>;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

// Foreground token, background token: every pairing the pages may set as text.
const BODY_PAIRS: [string, string][] = [
  ['text', 'ground'],
  ['text', 'surface'],
  ['muted', 'ground'],
  ['muted', 'surface'],
  ['oilskin-text', 'ground'],
  ['oilskin-text', 'surface'],
  ['window', 'ground'],
  ['window', 'surface'],
  ['on-oilskin', 'oilskin'],
  ['on-oilskin-muted', 'oilskin'],
  ['danger', 'ground'],
  ['danger', 'surface'],
  ['text', 'surface-raised'],
  ['muted', 'surface-raised'],
  ['on-window', 'window-field'],
  ['on-window-muted', 'window-field'],
];

const THEMES = {
  dark: String.raw`:root,\s*:root\[data-theme='dark'\]`,
  light: String.raw`:root\[data-theme='light'\]`,
};

describe.each(Object.entries(THEMES))('%s theme contrast', (_, selector) => {
  const theme = tokens(selector);
  it.each(BODY_PAIRS)('%s on %s is at least 4.5:1', (fg, bg) => {
    const [front, back] = [theme[fg], theme[bg]];
    expect(front, fg).toBeDefined();
    expect(back, bg).toBeDefined();
    expect(contrast(front as string, back as string)).toBeGreaterThanOrEqual(4.5);
  });
});
