import { expect, test } from "@playwright/test";

test("landing page walks a case and hands an event to the workspace", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Clear the hold" }),
  ).toBeVisible();

  const stages = page.locator("#how-it-works");
  await expect(stages.getByRole("heading", { level: 2 })).toHaveText(
    "First, read every document",
  );
  await stages.getByLabel("Stage of the case").focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(stages.getByRole("heading", { level: 2 })).toHaveText(
    "Next, a planner signs it",
  );
  await stages.getByRole("button", { name: "Monitor" }).click();
  await expect(stages).toContainText("Order created · 4500001023");

  const outputs = page.locator("#outputs");
  await outputs.getByRole("button", { name: "Transfer order" }).click();
  await expect(outputs.getByRole("article")).toContainText("STO 4500001023");

  await page.getByLabel("Exception").selectOption("S1-ETA-SLIP");
  await page.getByRole("button", { name: "CLEAR", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\?event=S1-ETA-SLIP$/);
  await expect(page.locator(".event-card.suggested")).toHaveCount(1);
  expect(errors).toEqual([]);
});
