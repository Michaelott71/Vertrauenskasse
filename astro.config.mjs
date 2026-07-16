import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://majorsgolfbox.de',
  trailingSlash: 'never',
  i18n: {
    locales: ['de', 'en'],
    defaultLocale: 'de',
    routing: {
      prefixDefaultLocale: true,
    },
  },
});
