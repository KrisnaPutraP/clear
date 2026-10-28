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
  await page.goto("/workspace");
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
  const planner = page.getByRole("combobox", { name: "Demo planner" });
  await planner.click();
  const customizableSelect = await page.evaluate(() =>
    CSS.supports("appearance", "base-select"),
  );
  if (customizableSelect) {
    await expect
      .poll(() => planner.evaluate((element) => element.matches(":open")))
      .toBeTruthy();
    const field = (await planner.boundingBox())!;
    const firstOption = (await page
      .getByRole("option", { name: "Rina Hartono", exact: true })
      .boundingBox())!;
    const lastOption = (await page
      .getByRole("option", { name: "Bayu Pratama", exact: true })
      .boundingBox())!;
    expect(lastOption.y + lastOption.height).toBeLessThanOrEqual(field.y - 8);
    expect(firstOption.y).toBeGreaterThanOrEqual(6);
    await page.screenshot({
      path: "test-results/planner-dropdown-desktop.png",
    });
  }
  await page.keyboard.press("Escape");
  await planner.selectOption("Bayu Pratama");
  await expect(planner).toHaveValue("Bayu Pratama");
  await planner.selectOption("Rina Hartono");
  if (customizableSelect) {
    await page.setViewportSize({ width: 1440, height: 520 });
    await planner.click();
    const first = (await page
      .getByRole("option", { name: "Rina Hartono", exact: true })
      .boundingBox())!;
    const last = (await page
      .getByRole("option", { name: "Bayu Pratama", exact: true })
      .boundingBox())!;
    expect(first.y).toBeGreaterThanOrEqual(6);
    expect(last.y + last.height).toBeLessThanOrEqual(514);
    await page.screenshot({ path: "test-results/planner-dropdown-short.png" });
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 1440, height: 1000 });
  }

  holdAnalysis = true;
  await page.getByRole("button", { name: /Customs document hold/ }).click();
  await expect(page.getByText("Event received", { exact: true })).toBeVisible();
  await expect(
    page.getByText("CLEAR is working on this case", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".analysis-icon .clear-mark[data-active='true']"),
  ).toBeVisible();
  const compass = page.locator(".analysis-icon .clear-mark");
  await expect(page.locator(".case-state-icon")).toHaveCSS(
    "background-color",
    "rgba(0, 0, 0, 0)",
  );
  await expect
    .poll(async () =>
      compass
        .locator(".compass-animated")
        .evaluate(
          (element: HTMLImageElement) =>
            element.complete &&
            element.naturalWidth > 0 &&
            element.currentSrc.endsWith(".webp"),
        ),
    )
    .toBeTruthy();
  await expect(compass.locator(".compass-animated")).toBeVisible();
  const movingFrame = await compass.screenshot();
  await page.waitForTimeout(650);
  expect(Buffer.compare(movingFrame, await compass.screenshot())).not.toBe(0);
  await expect(page.locator(".clear-orbit, .compass-edge")).toHaveCount(0);
  await page.screenshot({
    path: "test-results/workspace-analyzing.png",
    fullPage: true,
  });
  await page.locator(".analysis-state").screenshot({
    path: "test-results/compass-loading-3d.png",
  });
  await page.locator(".case-next-step").screenshot({
    path: "test-results/compass-loading-banner.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "Planner navigation" }),
  ).toBeHidden();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(
    page.getByRole("complementary", { name: "Planner navigation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Close navigation", exact: true }).last(),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeFocused();
  await expect(
    page.getByRole("complementary", { name: "Planner navigation" }),
  ).toBeHidden();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/workspace-analyzing-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(compass.locator(".compass-animated")).toBeHidden();
  await expect(compass.locator(".compass-still")).toBeVisible();
  const stillFrame = await compass.screenshot();
  await page.waitForTimeout(250);
  expect(Buffer.compare(stillFrame, await compass.screenshot())).toBe(0);
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
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  const reviewButton = await page
    .locator(".case-progress .primary-button")
    .boundingBox();
  expect(reviewButton).not.toBeNull();
  expect(reviewButton!.y + reviewButton!.height).toBeLessThanOrEqual(844);
  await page.screenshot({
    path: "test-results/workspace-mobile-decision.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
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
  await page.getByRole("tab", { name: "Monitoring", exact: true }).click();
  await expect(
    page.getByText("Monitoring is not the current stage", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "No stock transport order has been created in the current plan.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole("tab", { name: /^Approval/ }).click();
  await expect(
    page.getByText("Approval creates a stock transport order", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("radio", { name: /Another course/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve transfer", exact: true }),
  ).toBeEnabled();
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
  await page
    .locator(".case-progress")
    .getByRole("button", { name: "View monitoring", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "Monitoring", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel")).toBeFocused();
  await expect(
    page.getByRole("heading", { name: "Next follow-up", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".monitoring-view")).toContainText(
    "Arrival of the transfer at plant 1100, and the customs response.",
  );
  await expect(page.locator(".monitoring-view")).toContainText(
    "Order created: 4500001023",
  );
  await expect(
    page.locator(".monitoring-stock").getByRole("row", { name: /^1100 / }),
  ).toHaveText("110038 t20 t30 t");
  await expect(page.locator(".monitoring-view")).not.toContainText(
    "Monitoring is not the current stage",
  );
  await page.screenshot({
    path: "test-results/workspace-monitoring-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await page
    .locator(".workflow-steps")
    .getByRole("button", { name: "Monitor", exact: true })
    .click();
  const monitoringTab = (await page
    .getByRole("tab", { name: "Monitoring", exact: true })
    .boundingBox())!;
  expect(monitoringTab.x).toBeGreaterThanOrEqual(0);
  expect(monitoringTab.x + monitoringTab.width).toBeLessThanOrEqual(390);
  for (const name of [
    "Overview",
    "Documents",
    "Inventory",
    "Approval",
    "Monitoring",
  ]) {
    const bounds = (await page
      .getByRole("tab", { name: new RegExp(`^${name}`) })
      .boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/workspace-monitoring-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await page
    .locator(".next-check")
    .getByRole("button", { name: "View monitoring", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "Monitoring", exact: true }),
  ).toHaveAttribute("aria-selected", "true");

  await page.getByRole("button", { name: /Demo event simulator/ }).click();
  await page.getByRole("button", { name: /Vessel ETA changed/ }).click();
  await expect(page.locator(".case-banner .status")).toHaveText(
    "Needs a decision",
  );
  await expect(
    page.getByText("A decision needs your attention", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Make the call/ }).click();
  const resolve = page.locator(".resolve-desk");
  await expect(resolve.getByRole("radio").nth(1)).toBeChecked();
  await resolve.getByText("Another course", { exact: true }).click();
  const record = resolve.getByRole("button", { name: "Record decision" });
  await expect(record).toBeDisabled();
  await resolve
    .getByLabel(/Decision note/)
    .fill("Source 34 t from an external supplier.");
  await record.click();
  await expect(page.locator(".case-banner .status")).toHaveText("Monitoring");
  await expect(page.locator(".resolution-note")).toContainText(
    "chose a course outside the plan’s options",
  );
  await expect(page.locator(".timeline-panel")).toContainText(
    "Chose a course outside the plan's options: Source 34 t",
  );
  await page.getByRole("button", { name: /Demo event simulator/ }).click();
  await page.getByRole("button", { name: /Port congestion/ }).click();
  await expect(page.locator(".case-banner .status")).toHaveText("Monitoring");
  await expect(page.locator(".case-banner")).toContainText("SHP-1002");
  await expect(page.locator(".case-link")).toHaveCount(2);
  await page
    .locator(".case-progress")
    .getByRole("button", { name: "View monitoring", exact: true })
    .click();
  await expect(page.locator(".monitoring-view")).toContainText(
    "No stock transfer required by the current plan.",
  );
  await expect(page.locator(".monitoring-view")).toContainText(
    "Discharge progress at Tanjung Priok.",
  );
  await expect(page.locator(".monitoring-view")).not.toContainText(
    "Order created:",
  );
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
  await page.getByRole("button", { name: "Open navigation" }).click();
  await planner.click();
  if (customizableSelect) {
    const first = (await page
      .getByRole("option", { name: "Rina Hartono", exact: true })
      .boundingBox())!;
    const last = (await page
      .getByRole("option", { name: "Bayu Pratama", exact: true })
      .boundingBox())!;
    const field = (await planner.boundingBox())!;
    expect(first.y).toBeGreaterThanOrEqual(6);
    expect(last.y + last.height).toBeLessThanOrEqual(field.y - 8);
    await page.screenshot({ path: "test-results/planner-dropdown-mobile.png" });
    await page
      .getByRole("option", { name: "Bayu Pratama", exact: true })
      .click();
    await expect(planner).toHaveValue("Bayu Pratama");
    await planner.click();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("complementary", { name: "Planner navigation" }),
    ).toBeVisible();
  } else {
    await page.keyboard.press("Escape");
  }
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("complementary", { name: "Planner navigation" }),
  ).toBeHidden();
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
  await page.goto("/workspace");
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
  await expect(
    page.getByRole("tab", { name: "Monitoring", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Overview", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(
    page.getByRole("tab", { name: "Monitoring", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Home");
  await expect(
    page.getByRole("tab", { name: "Overview", exact: true }),
  ).toBeFocused();
});
