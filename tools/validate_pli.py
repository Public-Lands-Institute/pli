#!/usr/bin/env python3
"""
Public Lands Institute — data and page validator.
Run from the repo root (build.py runs it automatically):
    python3 tools/validate_pli.py

Checks:
  1. Duplicate frames — the same camera filename must not appear under more
     than one site slug in data/photos.json.
  2. Commons numbering — the caption number of each Commons-linked entry must
     agree with the number in the linked Commons filename.
  3. Pending Commons uploads — entries with no 'c' value (WARN, informational).
  4. Generated-page consistency — the about.html stats sentence and the
     photographs.html intro counts must match the data; sitemap.xml must cover
     exactly the site's pages with lastmod equal to each file's mtime date.
  5. Referenced files — every thumb / large / jpg / raw / xmp path referenced
     by data/photos.json must exist on disk.
  6. Shadow history — every site must carry either real narrative text or
     exactly the project's SHADOW_HISTORY_NONE convention text; empty fields
     and near-miss variants of the standard text FAIL.

Exit status: nonzero if any check FAILs. WARNs do not affect exit status.
"""

import difflib
import json
import os
import re
import sys
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from cleanup_sites import SHADOW_HISTORY_NONE  # single source of the convention text

# Commons numbers that are legitimately unlinked and must NOT be flagged as
# numbering drift: the source frame was intentionally removed from the index, so
# the Commons file (kept on Commons under CC0) has no site entry by design. Each
# accepted orphan also shifts every later entry's expected number by one, so the
# post-gap entries stop reading as "out of position". (slug, commons_number).
# Distinct from unresolved drift like Clifty Falls 001 / Prophetstown 005, which
# stay flagged until the files are realigned on Commons.
ACCEPTED_ORPHANS = {
    ('pointe-mouillee-state-game-area', 4),  # _DSF1814 pulled from the index 2026-07
}


def expected_commons_n(slug, i):
    """The commons_n the entry at 0-based position i should carry, counting past
    any accepted-orphan numbers that were intentionally skipped for this site."""
    n, seen = 0, -1
    while seen < i:
        n += 1
        if (slug, n) not in ACCEPTED_ORPHANS:
            seen += 1
    return n


failures = 0


def report(check, status, detail=''):
    global failures
    if status == 'FAIL':
        failures += 1
    print(f'check {check}: {status}' + (f' — {detail}' if detail else ''))


def camera_filename(entry):
    if entry.get('thumb'):
        return os.path.basename(entry['thumb'])
    if entry.get('large'):
        return os.path.basename(entry['large'])[3:]
    f = entry.get('f', '')
    if f.lower().endswith(('.jpg', '.jpeg')):
        return f
    if entry.get('r'):
        return os.path.splitext(os.path.basename(entry['r']))[0] + '.jpg'
    return ''


def main():
    with open('sites.json') as f:
        sites = json.load(f)
    with open('data/photos.json') as f:
        photos = json.load(f)

    # ── Check 1: duplicate frames across sites ────────────────────────────────
    frame_sites = {}
    for slug, entries in photos.items():
        for e in entries:
            frame_sites.setdefault(camera_filename(e), set()).add(slug)
    dupes = {cam: slugs for cam, slugs in frame_sites.items() if len(slugs) > 1}
    if dupes:
        lines = [f'{cam}: {", ".join(sorted(s))}' for cam, s in sorted(dupes.items())]
        report(1, 'FAIL', f'{len(dupes)} frames appear under multiple sites\n    '
               + '\n    '.join(lines))
    else:
        report(1, 'PASS', 'no frame appears under more than one site')

    # ── Check 2: Commons numbering ────────────────────────────────────────────
    commons_num_re = re.compile(r'-_(\d+)\.\w+$')
    mismatches = []
    bad_links = []
    for slug, entries in photos.items():
        for i, e in enumerate(entries):
            if not e.get('c'):
                continue
            m = commons_num_re.search(e['c'])
            if not m:
                bad_links.append(f'{slug} {i + 1}: unparseable Commons URL {e["c"]}')
                continue
            linked_n = int(m.group(1))
            if 'commons_n' in e:
                # Link integrity: the recorded commons_n must match the URL.
                if e['commons_n'] != linked_n:
                    bad_links.append(
                        f'{slug} {i + 1}: commons_n={e["commons_n"]} but URL is {linked_n:03d}')
                if linked_n != expected_commons_n(slug, i):
                    mismatches.append(f'{slug} {i + 1} -> Commons {linked_n:03d}')
            else:
                if linked_n != expected_commons_n(slug, i):
                    mismatches.append(f'{slug} {i + 1} -> Commons {linked_n:03d}')
    has_commons_n = any('commons_n' in e for entries in photos.values() for e in entries)
    if bad_links:
        report(2, 'FAIL', f'{len(bad_links)} broken Commons links\n    ' + '\n    '.join(bad_links))
    elif has_commons_n:
        detail = 'all Commons links agree with commons_n'
        if mismatches:
            # Orphaned Commons numbers: numbers below a site's highest claimed
            # Commons number that no entry links to — files left unclaimed by
            # the numbering shift.
            by_site = {}
            for slug, entries in photos.items():
                claimed = {e['commons_n'] for e in entries if e.get('commons_n')}
                if not claimed:
                    continue
                accepted = {n for (s, n) in ACCEPTED_ORPHANS if s == slug}
                unclaimed = set(range(1, max(claimed) + 1)) - claimed - accepted
                if unclaimed:
                    by_site[slug] = unclaimed
            orphans = [f'{slug} {n:03d}' for slug, ns in sorted(by_site.items())
                       for n in sorted(ns)]
            print(f'check 2: WARN — {len(mismatches)} entries numbered out of position '
                  f'(Commons files orphaned by the shift: {", ".join(orphans) or "none"})')
            for m_ in mismatches:
                print(f'    {m_}')
        report(2, 'PASS', detail)
    elif mismatches:
        report(2, 'FAIL', f'{len(mismatches)} caption/Commons number mismatches\n    '
               + '\n    '.join(mismatches))
    else:
        report(2, 'PASS', 'caption numbers agree with Commons filenames')

    # ── Check 3: pending Commons uploads ──────────────────────────────────────
    pending = [f'{slug} {i + 1} ({camera_filename(e)})'
               for slug, entries in photos.items()
               for i, e in enumerate(entries) if not e.get('c')]
    if pending:
        report(3, 'WARN', f'{len(pending)} entries pending Commons upload\n    '
               + '\n    '.join(pending))
    else:
        report(3, 'PASS', 'every entry has a Commons link')

    # ── Check 4: generated-page consistency ───────────────────────────────────
    problems = []
    n_frames = sum(len(entries) for entries in photos.values())
    n_sites = len(sites)
    n_states = len({s['state'] for s in sites})
    about = open('about.html').read()
    m = re.search(r'The index currently holds (\d[\d,]*) sites across (\d[\d,]*) states, '
                  r'documented in (\d[\d,]*) photographs', about)
    if not m:
        problems.append('about.html: stats sentence not found')
    else:
        got = tuple(int(g.replace(',', '')) for g in m.groups())
        if got != (n_sites, n_states, n_frames):
            problems.append(f'about.html: stats say {got}, data says '
                            f'({n_sites}, {n_states}, {n_frames})')
    gallery = open('photographs.html').read()
    m = re.search(r'(\d[\d,]*) images across (\d[\d,]*) sites\.', gallery)
    n_gallery = sum(1 for slug, entries in photos.items()
                    for e in entries if e.get('thumb') and os.path.exists(e['thumb']))
    if not m:
        problems.append('photographs.html: intro sentence not found')
    else:
        got = tuple(int(g.replace(',', '')) for g in m.groups())
        if got != (n_gallery, len(photos)):
            problems.append(f'photographs.html: intro says {got}, data says '
                            f'({n_gallery}, {len(photos)})')
    sitemap = open('sitemap.xml').read()
    locs = re.findall(r'<loc>([^<]+)</loc>', sitemap)
    lastmods = re.findall(r'<lastmod>([^<]+)</lastmod>', sitemap)
    base = 'https://publiclandsinstitute.net'
    expected = [f'{base}/', f'{base}/photographs.html', f'{base}/archive.html',
                f'{base}/about.html', f'{base}/glossary.html']
    expected += [f'{base}/sites/{s["slug"]}.html' for s in sites]
    if sorted(locs) != sorted(expected):
        missing = set(expected) - set(locs)
        extra = set(locs) - set(expected)
        problems.append(f'sitemap.xml: coverage mismatch '
                        f'(missing {sorted(missing)}, extra {sorted(extra)})')
    else:
        for loc, lastmod in zip(locs, lastmods):
            path = loc[len(base):].lstrip('/') or 'index.html'
            if os.path.exists(path):
                mtime = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
                if lastmod != mtime:
                    problems.append(f'sitemap.xml: {path} lastmod {lastmod} != mtime {mtime}')
    if problems:
        report(4, 'FAIL', '\n    '.join(problems))
    else:
        report(4, 'PASS', 'about/photographs stats and sitemap agree with data')

    # ── Check 5: referenced files exist ───────────────────────────────────────
    missing = []
    for slug, entries in photos.items():
        for i, e in enumerate(entries):
            cam = camera_filename(e)
            for label, path in (('thumb', e.get('thumb')), ('large', e.get('large')),
                                ('jpg', f'img/jpg/{slug}/{cam}'),
                                ('raw', e.get('r')), ('xmp', e.get('x'))):
                if path and not os.path.exists(path):
                    missing.append(f'{slug} {i + 1}: {label} {path}')
    if missing:
        report(5, 'FAIL', f'{len(missing)} referenced files missing\n    '
               + '\n    '.join(missing))
    else:
        report(5, 'PASS', 'all referenced thumb/large/jpg/raw/xmp files exist')

    # ── Check 6: shadow_history completeness ──────────────────────────────────
    shadow_problems = []
    for s in sites:
        sh = s.get('shadow_history', '').strip()
        if not sh:
            shadow_problems.append(f'{s["slug"]}: empty shadow_history')
        elif sh != SHADOW_HISTORY_NONE and \
                difflib.SequenceMatcher(None, sh, SHADOW_HISTORY_NONE).ratio() > 0.8:
            shadow_problems.append(f'{s["slug"]}: near-miss variant of the standard '
                                   f'none-found text: {sh!r}')
    if shadow_problems:
        report(6, 'FAIL', '\n    '.join(shadow_problems))
    else:
        report(6, 'PASS', 'every site has narrative text or the exact standard none-found text')

    if failures:
        print(f'\n{failures} check(s) failed')
        return 1
    print('\nall checks passed' + (' (with warnings)' if pending else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
