import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The API the dev server proxies /api to. Port 8000 may be taken on a machine;
// set STOREFRONT_API_URL (e.g. http://127.0.0.1:8700) to point elsewhere.
const api = process.env.STOREFRONT_API_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: api,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
});
