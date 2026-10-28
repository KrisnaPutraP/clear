import { expect, test } from "@playwright/test";

test("planner can investigate, approve, reassess, and review a covered case", async ({
  page,
}) => {
  const errors: string[] = [];
  let holdAnalysis = false;
  await page.route(/\/api\/clear\/cases\/[^/?]+$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const response = await route.fetch();
    const item = await response.json();
    await route.fulfill({
      response,
      json: holdAnalysis
        ? { ...item, status: "analyzing", running: true, plan: null }
        : item,
    });
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Scripted development mode.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Your next move starts here.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Vessel ETA changed/ }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/workspace-empty.png",
    fullPage: true,
  });

  holdAnalysis = true;
  await page.getByRole("button", { name: /Customs document hold/ }).click();
  await expect(page.getByText("Event received", { exact: true })).toBeVisible();
  await expect(
    page.getByText("CLEAR is working on this case", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".analysis-icon .clear-mark[data-active='true']"),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-analyzing.png",
    fullPage: true,
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page
      .locator(".analysis-icon .clear-needle")
      .evaluate((element) =>
        parseFloat(getComputedStyle(element).animationDuration),
      ),
  ).toBeLessThan(0.1);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  holdAnalysis = false;
  await expect(page.locator(".case-banner .status")).toHaveText(
    "Awaiting approval",
  );
  await expect(
    page.getByText("Validator rejected", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".case-progress")
      .getByRole("button", { name: "Review transfer" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Demo event simulator/ }),
  ).toHaveAttribute("aria-expanded", "false");
  await page.screenshot({
    path: "test-results/workspace-overview.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: /^Documents/ }).click();
  await expect(page.locator(".doc-mismatch")).not.toHaveCount(0);
  await expect(page.locator(".doc-match")).not.toHaveCount(0);
  await expect(page.locator(".quantity-source.reference")).toContainText("120");
  await expect(page.locator(".quantity-source.mismatch")).toContainText("112");
  await expect(
    page.getByText("Quantity mismatch found", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-documents.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Inventory", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Plant 1100", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".plant").first()).toContainText("38");
  await page.getByRole("tab", { name: /^Approval/ }).click();
  await expect(
    page.getByText("Approval creates a stock transport order", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reject", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText("Plant 1200", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-approval.png",
    fullPage: true,
  });
  let failDecision = true;
  await page.route("**/api/clear/cases/*/decisions", (route) =>
    failDecision
      ? route.fulfill({
          status: 409,
          contentType: "application/json",
          body: '{"detail":"The case changed. Review the current plan."}',
        })
      : route.continue(),
  );
  await page
    .getByRole("button", { name: "Approve transfer", exact: true })
    .click();
  await expect(
    page
      .locator(".approval-card")
      .getByText("Decision not recorded", { exact: true }),
  ).toBeVisible();
  failDecision = false;
  await page
    .getByRole("button", { name: "Approve transfer", exact: true })
    .click();
  await expect(
    page.getByText("Transfer approved", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".case-banner .status")).toHaveText("Monitoring");
  await page.getByRole("tab", { name: "Approval", exact: true }).click();
  await expect(page.getByText(/Order created:/)).toBeVisible();

  await page.getByRole("button", { name: /Demo event simulator/ }).click();
  await page.getByRole("button", { name: /Vessel ETA changed/ }).click();
  await expect(page.locator(".case-banner .status")).toHaveText(
    "Needs a decision",
  );
  await expect(
    page.getByText("A decision needs your attention", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Demo event simulator/ }).click();
  await page.getByRole("button", { name: /Port congestion/ }).click();
  await expect(page.locator(".case-banner .status")).toHaveText("Monitoring");
  await expect(page.locator(".case-banner")).toContainText("SHP-1002");
  await expect(page.locator(".case-link")).toHaveCount(2);
  await page.getByRole("tab", { name: "Approval", exact: true }).click();
  await expect(
    page.getByText(/No transfer is awaiting approval/),
  ).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Exception workspace", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/workspace-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("connection errors explain paused decisions and allow recovery", async ({
  page,
}) => {
  let offline = true;
  await page.route("**/api/clear/health", (route) =>
    offline
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: '{"detail":"Service temporarily unavailable"}',
        })
      : route.continue(),
  );
  await page.goto("/");
  await expect(page.locator(".notice-error[role='alert']")).toContainText(
    "Decisions are disabled",
  );
  await expect(page.locator(".notice-error[role='alert']")).toContainText(
    "Updates paused",
  );
  offline = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByText("API connected", { exact: true })).toBeVisible();
  await expect(page.locator(".notice-error[role='alert']")).toHaveCount(0);
  await page.getByRole("tab", { name: "Overview", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: /^Approval/ })).toBeFocused();
  await page.keyboard.press("Home");
  await expect(
    page.getByRole("tab", { name: "Overview", exact: true }),
  ).toBeFocused();
});
