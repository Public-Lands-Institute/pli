#!/usr/bin/env python3
"""
Public Lands Institute — Native Land territories for the map's native layer.
Run from the repo root:
    python3 tools/nativeland_territories.py            # sites with no nations_nld yet
    python3 tools/nativeland_territories.py --all      # refresh every site
    python3 tools/nativeland_territories.py --site <slug>

For each site, queries the native-land.ca territories API at the site's lat/lng
(a point-in-polygon lookup against Native Land Digital's current territories
layer) and writes sites_meta.json:
    nations_nld    Native Land territories containing the point, as PLI labels
    nld_retrieved  YYYY-MM-DD of the query

The curated `nations` list (nations documented at the site in its record) is
left alone; build.py shows the union of the two on the map.

Native Land names are mapped onto existing PLI labels (NLD_LABELS) so the
legend does not show the same nation twice. An unmapped name is used as
returned and printed, so it can be added to the table.

Needs NATIVELAND_API_KEY in .env.
"""

import datetime
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# Native Land name -> PLI label(s). A list splits a combined territory.
NLD_LABELS = {
    'Myaamia': 'Myaamia (Miami)',
    'Shawandasse Tula (Shawanwaki/Shawnee)': 'Shawnee',
    'Kiikaapoi (Kickapoo)': 'Kickapoo',
    'Očhéthi Šakówiŋ': 'Oceti Sakowin (Sioux)',
    'ᏣᎳᎫᏪᏘᏱ Tsalaguwetiyi (Cherokee, East)': 'Cherokee',
    'S’atsoyaha (Yuchi)': 'Yuchi',
    'Bodwéwadmi (Potawatomi)': 'Potawatomi',
    'O-ga-xpa Ma-zhoⁿ (O-ga-xpa) (Quapaw)': 'O-ga-xpa (Quapaw)',
    "Tsétsėhéstȧhese/Tsitsistas/Só'taeo'o (Cheyenne)": 'Cheyenne',
    'Nʉmʉnʉʉ Sookobitʉ (Comanche)': 'Comanche',
    'Núu-agha-tʉvʉ-pʉ̱ (Ute)': 'Ute (Núuchi-u / Núu-agha-tʉvʉ-pʉ̱)',
    'Gáuigú (Kiowa)': 'Kiowa',
    'Odawa': 'Ottawa (Odawa)',
    'Mvskoke (Muscogee)': 'Muscogee (Creek)',
    'Ndé Kónitsąąíí Gokíyaa (Lipan Apache)': 'Lipan Apache (Ndé Kónitsąąíí Gokíyaa)',
    'Meškwahki·aša·hina (Fox)': 'Meskwaki',
    'Diné Bikéyah': 'Navajo (Diné)',
    'Yankton': 'Yankton Dakota',
    'oθaakiiwaki‧hina‧ki (Sauk) & Meškwahki·aša·hina (Fox)': ['Sauk', 'Meskwaki'],
    'Kiowa-Comanche-Apache (Oklahoma)': ['Kiowa', 'Comanche', 'Apache'],
    'Jicarilla Apache': 'Jicarilla Apache (Tinde)',
    'Nuwuvi (Southern Paiute)': 'Southern Paiute (Nuwuvi)',
    'Newe Sogobia (Eastern Shoshone)': 'Eastern Shoshone',
    'Hoocąk (Ho-Chunk)': 'Ho-Chunk',
    'Ishak (Atakapa)': 'Ishak (Atakapa-Ishak)',
}


def pli_labels(name):
    if 'Osage' in name:  # returned in Osage script with stray carets
        return ['Osage']
    label = NLD_LABELS.get(name, name)
    return label if isinstance(label, list) else [label]


def load_key():
    key = os.environ.get('NATIVELAND_API_KEY', '')
    if not key and os.path.exists('.env'):
        for line in open('.env'):
            if line.startswith('NATIVELAND_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"\'')
    if not key:
        sys.exit('NATIVELAND_API_KEY not set in .env')
    return key


def query(lat, lng, key):
    # curl, not urllib: native-land.ca returns 403 to Python's default user agent
    url = f'https://native-land.ca/api/index.php?maps=territories&position={lat},{lng}&key={key}'
    for _ in range(3):
        r = subprocess.run(['curl', '-s', '-f', '-m', '40', url], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                return [f['properties']['Name'] for f in json.loads(r.stdout)]
            except (ValueError, KeyError):
                pass
        time.sleep(3)
    return None


def main(argv):
    with open('sites.json') as f:
        sites = json.load(f)
    with open('sites_meta.json') as f:
        meta = json.load(f)
    if '--site' in argv:
        want = {argv[argv.index('--site') + 1]}
    elif '--all' in argv:
        want = {s['slug'] for s in sites}
    else:
        want = {s['slug'] for s in sites if 'nations_nld' not in meta.get(s['slug'], {})}
    key = load_key()
    today = datetime.date.today().isoformat()
    known = set(NLD_LABELS) | {l for v in meta.values() for l in v.get('nations', [])}
    failed = []
    for site in sites:
        slug = site['slug']
        if slug not in want:
            continue
        names = query(site['lat'], site['lng'], key)
        if names is None:
            failed.append(slug)
            continue
        labels = []
        for n in names:
            if n not in known and 'Osage' not in n:
                print(f'  unmapped Native Land name (used as returned): {n}')
            for l in pli_labels(n):
                if l not in labels:
                    labels.append(l)
        meta.setdefault(slug, {})['nations_nld'] = labels
        meta[slug]['nld_retrieved'] = today
        print(f'{slug}: {", ".join(labels)}')
        time.sleep(0.3)
    with open('sites_meta.json', 'w') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write('\n')
    if failed:
        sys.exit(f'failed: {", ".join(failed)}')


if __name__ == '__main__':
    main(sys.argv[1:])
