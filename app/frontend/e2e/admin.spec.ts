import { test, expect } from "@playwright/test";

/**
 * Admin panel: knowledge-base management and answer-quality analytics —
 * the "business side" a client actually operates.
 */
test.describe("admin panel", () => {
  test("shows knowledge base and quality stats", async ({ page }) => {
    await page.goto("");

    await page.getByRole("button", { name: /admin/i }).click();

    // Knowledge base documents are listed.
    await expect(page.getByText("Shipping Policy", { exact: false })).toBeVisible();

    // Quality analytics render (grounded-rate is the key product metric).
    await expect(page.getByText(/grounded/i).first()).toBeVisible();
  });

  test("chat and admin tabs switch without losing the page", async ({ page }) => {
    await page.goto("");

    await page.getByRole("button", { name: /admin/i }).click();
    await expect(page.getByText(/grounded/i).first()).toBeVisible();

    await page.getByRole("button", { name: /chat/i }).click();
    await expect(page.getByRole("textbox")).toBeVisible();
  });
});
