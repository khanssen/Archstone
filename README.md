# Super Duper Linter Splinter

[![Super Duper Linter Splinter](https://github.com/khanssen/Archstone/actions/workflows/linter.yml/badge.svg)](https://github.com/khanssen/Archstone/actions/workflows/linter.yml)

**Super Duper Linter Splinter** is an automated quality-control workflow for this repository.  
It runs continuous linting and syntax validation across all supported file types in parallel, ensuring consistent style, secure code hygiene, and clean configuration files before merge.

---

###  What It Does
- **JavaScript / TypeScript linting**  
  Uses ESLint (flat config) to enforce modern JavaScript standards and detect logic or formatting errors.
- **Metadata validation**  
  Runs YAML, Markdown, and JSON linting to prevent broken syntax in workflows, docs, and configuration files.
- **Parallel job execution**  
  Splits linting tasks into multiple concurrent runners for faster checks.
- **Step summaries**  
  Publishes a detailed Markdown summary of rule violations (if any) directly in the pull request view.
- **Caching**  
  Uses GitHub’s npm cache to speed up dependency installs.

---

This workflow is defined in  
[`./.github/workflows/super-linter.yml`](.github/workflows/super-linter.yml)



It triggers automatically on:
- Pushes to `main`
- Pull requests
- Manual runs via “Run workflow” in the Actions tab

Each job spins up a lightweight Ubuntu runner, installs dependencies, and executes Super-Linter v7.4.0 with project-specific rules.

---

###  Why It Matters
By catching errors early in CI, Super Duper Linter Splinter:
- Keeps the main branch deploy-ready
- Enforces consistent formatting across contributors
- Detects potential misconfigurations in YAML and Markdown files
- Reduces time spent on manual code review and style correction

---

###  Extend It
To expand validation:
```yaml
VALIDATE_HTML: true
VALIDATE_CSS: true
VALIDATE_BASH: true
VALIDATE_DOCKERFILE: true