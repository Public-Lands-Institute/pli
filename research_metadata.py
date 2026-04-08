#!/usr/bin/env python3
"""
research_metadata.py — populate displacement_tenure from native-land.ca treaties API.

Run from PLI root:
    python3 research_metadata.py

For each site in sites.json, queries the native-land.ca /api/index.php?maps=treaties
endpoint using the site's GPS coordinates. Extracts treaty names and writes them to
the displacement_tenure field.

Sites flagged for manual research (complex tenure history) are left with a TODO
comment explaining what requires deeper work.

Safe to re-run: skips entries that already have a non-empty, non-TODO displacement_tenure.
Force refresh a single site by clearing its displacement_tenure field first.
"""

import json, os, time, urllib.request, urllib.parse
from dotenv import load_dotenv
load_dotenv()

SITES_FILE = 'sites.json'
CACHE_FILE = 'nativeland_cache.json'

# Sites whose tenure history involves documented atrocities, litigation, or
# complex multi-party land acquisition that requires manual narrative — not just
# a list of treaties. The script flags these with a TODO rather than overwriting.
COMPLEX_TENURE = {
    'mammoth-cave-national-park':
        'TODO: enslaved labor documented in cave saltpeter mining and tourist operations '
        '1810s-1840s; NPS acquired land from private owners beginning 1926; full land '
        'tenure narrative requires archival research',
    'johnsons-shut-ins-state-park':
        'TODO: 2005 AmerenUE Taum Sauk reservoir breach destroyed lower park; '
        'litigation settlement 2009 funded restoration; land tenure predates breach — '
        'research original Ozark acquisition history',
    'arc-of-appalachia':
        'TODO: privately assembled preserve system beginning 1995; parcels acquired '
        'from multiple landowners; research individual tract deed history',
}

with open(SITES_FILE) as f:
    sites = json.load(f)

cache = {}
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE) as f:
        cache = json.load(f)

api_key = os.environ.get('NATIVELAND_API_KEY', '')
if not api_key:
    print('WARNING: NATIVELAND_API_KEY not set in .env — API calls may fail or be rate-limited')

updated = 0

for site in sites:
    slug = site['slug']
    existing = site.get('displacement_tenure', '')

    # Skip if already populated with real data
    if existing and not existing.startswith('TODO'):
        print(f'  {slug}: already populated, skipping')
        continue

    # Flag complex cases for manual entry
    if slug in COMPLEX_TENURE:
        site['displacement_tenure'] = COMPLEX_TENURE[slug]
        print(f'  {slug}: flagged as complex (TODO)')
        updated += 1
        continue

    lat = site.get('lat')
    lng = site.get('lng')
    if not lat or not lng:
        print(f'  {slug}: no GPS, skipping')
        continue

    # Query treaties API (cached)
    cache_key = f'treaties:{slug}'
    if cache_key in cache:
        treaty_data = cache[cache_key]
        print(f'  {slug}: using cached treaty data')
    else:
        url = (
            f'https://native-land.ca/api/index.php?maps=treaties'
            f'&position={lat},{lng}'
            + (f'&key={api_key}' if api_key else '')
        )
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'PublicLandsInstitute/1.0 (publiclandsinstitute.net)'}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                treaty_data = json.load(r)
            time.sleep(0.6)
            cache[cache_key] = treaty_data
            with open(CACHE_FILE, 'w') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            print(f'  {slug}: fetched {len(treaty_data)} treaty feature(s) from API')
        except Exception as e:
            print(f'  {slug}: API error — {e}')
            site['displacement_tenure'] = 'TODO: API unavailable; research land cession treaties manually'
            updated += 1
            continue

    # Extract treaty names from GeoJSON features
    treaties = []
    for feature in treaty_data:
        props = feature.get('properties', {})
        name = props.get('Name', '').strip()
        if name:
            treaties.append(name)

    if treaties:
        site['displacement_tenure'] = '; '.join(f'Ceded via {t}' for t in treaties)
    else:
        site['displacement_tenure'] = (
            'TODO: no treaty data returned for this location; '
            'research land cession history manually'
        )

    updated += 1

# Write back
with open(SITES_FILE, 'w') as f:
    json.dump(sites, f, indent=2, ensure_ascii=False)

print(f'\nDone — updated {updated} entries. Run python3 generate_sites.py to rebuild.')
