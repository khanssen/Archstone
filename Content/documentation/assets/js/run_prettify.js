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
      if (el && (!el.readySta
