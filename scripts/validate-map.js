#!/usr/bin/env node
/**
 * validate-map.js - pre-push validation for the regulatory map.
 *
 * Usage:  node scripts/validate-map.js [path-to-index.html]
 * Default path: cui-regulatory-map/index.html (relative to repo root)
 *
 * Exit 0 = safe to push. Exit 1 = do not push.
 *
 * Core checks need no dependencies. The jsdom smoke test runs only if
 * jsdom is installed; otherwise it is skipped with a notice.
 */

const fs = require('fs');
const path = require('path');

const FILE = process.argv[2] || 'cui-regulatory-map/index.html';

let failures = 0;
let warnings = 0;

function ok(msg)   { console.log('  \x1b[32mPASS\x1b[0m  ' + msg); }
function bad(msg)  { console.log('  \x1b[31mFAIL\x1b[0m  ' + msg); failures++; }
function warn(msg) { console.log('  \x1b[33mWARN\x1b[0m  ' + msg); warnings++; }
function info(msg) { console.log('        ' + msg); }

console.log('\nValidating: ' + FILE + '\n');

// ---------------------------------------------------------------- load
if (!fs.existsSync(FILE)) {
  bad('file not found: ' + FILE);
  process.exit(1);
}
const src = fs.readFileSync(FILE, 'utf8');
const lines = src.split('\n');

// ------------------------------------------------------- 1. structure
if (lines[0].trim() === '<!DOCTYPE html>') {
  ok('line 1 is <!DOCTYPE html>');
} else {
  bad('line 1 is not <!DOCTYPE html> - got: ' + JSON.stringify(lines[0].slice(0, 60)));
}

// ----------------------------------------------------- 2. build stamp
const stampRe = /^<!--\s*build:\s*(v[\d.]+)\s*\|\s*([\d-]+)\s*\|\s*(\d+)\s*nodes\s*\/\s*(\d+)\s*edges\s*\|\s*(\d+)\s*load\s*\/\s*(\d+)\s*ref\s*\/\s*(\d+)\s*broken\s*\/\s*(\d+)\s*open\s*-->$/;
const stampMatch = (lines[1] || '').trim().match(stampRe);
let stamp = null;
if (stampMatch) {
  stamp = {
    build: stampMatch[1], date: stampMatch[2],
    nodes: +stampMatch[3], edges: +stampMatch[4],
    load: +stampMatch[5], ref: +stampMatch[6],
    broken: +stampMatch[7], open: +stampMatch[8],
  };
  ok('build stamp present on line 2 (' + stamp.build + ', ' + stamp.date + ')');
} else {
  bad('no parseable build stamp on line 2');
  info('expected: <!-- build: vNN | YYYY-MM-DD | NN nodes / NN edges | NN load / NN ref / NN broken / NN open -->');
}

const metaBuild = src.match(/<meta\s+name="build"\s+content="([^"]+)"/);
if (metaBuild) {
  ok('meta build tag present (' + metaBuild[1] + ')');
  if (stamp && metaBuild[1] !== stamp.build) {
    bad('meta build "' + metaBuild[1] + '" disagrees with comment stamp "' + stamp.build + '"');
  }
} else {
  warn('no <meta name="build"> tag');
}

// -------------------------------------------------- 3. script + parse
let blocks = [];
try {
  const { JSDOM } = require('jsdom');
  const dom = new JSDOM(src);
  blocks = Array.from(dom.window.document.querySelectorAll('script')).map(el => el.textContent || '');
} catch (_) {
  // Fallback keeps core checks dependency-free.
  blocks = [...src.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\b[^>]*>/gi)].map(m => m[1]);
}
if (!blocks.length) {
  bad('no <script> block found');
  process.exit(1);
}
const js = blocks.reduce((a, b) => (a.length > b.length ? a : b));
const dataJs = js.split('const diagram')[0];

let NODES, EDGES, TIERS;
try {
  ({ NODES, EDGES, TIERS } = new Function(dataJs + '; return {NODES,EDGES,TIERS};')());
  ok('script block parses and data model loads');
} catch (err) {
  bad('script block failed to parse: ' + err.message);
  process.exit(1);
}

if (!Array.isArray(NODES) || !Array.isArray(EDGES)) {
  bad('NODES or EDGES is not an array');
  process.exit(1);
}

// ------------------------------------------------------ 4. integrity
const ids = new Set(NODES.map(n => n.id));
const dupCount = NODES.length - ids.size;
if (dupCount === 0) ok('no duplicate node ids');
else {
  const seen = new Set(), dups = [];
  NODES.forEach(n => { if (seen.has(n.id)) dups.push(n.id); seen.add(n.id); });
  bad(dupCount + ' duplicate node id(s): ' + dups.join(', '));
}

const dangling = EDGES.filter(e => !ids.has(e.from) || !ids.has(e.to));
if (!dangling.length) ok('no dangling edge endpoints');
else {
  bad(dangling.length + ' dangling edge(s):');
  dangling.slice(0, 10).forEach(e => info(e.from + ' -> ' + e.to));
}

const badTier = NODES.filter(n => !(n.tier >= 0 && n.tier < TIERS.length));
if (!badTier.length) ok('all nodes have a valid tier index');
else bad(badTier.length + ' node(s) with out-of-range tier: ' + badTier.map(n => n.id).join(', '));

const noteless = EDGES.filter(e => !e.note || !String(e.note).trim());
if (!noteless.length) ok('every edge carries a note');
else warn(noteless.length + ' edge(s) with empty note: ' + noteless.map(e => e.from + '->' + e.to).join(', '));

const blurbless = NODES.filter(n => !n.blurb || !String(n.blurb).trim());
if (!blurbless.length) ok('every node carries a blurb');
else bad(blurbless.length + ' node(s) with empty blurb: ' + blurbless.map(n => n.id).join(', '));

// ------------------------------------------- 5. stamp matches reality
const counts = { load: 0, ref: 0, broken: 0, open: 0 };
EDGES.forEach(e => { counts[e.type] = (counts[e.type] || 0) + 1; });
const actual = {
  nodes: NODES.length, edges: EDGES.length,
  load: counts.load, ref: counts.ref, broken: counts.broken, open: counts.open,
};
info('model: ' + actual.nodes + ' nodes / ' + actual.edges + ' edges | ' +
     actual.load + ' load / ' + actual.ref + ' ref / ' +
     actual.broken + ' broken / ' + actual.open + ' open');

if (stamp) {
  const mismatched = ['nodes', 'edges', 'load', 'ref', 'broken', 'open']
    .filter(k => stamp[k] !== actual[k]);
  if (!mismatched.length) {
    ok('build stamp matches the parsed model');
  } else {
    bad('build stamp is stale - mismatched: ' + mismatched.join(', '));
    mismatched.forEach(k => info(k + ': stamp says ' + stamp[k] + ', model has ' + actual[k]));
    info('fix: update the line-2 comment and the build-counts meta tag');
  }
}

const metaCounts = src.match(/<meta\s+name="build-counts"\s+content="([^"]+)"/);
if (metaCounts) {
  const expect = 'nodes=' + actual.nodes + ' edges=' + actual.edges +
                 ' load=' + actual.load + ' ref=' + actual.ref +
                 ' broken=' + actual.broken + ' open=' + actual.open;
  if (metaCounts[1] === expect) ok('build-counts meta matches the parsed model');
  else {
    bad('build-counts meta is stale');
    info('meta:  ' + metaCounts[1]);
    info('model: ' + expect);
  }
}

// ------------------------------------------------- 6. regression guard
const MIN_NODES = 39, MIN_EDGES = 76;
if (actual.nodes >= MIN_NODES && actual.edges >= MIN_EDGES) {
  ok('no regression below known-good floor (' + MIN_NODES + '/' + MIN_EDGES + ')');
} else {
  bad('REGRESSION: model is smaller than the known-good floor of ' +
      MIN_NODES + ' nodes / ' + MIN_EDGES + ' edges');
  info('this is the signature of pushing a stale build - verify before overriding');
  info('if the shrink is intentional, raise the floor in scripts/validate-map.js');
}

// ------------------------------------------------- 7. jsdom smoke test
let jsdom = null;
try { jsdom = require('jsdom'); } catch (_) {}

if (!jsdom) {
  warn('jsdom not installed - smoke test skipped (npm i -D jsdom to enable)');
  finish();
} else {
  const { JSDOM } = jsdom;
  const dom = new JSDOM(src, { runScripts: 'dangerously', pretendToBeVisual: true });
  setTimeout(() => {
    try {
      const d = dom.window.document;
      const rendered = d.querySelectorAll('.node').length;
      if (rendered === NODES.length) ok('smoke: all ' + rendered + ' nodes render');
      else bad('smoke: rendered ' + rendered + ' nodes, model has ' + NODES.length);

      const first = d.getElementById('n-' + NODES[0].id);
      first.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
      const drawer = d.getElementById('drawer');
      if (drawer.classList.contains('open')) ok('smoke: selection opens the drawer');
      else bad('smoke: drawer did not open on node click');

      const blurbEl = d.querySelector('.drawer .blurb');
      if (blurbEl && blurbEl.textContent.trim().length > 20) ok('smoke: drawer renders blurb text');
      else bad('smoke: drawer blurb is empty or missing');

      // catches the CodeQL innerHTML -> textContent autofix
      if (!blurbEl) {
        info('literal-markup check skipped (no blurb element to inspect)');
      } else if (/<(div|span|button)\b/i.test(blurbEl.textContent)) {
        bad('smoke: drawer is showing literal HTML markup as text');
        info('likely cause: innerHTML replaced with textContent (CodeQL autofix)');
      } else {
        ok('smoke: no literal markup leaking into rendered text');
      }

      const closeBtn = d.querySelector('.closebtn');
      if (!closeBtn) {
        bad('smoke: no close button rendered in drawer');
        info('likely cause: drawer body was not built as HTML (CodeQL autofix)');
      } else {
        closeBtn.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
        if (!drawer.classList.contains('open')) ok('smoke: drawer closes');
        else bad('smoke: drawer did not close');
      }
    } catch (err) {
      bad('smoke test threw: ' + err.message);
    }
    finish();
  }, 900);
}

function finish() {
  console.log('');
  if (failures) {
    console.log('\x1b[31m' + failures + ' failure(s)' +
      (warnings ? ', ' + warnings + ' warning(s)' : '') + ' - DO NOT PUSH\x1b[0m\n');
    process.exit(1);
  }
  console.log('\x1b[32mAll checks passed' +
    (warnings ? ' (' + warnings + ' warning(s))' : '') + ' - safe to push\x1b[0m\n');
  process.exit(0);
}
