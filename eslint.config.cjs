// eslint.config.cjs
const eslintJs = require("@eslint/js");
const globals = require("globals");

module.exports = [
  {
    ignores: [
      "**/*.min.js",
      "**/dist/**",
      "**/vendor/**",
      "**/assets/js/vendor/**",
      "**/assets/js/old/**",
      "**/node_modules/**",
      "**/jquery/**",
      "**/HTML Template/**",
      "**/Content/**",
      "**/Archive/**",
      "**/documentation/**",
      "**/blogs/**",
      "**/states/**",
      "**/Certificates/**",
      "**/font/**",
      "js/**",
      "**/owl carousel/**"
    ]
  },
  {
    ...eslintJs.configs.recommended,
    files: ["app/js/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.jquery,
        WOW: "readonly"
      }
    },
    rules: {
      semi: ["error", "always"],
      "no-unused-vars": ["warn", { args: "none" }],
      "no-redeclare": "warn"
    }
  }
];
