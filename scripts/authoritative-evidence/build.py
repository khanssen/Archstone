"""Build /authoritative-evidence/index.html from the dataset CSV.

Aggregate counts only: no objective IDs, rationale or mechanisms reach the page.
Usage: python3 scripts/authoritative-evidence/build.py rfi-figure-dataset-v8_9.csv 8.9
"""
import csv, re, sys, html
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
src, ver = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(ROOT / src, encoding='utf-8')))
assert len(rows) == 320, len(rows)

FAM = {'01':'Access Control','02':'Awareness & Training','03':'Audit & Accountability','04':'Configuration Management',
       '05':'Identification & Authentication','06':'Incident Response','07':'Maintenance','08':'Media Protection',
       '09':'Personnel Security','10':'Physical Protection','11':'Risk Assessment','12':'Security Assessment',
       '13':'System & Communications Protection','14':'System & Information Integrity'}
CALLS = ['yes','partial','no']
fam = defaultdict(Counter)
for r in rows:
    fam[re.match(r'03\.(\d\d)\.', r['objective_id']).group(1)][r['machine_reportable']] += 1
tot = Counter(r['machine_reportable'] for r in rows)
ref = Counter(r['referent_class'] for r in rows if r['machine_reportable'] == 'yes')
dept = sum(v for k, v in ref.items() if k.startswith('NCP') or k.startswith('DoD'))
org = ref['Organization-defined ODP']
assert dept + org == tot['yes'], ref

# Previous published totals, for the slope chart. Add a version here when one is published.
HISTORY = [('v7', {'yes':140,'partial':101,'no':79}), ('v' + ver, dict(tot))]

e = html.escape
def pct(n, d): return round(100 * n / d)

# --- Figure 1: by family -------------------------------------------------
fams = sorted(fam, key=lambda k: (-fam[k]['yes'] / sum(fam[k].values()), k))
f1 = []
for k in fams:
    c = fam[k]; n = sum(c.values())
    cells = ''.join(f'<i class="ae-c ae-{x}"></i>' * c[x] for x in CALLS)
    f1.append(f'''<div class="ae-fam" role="listitem" aria-label="{e(FAM[k])}: {c['yes']} of {n} fully reportable, {c['partial']} partial, {c['no']} not reportable">
      <span class="ae-fn">{e(FAM[k])}</span>
      <span class="ae-cells" aria-hidden="true">{cells}</span>
      <span class="ae-fr"><b>{c['yes']}</b> of {n}</span>
    </div>''')

# --- Figure 2: one bar of 320 -------------------------------------------
segs = [('dept', dept, 'Department-published referent'), ('org', org, 'Organization-defined value'),
        ('partial', tot['partial'], 'Partially reportable'), ('no', tot['no'], 'Not reportable')]
bar = ''.join(f'<span class="ae-seg ae-s-{k}" style="flex:{n}"><b>{n}</b></span>' for k, n, _ in segs)
leg = ''.join(f'<li><i class="ae-sw ae-s-{k}"></i>{e(l)} <b>{n}</b></li>' for k, n, l in segs)

# --- Figure 3: slope chart ----------------------------------------------
W, H, PADL, PADR, PADT, PADB = 600, 230, 60, 250, 20, 34
ymin, ymax = 60, 160
x0, x1 = PADL, W - PADR
y = lambda v: PADT + (H - PADT - PADB) * (1 - (v - ymin) / (ymax - ymin))
LAB = {'yes':'Fully reportable','partial':'Partially reportable','no':'Not reportable'}
(a_lab, a), (b_lab, b) = HISTORY[0], HISTORY[-1]
svg = [f'<svg class="ae-slope" viewBox="0 0 {W} {H}" role="img" aria-label="Totals by call, {a_lab} to {b_lab}: ' +
       '; '.join(f'{LAB[c].lower()} {a[c]} to {b[c]}' for c in CALLS) + '">']
for gx, gl in ((x0, a_lab), (x1, b_lab)):
    svg.append(f'<line x1="{gx}" x2="{gx}" y1="{PADT-8}" y2="{H-PADB+4}" class="ae-ax"/><text x="{gx}" y="{H-8}" class="ae-axl" text-anchor="middle">{gl}</text>')
for c in CALLS:
    ya, yb = y(a[c]), y(b[c]); d = b[c] - a[c]
    svg.append(f'<line x1="{x0}" y1="{ya:.1f}" x2="{x1}" y2="{yb:.1f}" class="ae-ln ae-l-{c}"/>'
               f'<circle cx="{x0}" cy="{ya:.1f}" r="4.5" class="ae-dot ae-l-{c}"/><circle cx="{x1}" cy="{yb:.1f}" r="4.5" class="ae-dot ae-l-{c}"/>'
               f'<text x="{x0-12}" y="{ya+4:.1f}" text-anchor="end" class="ae-v">{a[c]}</text>'
               f'<text x="{x1+12}" y="{yb+4:.1f}" class="ae-v">{b[c]}</text>'
               f'<text x="{x1+48}" y="{yb+4:.1f}" class="ae-d">{d:+d}</text>'
               f'<text x="{x1+92}" y="{yb+4:.1f}" class="ae-sl">{LAB[c]}</text>')
svg.append('</svg>')

CSS = '''
.ae-def { margin: 28px 0 0; padding: 18px 22px; border-left: 3px solid var(--x-referent); background: var(--x-referent-fill); border-radius: 0 8px 8px 0; font-size: 15px; color: var(--x-ink-soft); max-width: 78ch; }
.ae-def b { color: var(--x-ink); }
.ae-fig { margin: 56px 0 0; }
.ae-fig > h2 { font-size: 24px; margin: 0 0 8px; max-width: 30ch; }
.ae-fig > p { font-size: 15px; color: var(--x-ink-soft); margin: 0 0 22px; }
.ae-cap { font-size: 13px !important; color: var(--x-ink-soft); margin: 14px 0 0 !important; font-family: var(--x-mono); }
.ae-key { display: flex; flex-wrap: wrap; gap: 6px 20px; list-style: none; padding: 0; margin: 0 0 18px; font-size: 13px; color: var(--x-ink-soft); }
.ae-key li { display: flex; align-items: center; gap: 7px; }
.ae-key b { color: var(--x-ink); font-weight: 600; }
.ae-fams { display: grid; gap: 10px; }
.ae-fam { display: grid; grid-template-columns: minmax(150px, 250px) 1fr 70px; gap: 14px; align-items: center; }
.ae-fn { font-size: 14px; }
.ae-fr { font-family: var(--x-mono); font-size: 12px; color: var(--x-ink-soft); text-align: right; white-space: nowrap; }
.ae-fr b { color: var(--x-ink); font-weight: 500; }
.ae-cells { display: flex; flex-wrap: wrap; gap: 3px; max-width: calc(36 * 15px); }
.ae-c, .ae-sw { display: inline-block; width: 12px; height: 12px; border-radius: 2px; }
.ae-yes, .ae-s-dept { background: var(--x-referent); }
.ae-s-org { background: #6E93AA; }
.ae-partial, .ae-s-partial { background: #B7CBD7; }
.ae-no, .ae-s-no { background: #fff; box-shadow: inset 0 0 0 1px #AEB9B4; }
.ae-bar { display: flex; height: 54px; border-radius: 6px; overflow: hidden; gap: 2px; }
.ae-seg { display: flex; align-items: center; padding: 0 10px; font-family: var(--x-mono); font-size: 13px; min-width: 0; }
.ae-seg b { font-weight: 500; }
.ae-s-dept b, .ae-s-org b { color: #fff; }
.ae-bar-ax { display: flex; justify-content: space-between; font-family: var(--x-mono); font-size: 11px; color: var(--x-ink-soft); margin: 6px 0 0; }
.ae-brace { display: grid; grid-template-columns: 143fr 177fr; gap: 2px; margin: 0 0 6px; font-size: 13px; color: var(--x-ink-soft); }
.ae-brace span { border-bottom: 1.5px solid var(--x-ink-soft); padding: 0 0 4px; }
.ae-brace span + span { border-color: var(--x-rule); }
.ae-slope { width: 100%; max-width: 640px; height: auto; display: block; font-family: var(--x-mono); }
.ae-ax { stroke: var(--x-rule); }
.ae-axl { font-size: 12px; fill: var(--x-ink-soft); }
.ae-ln { stroke-width: 2.5; fill: none; }
.ae-l-yes { stroke: var(--x-referent); fill: var(--x-referent); }
.ae-l-partial { stroke: #8FAABB; fill: #8FAABB; }
.ae-l-no { stroke: #8C9893; fill: #8C9893; }
.ae-v { font-size: 14px; fill: var(--x-ink); }
.ae-d { fill: var(--x-ink-soft); font-size: 13px; }
.ae-sl { font-family: var(--x-sans); font-size: 14px; fill: var(--x-ink-soft); }
@media (max-width: 640px) {
  .ae-fam { grid-template-columns: 1fr auto; }
  .ae-cells { grid-column: 1 / -1; grid-row: 2; }
  .ae-seg b { display: none; }
}
'''

body = f'''
  <section class="x20-hero" aria-labelledby="ae-h1">
  <p class="x20-eyebrow">Archstone Security · Research · NIST SP 800-171A Rev 2</p>
  <h1 id="ae-h1">Is the system an authoritative evidence source?</h1>
  <p class="x20-lede">We put the question to each of the {len(rows)} assessment objectives in NIST SP 800-171A Rev 2. For <b>{tot['yes']}</b>, the system's own state answers it. For <b>{tot['partial']}</b>, the evidence exists but is conditional, a proxy, or waits on a value nobody has published. For <b>{tot['no']}</b>, nothing the system emits answers the objective.</p>
  <div class="rs-meta">
    <span><b>Standard</b> NIST SP 800-171A Rev 2 · {len(rows)} objectives</span>
    <span><b>Dataset</b> v{e(ver)}</span>
    <span><b>Scope</b> one reference environment, n=1</span>
  </div>
  <p class="ae-def"><b>Authoritative evidence source</b>, as used here: the system's own emitted state, read by a machine and compared against a referent, with no human attestation in between. A <b>referent</b> is the value the state is compared against, either one the Department has published or one the standard obliges the organization to set.</p>
  </section>

  <section class="ae-fig" aria-labelledby="ae-f1">
  <h2 id="ae-f1">Family by family</h2>
  <p>One square per assessment objective. Families are ordered by the share the system answers in full.</p>
  <ul class="ae-key"><li><i class="ae-sw ae-yes"></i>Fully reportable</li><li><i class="ae-sw ae-partial"></i>Partially reportable</li><li><i class="ae-sw ae-no"></i>Not reportable</li></ul>
  <div class="ae-fams" role="list">
    {"".join(f1)}
  </div>
  <p class="ae-cap">Figure 1 · {len(rows)} objectives, {len(fams)} families · dataset v{e(ver)}</p>
  </section>

  <section class="ae-fig" aria-labelledby="ae-f2">
  <h2 id="ae-f2">The limit is the referent, not the telemetry</h2>
  <p>Of the {tot['yes']} objectives the system answers in full, {dept} are compared against a value the Department has published. The other {org} depend on a value the organization is required to set, so the answer is only as authoritative as that value.</p>
  <div class="ae-brace" aria-hidden="true"><span>Fully reportable · {tot['yes']}</span><span>Partial or not reportable · {tot['partial'] + tot['no']}</span></div>
  <div class="ae-bar" role="img" aria-label="{'; '.join(f'{l}: {n}' for _, n, l in segs)}">{bar}</div>
  <div class="ae-bar-ax" aria-hidden="true"><span>0</span><span>{len(rows)}</span></div>
  <ul class="ae-key" style="margin-top:14px">{leg}</ul>
  <p class="ae-cap">Figure 2 · Department-published referents: NIST Checklist Repository content and DoD organization-defined parameter values</p>
  </section>

  <section class="ae-fig" aria-labelledby="ae-f3">
  <h2 id="ae-f3">The calls have tightened</h2>
  <p>Each revision re-tested the classification against itself. Net movement between published versions:</p>
  {"".join(svg)}
  <p class="ae-cap">Figure 3 · Totals by call at each published dataset version · net change beside each total</p>
  </section>

  <section class="rs-notes" aria-label="Notes">
  <p><b>What these figures are.</b> Counts from one reference environment. They show that a substantial share of the standard can be answered from the system's own state using components the standard already requires. They are not a population estimate, and a different architecture would move objectives between categories.</p>
  <p><b>What is not on this page.</b> Counts only. Which objectives fall where, and how each is collected, are not shown here.</p>
  </section>

  <div class="rs-colophon">
    <span>Archstone Security</span>
    <span>Dataset v{e(ver)}</span>
    <span><a href="mailto:contact@archstonesecurity.com?subject=Research%20%E2%80%94%20authoritative%20evidence">Corrections and disagreements welcome</a></span>
  </div>
'''

shell = (ROOT / 'research.html').read_text(encoding='utf-8')
start = shell.index('  <section class="x20-hero"')
end = shell.index('                </div>\n            </div>\n        </div>\n    </main>')
out = shell[:start] + body.strip('\n') + '\n' + shell[end:]
title = 'Is the system an authoritative evidence source? | Archstone Security'
desc = f'Aggregate results for the {len(rows)} assessment objectives in NIST SP 800-171A Rev 2: how many the system itself can answer, and what limits the rest.'
url = 'https://archstonesecurity.com/authoritative-evidence/'
for a, b_ in [('<title>Research | Archstone Security</title>', f'<title>{e(title)}</title>'),
              ('content="Research | Archstone Security"', f'content="{e(title)}"'),
              ('https://archstonesecurity.com/research.html', url)]:
    assert a in out, a; out = out.replace(a, b_)
out = re.sub(r'(<meta (?:name|property)="(?:og:)?description" content=")[^"]*"', lambda m: m.group(1) + e(desc) + '"', out)
out = out.replace('</head>', f'<style>{CSS}</style>\n</head>', 1)
dst = ROOT / 'authoritative-evidence' / 'index.html'
dst.parent.mkdir(exist_ok=True)
dst.write_text(out, encoding='utf-8')
print('wrote', dst, dict(tot), 'dept', dept, 'org', org)
