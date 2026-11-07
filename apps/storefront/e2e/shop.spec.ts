import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const REVIEW = fileURLToPath(new URL('../../../.impeccable/review/', import.meta.url));

test.describe.configure({ mode: 'serial' });

let paidOrder = '';

async function fillContact(page: Page) {
  await page.getByLabel('Full name').fill('Kari Nordmann');
  await page.getByLabel('E-mail').fill('kari@example.invalid');
  await page.getByLabel('Street address').fill('Strandkaien 1');
  await page.getByLabel('Postal code').fill('5003');
  await page.getByLabel('City').fill('Bergen');
}

async function checkOutInNorway(page: Page) {
  await page.getByRole('link', { name: /^Bag, \d+ items?$/ }).click();
  await expect(page.getByRole('heading', { name: 'Your bag' })).toBeVisible();
  await page.getByRole('link', { name: 'Check out' }).click();
  const norway = page.getByRole('radio', { name: /Norway/ });
  await norway.check();
  await expect(norway).toBeChecked();
  await fillContact(page);
  await page.getByRole('button', { name: /Place order/ }).click();
  await expect(
    page.getByRole('heading', { name: 'A test payment. No money moves.' }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/pay\//);
}

test('browse, add, check out in Norway, approve: the order is paid', async ({ page }) => {
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Rain all week. Coffee all week.' }),
  ).toBeVisible();

  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Beans' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Beans' })).toBeVisible();
  await page.getByRole('link', { name: 'Morning roast' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Morning roast' })).toBeVisible();
  await expect(page.getByText('NOK 129.00').first()).toBeVisible();
  await page.getByRole('button', { name: 'Add to bag' }).click();
  await expect(page.getByRole('link', { name: 'Bag, 1 item' })).toBeVisible();

  await checkOutInNorway(page);
  await page.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByRole('heading', { name: 'Status: Paid' })).toBeVisible();
  await expect(
    page.getByRole('cell', { name: 'NOK 129.00' }).or(page.getByText('NOK 129.00').first()),
  ).toBeVisible();
  paidOrder = new URL(page.url()).pathname;
});

test('a second order is declined, then approved on retry', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Add Morning roast' }).click();
  await expect(page.getByRole('link', { name: 'Bag, 1 item' })).toBeVisible();

  await checkOutInNorway(page);
  await page.getByRole('button', { name: 'Decline' }).click();
  await expect(page.getByText('The payment was declined.')).toBeVisible();
  await expect(page).toHaveURL(/\/pay\//);

  await page.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByRole('heading', { name: 'Status: Paid' })).toBeVisible();
});

/** Still the motion, wait for the face and the data, then capture. */
async function capture(page: Page, path: string, name: string, theme: 'dark' | 'light') {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript((value) => {
    window.localStorage.setItem('sydvest.theme', value);
  }, theme);
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready);
  mkdirSync(REVIEW, { recursive: true });
  await page.screenshot({ path: `${REVIEW}${name}.png`, fullPage: true });
}

test('screenshots for review', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await capture(page, '/', 'desktop', 'dark');
  await capture(page, '/', 'desktop-light', 'light');
  await capture(page, '/shop', 'shop', 'dark');
  if (paidOrder !== '') await capture(page, paidOrder, 'order', 'dark');

  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, '/', 'mobile', 'dark');

  // The roast scale fills when a bean card scrolls into view: motion on, after the fill.
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  const scale = page.locator('.street .roast').first();
  await expect(scale).toHaveAttribute('data-shown', 'false');
  await scale.scrollIntoViewIfNeeded();
  await expect(scale).toHaveAttribute('data-shown', 'true');
  await page.waitForTimeout(1600);
  await page.screenshot({ path: `${REVIEW}scale.png` });

  await capture(page, '/', 'mobile-light', 'light');

  // The checkout, with a Swedish bag: the foreign VAT wording and the NOK charge.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => {
    window.localStorage.setItem(
      'sydvest.cart',
      JSON.stringify({
        version: 1,
        country: 'SE',
        items: [
          { productId: 'P-10', qty: 2 },
          { productId: 'P-20', qty: 1 },
        ],
      }),
    );
  });
  await capture(page, '/checkout', 'checkout', 'dark');
});
