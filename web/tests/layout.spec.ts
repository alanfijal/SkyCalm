import { expect, test, type Page } from "@playwright/test";

const replay = "gfs-20261124-12";

async function openReplay(page: Page) {
  await page.goto("/");
  await page.getByLabel("Weather source").selectOption(replay);
  await expect(page.getByRole("slider")).toHaveAttribute("max", "93");
  await expect(
    page.getByRole("button", { name: "Fit route to map" }),
  ).toBeEnabled();
  await page.evaluate(() => document.fonts.ready);
}

const viewports = [
  { width: 320, height: 640 },
  { width: 390, height: 844 },
  { width: 768, height: 900 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
];

for (const viewport of viewports) {
  test(`flight controls and route fit at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await openReplay(page);
    const map = page.getByRole("region", { name: /Route map/ });
    const planner = page.getByRole("region", { name: "Your flight" });
    const slider = page.getByRole("slider");

    if (viewport.width < 960) {
      const edit = page.getByRole("button", { name: "Edit flight" });
      await expect(edit).toHaveAttribute("aria-expanded", "false");
      expect((await map.boundingBox())!.y).toBeLessThan(viewport.height * 0.67);
      await edit.click();
    } else {
      await expect(slider).toBeInViewport();
    }

    const card = (await planner.boundingBox())!;
    for (const field of [
      page.getByLabel("Departure date", { exact: true }),
      page.getByLabel("Departure time UTC"),
    ]) {
      await expect(field).toBeVisible();
      const box = (await field.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(card.x);
      expect(box.x + box.width).toBeLessThanOrEqual(card.x + card.width);
      expect(
        await field.evaluate((el) => el.scrollWidth - el.clientWidth),
      ).toBeLessThanOrEqual(1);
    }
    const sourceFits = await page
      .getByLabel("Weather source")
      .evaluate((select: HTMLSelectElement) => {
        const style = getComputedStyle(select);
        const ctx = document.createElement("canvas").getContext("2d")!;
        ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const available =
          select.clientWidth -
          parseFloat(style.paddingLeft) -
          parseFloat(style.paddingRight);
        return (
          ctx.measureText(select.selectedOptions[0].text).width <= available + 1
        );
      });
    expect(sourceFits).toBe(true);
    const to = planner.getByRole("button", { name: /Arrival airport/ });
    await to.click();
    await expect(page.getByRole("listbox")).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    ).toBe(0);
    await page.keyboard.press("Escape");
    await expect(to).toBeFocused();

    if (viewport.width < 960) {
      await page.getByRole("button", { name: "Forecast flight" }).click();
      await expect(
        page.getByRole("button", { name: "Edit flight" }),
      ).toBeFocused();
    }
    const area = (await map.boundingBox())!;
    for (const label of await map.locator(".globe-airport span").all()) {
      const tag = (await label.boundingBox())!;
      expect(tag.x).toBeGreaterThanOrEqual(area.x - 1);
      expect(tag.x + tag.width).toBeLessThanOrEqual(area.x + area.width + 1);
      expect(tag.y).toBeGreaterThanOrEqual(area.y - 1);
      expect(tag.y + tag.height).toBeLessThanOrEqual(area.y + area.height + 1);
    }
    if (viewport.width === 1920)
      expect((await page.locator("main").boundingBox())!.width).toBeGreaterThan(
        1700,
      );
  });
}

test("the palette follows the theme without moving the map or the selected point", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openReplay(page);
  const slider = page.getByRole("slider");
  await slider.fill("26");
  const point = page.locator(".globe-plane");
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(point).toBeAttached();
  const transform = await point.evaluate((el) => el.style.transform);
  const canvas = await page.locator(".maplibregl-canvas").elementHandle();
  const weatherCalls: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) weatherCalls.push(request.url());
  });
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator("body")).toHaveCSS("color", "rgb(15, 23, 42)");
  await expect(
    page.locator(".legend span").filter({ hasText: "Light" }).locator("i"),
  ).toHaveCSS("background-color", "rgb(184, 134, 11)");
  await expect(slider).toHaveValue("26");
  expect(await point.evaluate((el) => el.style.transform)).toBe(transform);
  expect(await canvas?.evaluate((el) => el.isConnected)).toBe(true);
  expect(weatherCalls).toEqual([]);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(
    page.locator(".legend span").filter({ hasText: "Light" }).locator("i"),
  ).toHaveCSS("background-color", "rgb(244, 211, 94)");
});

test("a visible route section stays selectable after resizing", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openReplay(page);
  const slider = page.getByRole("slider");
  await slider.fill("24");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Edit flight" })).toBeVisible();
  await expect(slider).toHaveValue("24");
  const map = page.getByRole("region", { name: /Route map/ });
  await map.scrollIntoViewIfNeeded();
  const marker = page.locator(".globe-plane");
  // Pick a point away from the marker and endpoints to exercise the ribbon's hit area.
  await slider.fill("68");
  await map.scrollIntoViewIfNeeded();
  const target = (await marker.boundingBox())!;
  await slider.fill("24");
  await map.scrollIntoViewIfNeeded();
  await page.mouse.click(
    target.x + target.width / 2,
    target.y + target.height / 2,
  );
  await expect
    .poll(async () => Math.abs(Number(await slider.inputValue()) - 68))
    .toBeLessThanOrEqual(3);
});
