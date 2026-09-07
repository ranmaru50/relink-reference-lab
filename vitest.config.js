// vitest.config.js
// Web UI の DOM 操作を jsdom 上で単体テストする設定。

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    environmentOptions: {
      jsdom: {
        url: "https://lab.example/",
      },
    },
    include: ["tests/**/*.test.js"],
  },
});
