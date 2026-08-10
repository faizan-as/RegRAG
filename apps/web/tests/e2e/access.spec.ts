import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("protected routes redirect to the login workspace", async ({ page }) => {
  await page.goto("/research");

  await expect(page).toHaveURL(/\/login(?:\?|$)/);
  await expect(page.getByRole("heading", { name: "Regulatory Workspace Login" })).toBeVisible();
});

test("login and password reset are accessible and fit the viewport", async ({ page }) => {
  await page.goto("/login?next=https://example.com/not-allowed");

  await expect(page.getByRole("textbox", { name: "Email" })).toBeVisible();
  await page.getByRole("button", { name: "Forgot password" }).click();
  await expect(page.getByRole("button", { name: "Send reset email" })).toBeVisible();

  const viewport = page.viewportSize();
  const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(viewport).not.toBeNull();
  expect(documentWidth).toBeLessThanOrEqual(viewport?.width ?? documentWidth);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await expect(page).toHaveScreenshot("login-reset.png", { fullPage: true });
});