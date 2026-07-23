#!/usr/bin/env python3
"""
Public Lands Institute — Phase 2 data cleanup (July 2026 audit).
Run from the repo root:
    python3 tools/cleanup_sites.py

Idempotent. Applies, in order:

  1. data/photos.json — add a commons_n integer to every Commons-linked entry,
     recording which Commons number the entry actually links to. Commons URLs
     themselves are never touched; they are correct as uploaded.
  2. sites.json — remove space-before-semicolon, collapse runs of spaces,
     add a numeric acreage_n parsed from the display string (which is left
     untouched), regenerate gps from lat/lng so the two can never drift, and
     fill empty shadow_history fields with SHADOW_HISTORY_NONE.
  3. sites_meta.json + data/nations.geojson — unify nation orthography with
     glossary.html as canonical; feature colors are recomputed with the same
     deterministic md5-palette scheme the generator uses.

Prints the acreage_n total for reconciliation against PLI-Project-Metrics.txt.
"""

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# Project convention for sites where research found nothing to report.
# validate_pli.py accepts exactly this string (or real narrative text) and
# flags empty fields and near-miss variants.
SHADOW_HISTORY_NONE = ('No significant or independently documentable shadow '
                       'history has been identified for this site.')

# glossary.html is canonical for nation orthography.
NATION_RENAMES = {
    'Crow (Apsaalooke)': 'Apsáalooke (Crow)',
    "Wichita (Kitikiti'sh)": 'Wichita (Kitikiti’sh)',
    'Ute (Núu-agha-tʉvʉ-pʉ̱)': 'Ute (Núuchi-u / Núu-agha-tʉvʉ-pʉ̱)',
}

# Acreage strings holding two component figures that should be summed.
ACREAGE_SUM_SLUGS = {'john-bryan-state-park', 'hocking-hills'}

COMMONS_NUM_RE = re.compile(r'-_(\d+)\.\w+$')


def nation_color(name):
    palette = [
        '#e8a838', '#5b9e6e', '#5b8abf', '#bf5b7a', '#7a5bbf', '#c87840', '#5bbfbf',
        '#bf5b5b', '#8cbf5b', '#4a6ebf', '#bf9e5b', '#5bbf8c', '#bf5b9e', '#5b9ebf',
        '#9ebf5b', '#bf6e5b', '#8a5bbf', '#bfbf5b', '#e87c5b', '#5be8a8', '#c45be8',
        '#e8c45b', '#5bc4e8', '#e85b8a', '#a8e85b', '#c8a050', '#6abf9e', '#9e6abf',
    ]
    return palette[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(palette)]


def clean_spaces(value, counters):
    if ' ;' in value:
        counters['semi'] += 1
        value = re.sub(r' +;', ';', value)
    if '  ' in value:
        counters['double'] += 1
        value = re.sub(r'  +', ' ', value)
    return value


def parse_acreage(slug, text):
    nums = [int(n.replace(',', '')) for n in re.findall(r'[\d,]*\d', text)]
    if not nums:
        raise ValueError(f'{slug}: no number in acreage {text!r}')
    if slug in ACREAGE_SUM_SLUGS:
        return sum(nums)
    return nums[0]


def main():
    # ── 1. photos.json: commons_n ─────────────────────────────────────────────
    with open('data/photos.json') as f:
        photos = json.load(f)
    added = 0
    for slug, entries in photos.items():
        for e in entries:
            if e.get('c') and 'commons_n' not in e:
                m = COMMONS_NUM_RE.search(e['c'])
                if not m:
                    print(f'  WARNING: unparseable Commons URL for {slug}: {e["c"]}',
                          file=sys.stderr)
                    continue
                e['commons_n'] = int(m.group(1))
                added += 1
    with open('data/photos.json', 'w') as f:
        json.dump(photos, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'photos.json: commons_n added to {added} entries')

    # ── 2. sites.json ─────────────────────────────────────────────────────────
    with open('sites.json') as f:
        sites = json.load(f)
    counters = {'semi': 0, 'double': 0}
    gps_changed = 0
    shadow_filled = []
    for s in sites:
        for k, v in list(s.items()):
            if isinstance(v, str):
                s[k] = clean_spaces(v, counters)
            elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                cleaned = [clean_spaces(x, {'semi': 0, 'double': 0}) for x in v]
                if cleaned != v:
                    # Count the field once, matching the audit's field counts
                    if any(' ;' in x for x in v):
                        counters['semi'] += 1
                    if any('  ' in x for x in v):
                        counters['double'] += 1
                    s[k] = cleaned
        s['acreage_n'] = parse_acreage(s['slug'], s['acreage'])
        gps = f"{s['lat']:.4f}° N, {abs(s['lng']):.4f}° W"
        if s['gps'] != gps:
            gps_changed += 1
            s['gps'] = gps
        if not s.get('shadow_history', '').strip():
            s['shadow_history'] = SHADOW_HISTORY_NONE
            shadow_filled.append(s['slug'])
    with open('sites.json', 'w') as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)
        f.write('\n')
    total_acreage = sum(s['acreage_n'] for s in sites)
    print(f'sites.json: {counters["semi"]} space-before-semicolon fields, '
          f'{counters["double"]} double-space fields cleaned; '
          f'acreage_n added to {len(sites)} records; '
          f'{gps_changed} gps strings regenerated; '
          f'shadow_history filled for {", ".join(shadow_filled) or "none"}')
    print(f'acreage_n total: {total_acreage:,}')

    # ── 3. nation orthography ─────────────────────────────────────────────────
    with open('sites_meta.json') as f:
        meta = json.load(f)
    renamed = 0
    for slug, m in meta.items():
        territory = m.get('territory', [])
        for i, n in enumerate(territory):
            if n in NATION_RENAMES:
                territory[i] = NATION_RENAMES[n]
                renamed += 1
    with open('sites_meta.json', 'w') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write('\n')
    with open('data/nations.geojson') as f:
        nations = json.load(f)
    renamed_gj = 0
    for feat in nations['features']:
        p = feat['properties']
        if p['nation'] in NATION_RENAMES:
            p['nation'] = NATION_RENAMES[p['nation']]
            p['color'] = nation_color(p['nation'])
            renamed_gj += 1
    with open('data/nations.geojson', 'w') as f:
        json.dump(nations, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'nation orthography: {renamed} territory values in sites_meta.json, '
          f'{renamed_gj} features in data/nations.geojson')


if __name__ == '__main__':
    main()
