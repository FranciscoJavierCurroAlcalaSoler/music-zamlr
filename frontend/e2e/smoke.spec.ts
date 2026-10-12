import { expect, test } from "./fixtures";

test("the page reaches the backend and shows the three tabs", async ({
  page,
}) => {
  await page.goto("/");

  await expect(page.getByRole("tab", { name: "Collections" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Compare" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Settings" })).toBeVisible();
});
