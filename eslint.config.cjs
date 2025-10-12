import js from "@eslint/js";

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
