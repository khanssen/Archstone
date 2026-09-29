// eslint.config.cjs (Flat config)
const globals = require("globals");

module.exports = [
  {
    //  MUST BE FIRST
    ignores: [
      "Content/HTML Template/**",
      "HTML Template/**",

      "Content/js/**",
      "Content/app/js/**",
      "Content/documentation/assets/**",

      "**/*.min.js",
      "**/gulpfile.js",

      "node_modules/**",
      "dist/**",
      "build/**",
      "coverage/**",
      "vendor/**"
    ],
  },

  {
    files: ["**/*.{js,cjs,mjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: {
        ...globals.browser,
        ...globals.jquery,
        WOW: "readonly",
        google: "readonly",
      },
    },
    rules: {
      semi: ["error", "always"],
      "no-undef": "off",
      "no-unused-vars": ["warn", { args: "none" }],
      "no-redeclare": "warn",
    },
  },
  // Node build scripts (gulpfile, *.cjs)
  {
    files: ["**/gulpfile.js", "**/*.cjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "script",
      globals: {
        ...globals.node,
      },
    },
  },
];
