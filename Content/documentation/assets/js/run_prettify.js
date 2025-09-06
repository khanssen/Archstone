(function () {
  "use strict";

  // --- Safety/compat ---
  var win = window;
  var doc = document;
  var docEl = doc.documentElement;
  var head = doc.head || doc.getElementsByTagName("head")[0] || docEl;

  // Ensure callbacks target exists (used by ?callback=<name>).
  win.exports = win.exports || {};

  // Cross-browser DOM ready (lightweight, no deps).
  function contentLoaded(callback) {
    var add = doc.addEventListener ? "addEventListener" : "attachEvent";
    var rem = doc.addEventListener ? "removeEventListener" : "detachEvent";
    var pre = doc.addEventListener ? "" : "on";
    var done = false;

    function init(e) {
      if (e.type === "readystatechange" && doc.readyState !== "complete") return;
      (e.type === "load" ? win : doc)[rem](pre + e.type, init, false);
      if (!done) { done = true; callback(); }
    }

    if (doc.readyState === "complete") {
      // DOM was ready before this ran.
      setTimeout(callback, 0);
    } else {
      if (doc.createEventObject && docEl.doScroll) {
        // IE < 9
        try {
          if (!win.frameElement) {
            (function poll() {
              try { docEl.doScroll("left"); }
              catch (e) { return setTimeout(poll, 50); }
              init({ type: "load" });
            })();
          }
        } catch (e) { /* ignore */ }
      }
      doc[add](pre + "DOMContentLoaded", init, false);
      doc[add](pre + "readystatechange", init, false);
      win[add](pre + "load", init, false);
    }
  }

  // --- Parse query from script tag that loaded this file ---
  var query = "";
  (function findSelf() {
    var scripts = doc.getElementsByTagName("script");
    for (var i = scripts.length - 1; i >= 0; --i) {
      var s = scripts[i];
      var m = s.src && s.src.match(/^[^#?]*\/run_prettify\.js(\?[^#]*)?(?:#.*)?$/);
      if (m) {
        query = m[1] || "";
        // remove tag for deterministic param handling when loaded multiple times
        if (s.parentNode) s.parentNode.removeChild(s);
        break;
      }
    }
  })();

  // --- Params ---
  var autorun = true;       // ?autorun=true|false        (default true)
  var langs = [];           // ?lang=<name>               (repeatable)
  var skins = [];           // ?skin=<name>               (repeatable)
  var callbacks = [];       // ?callback=<exports.name>   (repeatable)

  query.replace(/[?&]([^&=]+)=([^&]+)/g, function (_, k, v) {
    k = decodeURIComponent(k);
    v = decodeURIComponent(v);
    if (k === "autorun") autorun = !/^[0fn]/i.test(v);
    else if (k === "lang") langs.push(v);
    else if (k === "skin") skins.push(v);
    else if (k === "callback") callbacks.push(v);
  });

  // --- CDN endpoints (RawGit/GoogleCode are dead) ---
  var LOADER_BASE = "https://cdn.jsdelivr.net/gh/google/code-prettify@master/loader";
  function langUrl(name)  { return LOADER_BASE + "/lang-"  + encodeURIComponent(name) + ".js"; }
  function skinUrl(name)  { return LOADER_BASE + "/skins/" + encodeURIComponent(name) + ".css"; }
  var baseCssUrl = LOADER_BASE + "/prettify.css";

  // --- Load language handlers, track pending ---
  var pendingLanguages = langs.length;
  function loadLang(name) {
    var el = doc.createElement("script");
    el.type = "text/javascript";
    el.async = true;
    el.onload = el.onerror = el.onreadystatechange = function () {
      if (el && (!el.readyState || /loaded|complete/.test(el.readyState))) {
        el.onload = el.onerror = el.onreadystatechange = null;
        if (el.parentNode) el.parentNode.removeChild(el);
        el = null;
        pendingLanguages = Math.max(0, pendingLanguages - 1);
        checkReadinessSoon();
      }
    };
    el.src = langUrl(name);
    // insert early to avoid base <base> quirks in old IE
    head.insertBefore(el, head.firstChild);
  }
  for (var i = 0; i < langs.length; i++) loadLang(langs[i]);

  // --- Load skins with simple fallback chain ---
  (function loadSkins(urls) {
    var list = [];
    for (var i = 0; i < skins.length; i++) list.push(skinUrl(skins[i]));
    list.push(baseCssUrl);
    function insertAt(index) {
      if (index >= list.length) return;
      var link = doc.createElement("link");
      link.rel = "stylesheet";
      link.type = "text/css";
      if (index + 1 < list.length) {
        link.onerror = link.error = function () { insertAt(index + 1); };
      }
      link.href = list[index];
      head.appendChild(link);
    }
    insertAt(0);
  })();

  // --- After langs + DOM + PR.prettyPrint are ready, run prettify & callbacks ---
  var readinessTimer = null;
  function checkReadinessSoon() {
    if (readinessTimer != null) return;
    readinessTimer = setTimeout(function () {
      readinessTimer = null;
      checkReadiness();
    }, 25);
  }

  function checkReadiness() {
    // 1) language handlers done
    if (pendingLanguages > 0) return checkReadinessSoon();
    // 2) prettify core present
    if (!(win.PR && typeof win.PR.prettyPrint === "function")) return checkReadinessSoon();

    // 3) DOM ready, then autorun + callbacks
    contentLoaded(function () {
      if (!autorun) return;

      var completion = callbacks.length ? function () {
        var args = arguments;
        for (var i = 0; i < callbacks.length; i++) {
          var name = callbacks[i];
          var fn = win.exports && win.exports[name];
          if (typeof fn === "function") {
            setTimeout((function (f) { return function () { f.apply(win, args); }; })(fn), 0);
          }
        }
      } : undefined;

      try { win.PR.prettyPrint(completion); }
      catch (e) { /* swallow to avoid breaking host pages */ }
    });
  }

  // Kick it off in case there are zero langs (pendingLanguages === 0)
  checkReadinessSoon();

  // --- AMD definition (safe: factory returns window.PR at require-time) ---
  var amdDefine = (typeof win.define === "function" && win.define.amd) ? win.define : null;
  if (amdDefine) {
    amdDefine("google-code-prettify", [], function () {
      return win.PR;
    });
  }
})();
