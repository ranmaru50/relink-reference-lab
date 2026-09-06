// eslint.config.js
// ブラウザー JavaScript と Vitest の flat config。

import eslint from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: ["public/vendor/**", "vendor/**"],
  },
  eslint.configs.recommended,
  {
    files: ["public/**/*.js", "tests/**/*.test.js", "vitest.config.js", "eslint.config.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.vitest,
      },
    },
    rules: {
      "no-console": "warn",
    },
  },
];
