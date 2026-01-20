# Dependency Analysis Report

**Generated:** January 2026
**Project:** Archstone

## Executive Summary

This analysis identified **1 security vulnerability**, **1 deprecated package**, and **significant bloat** from duplicate vendor files. The most critical issue is the use of **Owl Carousel**, which is deprecated and archived.

---

## 1. Security Vulnerabilities

### js-yaml (Moderate Severity)
| Property | Value |
|----------|-------|
| Package | `js-yaml@4.1.0` |
| Severity | Moderate (CVSS 5.3) |
| Vulnerability | Prototype pollution in merge (`<<`) |
| Advisory | [GHSA-mh29-5h37-fv8m](https://github.com/advisories/GHSA-mh29-5h37-fv8m) |
| Affected Range | 4.0.0 - 4.1.0 |
| Fix Available | Yes |

**Root Cause:** This is a transitive dependency from ESLint:
```
eslint → @eslint/eslintrc → js-yaml
```

**Remediation:**
```bash
npm audit fix
```

---

## 2. Outdated Packages

### jQuery 3.7.1 → 4.0.0

| Current | Latest | Released |
|---------|--------|----------|
| 3.7.1 | 4.0.0 | Jan 17, 2026 |

**Status:** jQuery 4.0.0 was released 3 days ago. This is a major version with breaking changes:

- Drops IE 10 and older support
- Removes deprecated APIs: `$.isArray`, `$.parseJSON`, `$.trim`, `$.type`, `$.now`, `$.isNumeric`, `$.isFunction`, `$.isWindow`, `$.camelCase`
- Changes focus event order
- Slim build no longer includes Deferreds/Callbacks

**Recommendation:**
- **Wait 2-3 months** before upgrading to let the ecosystem stabilize
- Use [jQuery Migrate Plugin](https://github.com/jquery/jquery-migrate) when upgrading
- Test all jQuery-dependent plugins (owl.carousel requires jQuery)

**References:**
- [jQuery 4.0.0 Release Notes](https://blog.jquery.com/2026/01/17/jquery-4-0-0/)
- [jQuery 4.0 Upgrade Guide](https://jquery.com/upgrade-guide/4.0/)

### Owl Carousel 2.3.4 (DEPRECATED)

| Status | Last Update | Maintained |
|--------|-------------|------------|
| **DEPRECATED** | 2019 | No |

**Critical Issue:** Owl Carousel is deprecated and archived on GitHub. The project is no longer maintained and will not receive security updates or bug fixes.

---

## 3. Bloat Analysis

### Duplicate Vendor Files

The project contains **duplicate copies** of vendor libraries:

| Location | Size | Purpose |
|----------|------|---------|
| `/js/` directory | Static files | Actually used by HTML |
| `/node_modules/` | 16 MB | Not referenced by HTML |
| `/owl carousel/` | 1.5 MB | Full source copy (unused) |

**Files in `/js/` directory (actually used):**
- `jquery-3.7.1.min.js` (289 KB)
- `owl.carousel.min.js` (44 KB)
- `jquery-ui.min.js` (248 KB)
- `bootstrap.bundle.min.js` (77 KB)
- Plus 14 other JS files

**Recommendation:** The `npm` packages may be unnecessary since static vendor files in `/js/` are what the HTML actually loads.

### Dependency Count

| Type | Count | Notes |
|------|-------|-------|
| Production deps | 2 | jquery, owl.carousel |
| Dev deps | 3 | eslint + plugins |
| Transitive deps | 83 | Mostly from ESLint |
| **Total** | 88 | Reasonable for dev tooling |

---

## 4. Recommendations

### Immediate Actions (High Priority)

1. **Fix security vulnerability:**
   ```bash
   npm audit fix
   ```

2. **Remove unused vendor copy:**
   ```bash
   rm -rf "owl carousel/"
   ```
   This directory contains a full copy of Owl Carousel source (1.5 MB) that is not used.

### Short-Term Actions

3. **Plan Owl Carousel replacement:**

   The deprecated Owl Carousel should be replaced with an actively maintained alternative:

   | Alternative | jQuery Required | Size | Recommendation |
   |-------------|-----------------|------|----------------|
   | [Swiper.js](https://swiperjs.com/) | No | 41 KB | Best feature parity |
   | [Tiny Slider](https://github.com/ganlanyuan/tiny-slider) | No | 36 KB | Lighter weight |
   | [Splide](https://splidejs.com/) | No | 29 KB | Modern, accessible |
   | [Keen Slider](https://keen-slider.io/) | No | 6 KB | Smallest size |

   **Recommended:** Swiper.js - Most similar API to Owl Carousel, actively maintained, excellent documentation.

4. **Evaluate npm usage:**

   Consider removing npm production dependencies if they're not actually used:
   ```json
   // HTML loads from /js/, not node_modules
   <script src="/js/jquery-3.7.1.min.js"></script>
   <script src="/js/owl.carousel.min.js"></script>
   ```

   If you're only using ESLint as a dev tool, you could remove production deps entirely.

### Long-Term Actions

5. **jQuery 4.0 upgrade path:**
   - Wait for ecosystem stability (2-3 months)
   - Run jQuery Migrate plugin to identify compatibility issues
   - Test all jQuery plugins for compatibility
   - Note: If replacing Owl Carousel with a vanilla JS alternative, jQuery may become removable

6. **Consider removing jQuery entirely:**

   Modern alternatives exist for all jQuery functionality used:
   - DOM manipulation: Native `querySelector`, `classList`, etc.
   - AJAX: `fetch()` API
   - Animations: CSS animations/transitions
   - UI components: Modern vanilla JS libraries

---

## 5. Package.json Cleanup Suggestions

Current `package.json` has some placeholder values that should be updated:

```json
{
  "description": "",           // Add project description
  "main": "index.js",          // Remove if not a Node module
  "scripts": {
    "test": "echo \"Error: no test specified\" && exit 1"  // Remove or add real tests
  },
  "keywords": [],              // Add relevant keywords
  "author": ""                 // Add author information
}
```

---

## Summary Table

| Issue | Severity | Effort | Recommendation |
|-------|----------|--------|----------------|
| js-yaml vulnerability | Moderate | Low | `npm audit fix` |
| Owl Carousel deprecated | High | High | Replace with Swiper.js |
| Duplicate vendor files | Low | Low | Remove `/owl carousel/` dir |
| jQuery outdated | Low | Medium | Wait, then upgrade with migrate plugin |
| Unused npm production deps | Low | Low | Consider removal |

---

## References

- [Owl Carousel Deprecation Issue](https://github.com/OwlCarousel2/OwlCarousel2/issues/2672)
- [Owl Carousel Alternatives](https://www.saashub.com/owl-carousel-alternatives)
- [jQuery 4.0.0 Release](https://blog.jquery.com/2026/01/17/jquery-4-0-0/)
- [jQuery Upgrade Guide](https://jquery.com/upgrade-guide/4.0/)
- [js-yaml Security Advisory](https://github.com/advisories/GHSA-mh29-5h37-fv8m)
