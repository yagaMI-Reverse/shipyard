import { test, expect } from "@playwright/test";

/**
 * Core money path: a visitor asks a question and gets a grounded, cited
 * answer streamed back. If this breaks, the product is down no matter what
 * else works.
 */
test.describe("chat flow", () => {
  test("answers a shipping question with sources", async ({ page }) => {
    await page.goto("");

    const input = page.getByRole("textbox");
    await input.fill("How long does shipping take, and is it free?");
    await input.press("Enter");

    // The user bubble renders immediately…
    await expect(page.getByText("How long does shipping take", { exact: false })).toBeVisible();

    // …then the streamed answer lands, grounded in the shipping policy.
    await expect(page.getByText(/business days/i)).toBeVisible();

    // Citations are the product's trust feature — they must be present.
    await expect(page.getByText("Sources:", { exact: false })).toBeVisible();
    await expect(page.getByText("Shipping Policy", { exact: false })).toBeVisible();
  });

  test("suggestion chip fills the flow end-to-end", async ({ page }) => {
    await page.goto("");

    // Clicking a suggestion must produce a full answered exchange, not just
    // populate the input.
    await page.getByText(/shipping/i).first().click();
    await expect(page.getByText("Sources:", { exact: false })).toBeVisible();
  });

  test("honestly declines questions outside the knowledge base", async ({ page }) => {
    await page.goto("");

    const input = page.getByRole("textbox");
    await input.fill("What is the capital of France?");
    await input.press("Enter");

    // Grounded RAG must not hallucinate an answer — it should say the docs
    // don't cover this (phrasing varies, so match loosely on the refusal).
    await expect(page.getByText(/don't|couldn't|not.*(find|cover|contain)|no information/i)).toBeVisible();
  });
});
