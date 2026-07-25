import { test, expect } from "@playwright/test";

/**
 * Honest-refusal path: an off-topic question must produce a transparent
 * "not in my documents" answer — no invented facts, no fake citations.
 * That transparency is the product's core trust promise, so it gets its
 * own spec.
 *
 * This spec was written by an AI agent from the plain-English flow
 * description in TESTING.md ("Flow: honest refusal") — see that file for
 * the conventions that make automated test-writing safe in this suite.
 */
test.describe("honest refusal", () => {
  test("off-topic question is refused with no citations", async ({ page }) => {
    await page.goto("");

    const input = page.getByRole("textbox");
    await input.fill("Who won the 2022 FIFA World Cup?");
    await input.press("Enter");

    // The refusal streams in like any other answer…
    await expect(page.getByText(/couldn't find anything about that/i)).toBeVisible({
      timeout: 20_000,
    });

    // …is flagged as ungrounded…
    await expect(page.getByText(/not found in documents/i)).toBeVisible();

    // …and — critically — shows zero source chips. A refusal that cites
    // documents would be lying about where it looked.
    await expect(page.getByText("Sources:", { exact: false })).toHaveCount(0);
  });
});
