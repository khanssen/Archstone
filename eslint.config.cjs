import js from "@eslint/js";

// eslint.config.cjs
// Flat config for ESLint v8.57+ (works with Super-Linter v7)
const js = require("@eslint/js");

module.exports = [
  // Global ignores
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/vendor/**",
      "**/docs/**",
      "**/documentation/**",
      "**/docs_src/**",
      "**/tests/**",
      "**/test/**",
      "**/*.min.js",
      "owl carousel/**",
      // If these folders are copies of templates/vendors, ignore them too:
      "Content/**/js/*.min.js",
      "HTML Template/**",
    ],
  },

  // Default: browser code
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "script",
      globals: {
        // Browser globals so ESLint stops complaining
        window: "readonly",
        document: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        fetch: "readonly",

        // Common libs your code references
        jQuery: "readonly",
        $: "readonly",
        WOW: "readonly",        // wow.js
        google: "readonly",     // Google Maps
        PR: "readonly",         // google-code-prettify
        prettyPrintOne: "readonly",
        hljs: "readonly",       // highlight.js (if used)
      },
    },
    rules: {
      "no-console": "off",
      "no-inner-declarations": "off",
      "no-prototype-builtins": "off",
      // loosen redeclare temporarily if you need it:
      // "no-redeclare": "off",
    },
  },

  // Node-only files (gulp/grunt etc.)
  {
    files: ["**/gulpfile.js", "**/Gruntfile.js", "**/*.cjs"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "script",
      globals: {
        module: "readonly",
        require: "readonly",
        exports: "readonly",
        __dirname: "readonly",
        process: "readonly",
      },
    },
    rules: {
      "no-console": "off",
    },
  },

  // Test files (if any use QUnit/Jest etc.) – optional
  // {
  //   files: ["**/test/**/*.js", "**/tests/**/*.js"],
  //   languageOptions: {
  //     globals: {
  //       module: "readonly",
  //       test: "readonly",
  //       expect: "readonly",
  //       equal: "readonly",
  //       deepEqual: "readonly",
  //       start: "readonly",
  //     },
  //   },
  // },
  js.configs.recommended,
];

export default [
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "script",
      globals: {
        // Browser globals
        window: "readonly",
        document: "readonly",
        navigator: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        console: "readonly",
        Image: "readonly",
        fetch: "readonly",

        // jQuery
        $: "readonly",
        jQuery: "readonly",

        // Define AMD support
        define: "readonly",
        module: "readonly",
        exports: "readonly",

        // Google Maps
        google: "readonly",

        // Third-party libraries used in your code
        WOW: "readonly",
        hljs: "readonly",
      },
    },
    rules: {
      "no-console": "off",
      "no-unused-vars": ["warn", { args: "none", varsIgnorePattern: "^_\\$?" }],
      "no-redeclare": "off",
      "no-undef": "off",
    },
  },
];
