// @ts-check
import { defineConfig } from 'astro/config';

// GitHub Pages project site: https://tmhsdigital.github.io/USA-Election-Tracker/
export default defineConfig({
  site: 'https://tmhsdigital.github.io',
  base: '/USA-Election-Tracker',
  trailingSlash: 'always',
  output: 'static',
  build: {
    format: 'directory',
    inlineStylesheets: 'auto',
  },
  // English only in v0. Spanish ("es") is added by listing it here and adding
  // src/i18n/es.json; routes are already locale-aware.
  i18n: {
    locales: ['en'],
    defaultLocale: 'en',
    routing: { prefixDefaultLocale: false },
  },
  compressHTML: true,
});
