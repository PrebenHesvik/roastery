import en from './en.json';

export type Key = keyof typeof en;
export type Vars = Readonly<Record<string, string | number>>;

/** The copy for `key`, with `{name}` replaced from `vars`. A name with no value stays as written. */
export function t(key: Key, vars?: Vars): string {
  const text: string = en[key];
  if (vars === undefined) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = vars[name];
    return value === undefined ? whole : String(value);
  });
}
