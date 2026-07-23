#!/usr/bin/env python3
"""
Public Lands Institute — point site-page og:image tags at the social cards.
Run from the repo root (after tools/make_cards.py):
    python3 tools/add_site_og.py

For every sites/<slug>.html: replaces the og:image URL with the site's card
(img/cards/<slug>.jpg) and adds og:image:width / og:image:height after it.
twitter:card already exists on the site pages and is left as is. Idempotent.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

BASE = 'https://publiclandsinstitute.net'


def main():
    with open('sites.json') as f:
        sites = json.load(f)
    changed = 0
    for site in sites:
        slug = site['slug']
        path = f'sites/{slug}.html'
        card = f'{BASE}/img/cards/{slug}.jpg'
        if not os.path.exists(f'img/cards/{slug}.jpg'):
            print(f'  skipped {slug}: no card')
            continue
        html = open(path).read()
        new = re.sub(r'<meta property="og:image" content="[^"]*"/>',
                     f'<meta property="og:image" content="{card}"/>', html)
        if '<meta property="og:image:width"' not in new:
            new = new.replace(
                f'<meta property="og:image" content="{card}"/>',
                f'<meta property="og:image" content="{card}"/>\n'
                f'<meta property="og:image:width" content="1200"/>\n'
                f'<meta property="og:image:height" content="630"/>')
        if new != html:
            open(path, 'w').write(new)
            changed += 1
    print(f'site pages updated: {changed}')


if __name__ == '__main__':
    main()
