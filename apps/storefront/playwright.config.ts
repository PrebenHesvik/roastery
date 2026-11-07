import { defineConfig, devices } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * The smoke runs against the real API on a fresh, seeded sqlite db in a temp folder. Ports 8000
 * and 5173 may be taken by other programs, so the API listens on 8700 and Vite on 5180. Playwright
 * starts both servers and stops them (and their children) when the run ends.
 */
const API_PORT = 8700;
const WEB_PORT = 5180;
const repo = fileURLToPath(new URL('../..', import.meta.url));
const dbs = (process.env.E2E_DB_DIR ??= mkdtempSync(join(tmpdir(), 'sydvest-e2e-')));
const sqlite = (name: string) => `sqlite:///${join(dbs, name).replaceAll('\\', '/')}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 60_000,
  use: {
    baseURL: `http://localhost:${String(WEB_PORT)}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `uv run python -m roastery_api seed && uv run python -m uvicorn roastery_api.app:app --port ${String(API_PORT)}`,
      cwd: repo,
      env: {
        ROASTERY_DATABASE_URL: sqlite('shop.db'),
        SHOP_API_STATE_URL: sqlite('state.db'),
      },
      url: `http://127.0.0.1:${String(API_PORT)}/products?country=NO`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: `npx vite --port ${String(WEB_PORT)} --strictPort`,
      env: { STOREFRONT_API_URL: `http://127.0.0.1:${String(API_PORT)}` },
      url: `http://localhost:${String(WEB_PORT)}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
