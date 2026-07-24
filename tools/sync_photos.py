#!/usr/bin/env python3
"""
Public Lands Institute — append data/photos.json entries for new images.
Run from the repo root, AFTER Commons upload (upload_next.py) and thumbnail
generation, BEFORE build.py:
    python3 tools/sync_photos.py [--site <slug>] [--dry-run]

Scans img/jpg/<slug>/ for every site in sites.json. Camera files with no
photos.json entry are appended to the END of the site's list, so existing
caption numbers never shift. Each new entry gets:
  d              EXIF DateTimeOriginal (previous image's date when missing)
  thumb / large  thumbs/<slug>/<cam> and thumbs/<slug>/lg_<cam> (warns if absent)
  f / t / c / commons_n  from ../pli-commons/upload_log.json when uploaded;
                 until then f=camera filename and t/c stay empty ("Uploading"
                 state in the archive)
  r / x          img/RAW/<slug>/<stem>.RAF|.NEF and .xmp when present
"""

import json
import os
import re
import sys
import urllib.parse

from PIL import Image
from PIL.ExifTags import TAGS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

COMMONS_LOG = os.path.expanduser(
    '~/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli-commons/upload_log.json')
COMMONS_NUM_RE = re.compile(r'- (\d+)\.\w+$')


def exif_date(path):
    try:
        exif = Image.open(path)._getexif()
        if exif:
            for tag_id, val in exif.items():
                if TAGS.get(tag_id) == 'DateTimeOriginal':
                    return val[:10].replace(':', '-')
    except Exception:
        pass
    return ''


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
    site_filter = None
    if '--site' in sys.argv:
        site_filter = sys.argv[sys.argv.index('--site') + 1]
    dry_run = '--dry-run' in sys.argv

    with open('sites.json') as f:
        sites = json.load(f)
    with open('data/photos.json') as f:
        photos = json.load(f)

    commons = {}
    if os.path.exists(COMMONS_LOG):
        for e in json.load(open(COMMONS_LOG)):
            stem = os.path.splitext(os.path.basename(e['source_path']))[0]
            commons[(e['slug'], stem)] = e['commons_filename']

    added_total = 0
    for site in sites:
        slug = site['slug']
        if site_filter and slug != site_filter:
            continue
        jpg_dir = f'img/jpg/{slug}'
        if not os.path.isdir(jpg_dir):
            continue
        entries = photos.setdefault(slug, [])
        existing = {camera_filename(e) for e in entries}
        last_date = entries[-1].get('d', '') if entries else ''
        new_files = sorted(f for f in os.listdir(jpg_dir)
                           if f.lower().endswith(('.jpg', '.jpeg')) and f not in existing)
        for cam in new_files:
            stem = os.path.splitext(cam)[0]
            d = exif_date(os.path.join(jpg_dir, cam)) or last_date
            last_date = d
            thumb = f'thumbs/{slug}/{cam}'
            large = f'thumbs/{slug}/lg_{cam}'
            for p in (thumb, large):
                if not os.path.exists(p):
                    print(f'  WARNING: {p} missing — generate thumbnails before build.py',
                          file=sys.stderr)
            raw = next((f'img/RAW/{slug}/{stem}{ext}' for ext in ('.RAF', '.NEF')
                        if os.path.exists(f'img/RAW/{slug}/{stem}{ext}')), '')
            xmp = next((f'img/RAW/{slug}/{stem}{ext}' for ext in ('.xmp', '.XMP')
                        if os.path.exists(f'img/RAW/{slug}/{stem}{ext}')), '')
            name = commons.get((slug, stem))
            entry = {
                'f': name or cam,
                'd': d,
                'thumb': thumb if os.path.exists(thumb) else '',
                'large': large if os.path.exists(large) else '',
                't': ('https://commons.wikimedia.org/wiki/Special:FilePath/'
                      + urllib.parse.quote(name)) if name else '',
                'r': raw,
                'x': xmp,
                'c': ('https://commons.wikimedia.org/wiki/File:'
                      + urllib.parse.quote(name.replace(' ', '_'))) if name else '',
            }
            if name:
                m = COMMONS_NUM_RE.search(name)
                if m:
                    entry['commons_n'] = int(m.group(1))
            entries.append(entry)
            added_total += 1
            print(f'  {slug}: + {cam} (caption {len(entries)}, '
                  f'{"Commons " + name.rsplit(" - ", 1)[-1] if name else "pending upload"})')

    if added_total and not dry_run:
        with open('data/photos.json', 'w') as f:
            json.dump(photos, f, ensure_ascii=False, indent=2)
            f.write('\n')
    print(f'{"[dry run] " if dry_run else ""}{added_total} new entries'
          + ('' if dry_run or not added_total else ' written to data/photos.json'))


if __name__ == '__main__':
    main()
