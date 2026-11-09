#!/usr/bin/env python3
"""
Public Lands Institute — dry run of the Native Land nation filter.
Run from the repo root:
    python3 tools/nations_dry_run.py [out.md]

Compares the map's nation tags under the old rule (union of `nations` and
`nations_nld`) with the filter in build.py (site_nations), and writes a
markdown report: per-nation counts, every dropped tag, nations that fall to
zero, sites left with no nation, and the record text that keeps each Native
Land tag. Writes nothing else.
"""

import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402  (build.py chdirs to ROOT on import)


def main(out):
    sites = json.load(open('sites.json'))
    meta = json.load(open('sites_meta.json'))
    old, new = defaultdict(set), defaultdict(set)
    dropped_rows, kept_text, no_nation = [], [], []
    for s in sites:
        slug, m = s['slug'], meta.get(s['slug'], {})
        for n in m.get('nations', []) + m.get('nations_nld', []):
            old[build.NATION_CANON.get(n, n)].add(slug)
        kept, dropped = build.site_nations(s, m)
        for cn, src in kept:
            new[cn].add(slug)
            if src == 'text':
                text = ' '.join([s.get('native_lands', ''), s.get('displacement_tenure', '')])
                mt = build.nation_rx(cn).search(text)
                snip = text[max(0, mt.start() - 40):mt.end() + 40].replace('|', '/').strip()
                kept_text.append((cn, slug, snip))
        for cn in dropped:
            dropped_rows.append((cn, slug))
        if not kept:
            no_nation.append((slug, m.get('cultures', [])))

    names = sorted(old, key=lambda n: (-len(old[n]), n))
    zero = [n for n in names if old[n] and not new[n]]
    L = ['# Native Land nation filter: dry run', '',
         f'{len(sites)} sites. Old rule: union of record nations and every Native Land '
         'polygon containing the site. New rule: a Native Land nation is kept only where the '
         'site\'s native_lands or displacement_tenure text names it (name or common alternate); '
         'record nations are always kept. The Royce cession test is not applied because the '
         'pipeline has no Royce cession geometry. Cultures are unchanged and not listed.', '',
         f'Tags before: {sum(len(v) for v in old.values())}. After: {sum(len(v) for v in new.values())}. '
         f'Dropped: {len(dropped_rows)}.', '',
         '## Counts per nation', '', '| Nation | Current | New | Change |', '|---|---:|---:|---:|']
    for n in names:
        L.append(f'| {n} | {len(old[n])} | {len(new[n])} | {len(new[n]) - len(old[n])} |')
    L += ['', '## Nations that drop to zero', '']
    if zero:
        for n in zero:
            L.append(f'### {n} ({len(old[n])} to 0)')
            L += [f'- {s}' for s in sorted(old[n])]
            L.append('')
    else:
        L += ['None.', '']
    L += ['## Sites left with no nations', '']
    L += [f'- {s} (cultures: {", ".join(c) or "none"})' for s, c in no_nation] or ['None.']
    L += ['', '## Dropped tags by nation', '']
    by_n = defaultdict(list)
    for cn, slug in dropped_rows:
        by_n[cn].append(slug)
    for n in sorted(by_n, key=lambda n: (-len(by_n[n]), n)):
        L.append(f'### {n} ({len(by_n[n])})')
        L += [f'- {s}' for s in sorted(by_n[n])]
        L.append('')
    L += ['## Native Land tags kept because the record text names them', '',
          'Check these for false matches (a place name read as a nation).', '',
          '| Nation | Site | Matching text |', '|---|---|---|']
    for cn, slug, snip in sorted(kept_text):
        L.append(f'| {cn} | {slug} | ...{snip}... |')
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    open(out, 'w').write('\n'.join(L) + '\n')
    print(f'{out}: {len(dropped_rows)} dropped tags, {len(zero)} nations to zero, '
          f'{len(no_nation)} sites with no nation')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '_review_sheets/nations-filter-dry-run.md')
