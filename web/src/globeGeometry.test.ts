import { afterEach, expect, it, vi } from "vitest";
import { globePalette } from "./globeGeometry";

afterEach(() => vi.unstubAllGlobals());

it("resolves short and long CSS hex colours for the WebGL route", () => {
  const tokens: Record<string, string> = {
    "--map-casing": "#fff",
    "--turb-smooth": "#1F9A86",
    "--turb-light": "#B8860B",
    "--turb-moderate": "#D0661A",
    "--turb-severe": "#C23A1C",
    "--turb-none": "#5B6B85",
  };
  vi.stubGlobal("document", { documentElement: {} });
  vi.stubGlobal("getComputedStyle", () => ({
    getPropertyValue: (name: string) => tokens[name] || "",
  }));
  const palette = globePalette();
  expect(palette.casing).toEqual([255, 255, 255]);
  expect(palette.route.light).toEqual([184, 134, 11]);
  expect(palette.route.unavailable).toEqual([91, 107, 133]);
});
