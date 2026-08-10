import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const email = process.env.E2E_USER_EMAIL;
const password = process.env.E2E_USER_PASSWORD;

test.describe("authenticated workspace", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!email || !password, "E2E_USER_EMAIL and E2E_USER_PASSWORD are required.");

  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("textbox", { name: "Email" }).fill(email ?? "");
    await page.getByLabel("Password").fill(password ?? "");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/research$/);
  });

  for (const route of ["/research", "/search", "/chat", "/alerts"] as const) {
    test(`${route} has no serious accessibility violations`, async ({ page }) => {
      await page.goto(route);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });
  }
});