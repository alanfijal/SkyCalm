import type { Category } from "./types";

export type Theme = "dark" | "light";

export const categoryTokens: Record<Category, string> = {
  smooth: "--turb-smooth",
  light: "--turb-light",
  moderate: "--turb-moderate",
  severe: "--turb-severe",
  unavailable: "--turb-none",
};

export const categoryColor = (category: Category) =>
  `var(${categoryTokens[category]})`;

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute(
      "content",
      getComputedStyle(root).getPropertyValue("--bg").trim(),
    );
  try {
    localStorage.setItem("skycalm-theme", theme);
  } catch {
    // The page still switches when browser storage is unavailable.
  }
}
