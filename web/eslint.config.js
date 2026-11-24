import js from "@eslint/js";
import globals from "globals";
import ts from "typescript-eslint";

export default ts.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...ts.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
  },
);
