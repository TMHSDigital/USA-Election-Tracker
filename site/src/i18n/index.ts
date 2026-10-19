import en from './en.json';

export const LOCALES = { en } as const;
export type Locale = keyof typeof LOCALES;
export type Key = keyof typeof en;
export const DEFAULT_LOCALE: Locale = 'en';

/** Translate a key with {placeholder} substitution. Missing keys fail the build. */
export function t(key: Key, vars: Record<string, string | number> = {}, locale: Locale = DEFAULT_LOCALE): string {
  const table = LOCALES[locale] as Record<string, string>;
  const template = table[key] ?? (LOCALES[DEFAULT_LOCALE] as Record<string, string>)[key];
  if (template === undefined) throw new Error(`missing i18n key: ${key}`);
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    if (!(name in vars)) throw new Error(`missing i18n var ${name} for ${key}`);
    return String(vars[name]);
  });
}

const dateFmt = new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' });
const dateTimeFmt = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'America/New_York',
  timeZoneName: 'short',
});
const intFmt = new Intl.NumberFormat('en-US');
const moneyFmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

export const fmtDate = (iso: string | null | undefined): string =>
  iso ? dateFmt.format(new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso)) : t('date.never');
export const fmtDateTime = (iso: string | null | undefined): string => (iso ? dateTimeFmt.format(new Date(iso)) : t('date.never'));
export const fmtInt = (n: number | null | undefined): string => (n == null ? '' : intFmt.format(n));
export const fmtMoney = (n: number | null | undefined): string => (n == null ? '' : moneyFmt.format(n));
export const fmtPct = (n: number | null | undefined): string => (n == null ? '' : `${n.toFixed(1)}%`);
