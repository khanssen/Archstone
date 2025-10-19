// eslint.config.cjs
const eslintJs = require("@eslint/js");
let tseslint;
try {
  // optional, only if you lint TS:
  tseslint = require("typescript-eslint");
} catch {
  tseslint = null;
}

module.exports = [
  eslintJs.configs.recommended,
  ...(tseslint ? tseslint.configs.recommended : []),
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    ignores: ["**/node_modules/**", "dist/**", "build/**", "coverage/**", "vendor/**"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module" // or "commonjs" to match your codebase
    },
    rules: {
      // your rules here
    }
  }
];
