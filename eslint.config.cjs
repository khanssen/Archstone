const globals = require("globals");

module.exports = [
  // 1) Ignore vendor/template assets (the stuff causing your CI noise)
  {
    ignores: [
      "Content/HTML Template/**",
      "node_modules/**",
      "dist/**",
      "build/**",
      "coverage/**",
      "vendor/**"
    ],
  },

  // 2) Default JS rules for the repo
  {
    files: ["**/*.{js,cjs,mjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: {
        ...globals.browser,
        ...globals.jquery,
        WOW: "readonly",
      },
    },
    rules: {
      semi: ["error", "always"],
      "no-undef": "off",
      "no-unused-vars": ["warn", { args: "none" }],
      "no-redeclare": "warn",
    },
  },

  // 3) Node-specific files (if you ever lint these)
  {
    files: ["**/gulpfile.js", "**/*.config.{js,cjs}", "**/*.cjs"],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
];
