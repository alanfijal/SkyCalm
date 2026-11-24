import { defineConfig } from "@playwright/test";

const baseURL = "http://127.0.0.1:4187";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 45_000,
  use: {
    baseURL,
    reducedMotion: "reduce",
    launchOptions: {
      args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    },
  },
  webServer: {
    command: "python3 -B -m services.forecast.local --port 4187",
    cwd: "..",
    url: baseURL + "/api/runs",
    timeout: 15_000,
  },
});
