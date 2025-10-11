// eslint.config.cjs
const js = require("@eslint/js");
const globals = require("globals");

module.exports = [
  {
    files: ["**/*.js"],
    ignores: [
      "node_modules/**",
      "dist/**",
      "build/**",
      "vendor/**",
      "js/*.min.js"
    ],
    languageOptions: {
      ecmaVersion: 5,      // your slider is ES5-style
      sourceType: "script",
      globals: {
        ...globals.browser,
        $: "readonly",
        jQuery: "readonly",
        console: "readonly",
        window: "readonly",
        document: "readonly",
      },
    },
    rules: {
      // mimic common Super-Linter defaults
      "no-console": "warn",          // we’ll silence specific lines inline
      "eqeqeq": "error",
      "no-implied-eval": "error",
      "no-unused-vars": ["warn", { args: "after-used", varsIgnorePattern: "^_" }],
      "no-unsafe-finally": "error"
    },
  },
  js.configs.recommended, // ESLint recommended rules
];
