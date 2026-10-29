import { expect, test } from "@playwright/test";

test("planner can investigate, approve, reassess, and review a covered case", async ({
  page,
}) => {
  const errors: string[] = [];
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

  await page.getByRole("button", { name: /Customs document hold/ }).click();
  await expect(page.locator(".case-banner .status")).toHaveText(
    "Awaiting approval",
  );
  await expect(
    page.getByText("Validator rejected", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Documents", exact: true }).click();
  await expect(page.locator(".doc-mismatch")).not.toHaveCount(0);
  await page.getByRole("tab", { name: "Inventory", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Plant 1100", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".plant").first()).toContainText("38");
  await page.getByRole("tab", { name: "Approval", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Reject", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText("Plant 1200", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/workspace-approval.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Approve transfer", exact: true })
    .click();
  await expect(page.locator(".case-banner .status")).toHaveText("Monitoring");
  await page.getByRole("tab", { name: "Approval", exact: true }).click();
  await expect(page.getByText(/Order created:/)).toBeVisible();

  await page.getByRole("button", { name: /Vessel ETA changed/ }).click();
  await expect(page.locator(".case-banner .status")).toHaveText(
    "Needs a decision",
  );
  await expect(
    page.getByText("A decision needs your attention", { exact: true }),
  ).toBeVisible();
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
    page.getByRole("heading", { name: "Clarity through every exception." }),
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
