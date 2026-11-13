#!/usr/bin/env python3
"""
Public Lands Institute — build.py
Single-source-of-truth page builder.
Run from the root of the PLI site folder:
    python3 build.py                 # build everything, then validate
    python3 build.py archive mapjs   # build a subset
    python3 build.py --no-validate   # skip tools/validate_pli.py

Inputs:
  sites.json            location records (one object per site)
  sites_meta.json       agency / agency_type / nations / cultures
  data/photos.json      per-site image entries, keyed by slug
                        entry shape: f, d, thumb, large, t, r, x, c

Outputs:
  sites/<slug>.html     one page per site (record column + photo pane)
  archive.html          plain-text download index (all rows, per-site sections)
  photographs.html      visual feed grouped by site
  about.html            stats sentence only — the rest of the page is hand-maintained
  support.html          counts line only — the rest of the page is hand-maintained
  prospective.html      public Prospective Sites page (map + list), from the public
                        entries in submissions/suggestions.json
  data/suggestions-map.js  SUGGESTIONS geojson (public fields only), loaded by
                        index.html and prospective.html with a ?v= content hash
  sitemap.xml           lastmod = each source file's actual last-modified date
  data/nations.geojson  per-(site, nation or culture) points for the map's native
                        layer, derived from sites_meta.json on every mapjs build
  data/sites-map.js     SITES / NATIONS_GJ / PHOTOS / NATION_COLORS / NATION_LIST /
                        CULTURE_LIST / NATION_COUNTS,
                        loaded by index.html with a ?v= content-hash query string

glossary.html and index.html are hand-maintained (build.py only stamps the
sites-map.js version string into index.html).

Ends by running tools/validate_pli.py; exits nonzero if validation fails.
"""

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


# Endonym/exonym label variants that name the SAME nation. Only true duplicates
# are merged here; distinct bands (the various Ute or Dakota divisions, Wea vs
# Miami, Sauk vs Meskwaki) are deliberately left separate.
NATION_CANON = {
    'Miami': 'Myaamia (Miami)',
    'Myaamia': 'Myaamia (Miami)',
    'Miami (Myaamia)': 'Myaamia (Miami)',
    'Odawa': 'Ottawa (Odawa)',
    'Odawa (Ottawa)': 'Ottawa (Odawa)',
    'Ojibwe (Chippewa)': 'Ojibwe',
    'Potawatomi (Bodéwadmi)': 'Potawatomi',
    'Wea (Waayaahtanwa)': 'Wea',
    'Lenape': 'Lenape (Delaware)',
    'Delaware': 'Lenape (Delaware)',
    'Delaware (Lenape)': 'Lenape (Delaware)',
    'Comanche (Nʉmʉnʉʉ)': 'Comanche',
    'Kiowa (Cáuigù)': 'Kiowa',
    'Osage (Wazhazhe)': 'Osage',
    'Ottawa': 'Ottawa (Odawa)',
    'Hopi (Hopisinom)': 'Hopi',
    'Yuchi (Tsoyaha)': 'Yuchi',
    'Wichita (Kitikiti’sh)': 'Wichita',
    'Ute Mountain Ute (Weeminuche)': 'Ute Mountain Ute',
}


# ── Native Land filter ────────────────────────────────────────────────────────
# Native Land's territory polygons are broad (the Kaskaskia polygon covers all
# of Ohio and Indiana), so a point-in-polygon match alone does not put a nation
# on the map. A nation from `nations_nld` is kept for a site only when the
# site's native_lands or displacement_tenure text names it, by the canonical
# label or a common alternate below. Nations in the curated `nations` list are
# always kept. The raw Native Land result stays in sites_meta.json
# (`nations_nld`), so this filter can be rerun or changed at any time.
# A second test, a Royce cession polygon containing the site and made by that
# nation, is not applied: the pipeline has no Royce cession geometry.
# Patterns are case-insensitive except inside (?-i:...); lookarounds keep place
# names (Little Miami River, Lake Erie, Ottawa County, Taum Sauk) from counting.
NATION_ALIASES = {
    'Kaskaskia': r'\bKaskaskias?\b(?!\s+River)',
    'Peoria': r'\bPeorias?\b(?!\s+(County|Lake))|Illinois Confederacy|Illiniwek|Inoka',
    'Shawnee': r'\bShawnees?\b|Shawanwaki|Šawanwaki|Shawandasse',
    'Myaamia (Miami)': r'Myaamia|(?<!Great )(?<!Little )\bMiamis?\b(?!\)?\s+(River|Valley|Canal|and Erie|County|University|Whitewater|Township|Bend|Fort|Purchase|Conservancy|Rapids))',
    'Osage': r'\bOsages?\b(?!\s+(orange|River|Plains|County|Cuestas|Reserve))|Wazhazhe',
    'Kickapoo': r'Kickapoo|Kiikaapoi|Kiiakapoi',
    'Oceti Sakowin (Sioux)': r'Oceti|Očhéthi|\bSioux\b(?!\s+River)|\bLakh?ota\b|(?<!North )(?<!South )\bDakotas?\b(?!\s+Territory)|\bNakota\b',
    'Cherokee': r'Cherokee|Tsalagi|Tsalaguwetiyi|Aniyvwiya',
    'Yuchi': r'Yuchi|Euchee|Tsoyaha',
    'Potawatomi': r'Potawatomi|Pottawatomi|Bod[ée]wadmi|Bodwéwadmi|Bodewadmi|Neshnab',
    'O-ga-xpa (Quapaw)': r'Quapaw(?!\s+Agency)|O-ga-xpa',
    'Cheyenne': r'Cheyenne(?!\s+River)|Tsitsistas',
    'Comanche': r'Comanche|Nʉmʉnʉʉ',
    'Ute (Núuchi-u / Núu-agha-tʉvʉ-pʉ̱)': r'\bUtes?\b|Núuchi|Núu-agha',
    'Meskwaki': r'Meskwaki|Mesquakie|Sau?k and Fox|Sac and Fox|Sauk, Fox',
    'Sauk': r'(?<!Taum )\bSauk\b|\bSac\b|Ozaakiiwaki',
    'Ofo': r'\bOfo\b|Mosopelea',
    'Miccosukee': r'Miccosukee|Mikasuki',
    'Kiowa': r'Kiowa|Cáuigù|Gáuigú',
    'Wyandot': r'Wyandott?e?s?\b(?!\s+County)|Wendat|(?<!Lake )\bHurons?\b(?!\s+(River|County))',
    'Ottawa (Odawa)': r'Odawa|\bOttawas?\b(?!\s+(County|National|River))',
    'Muscogee (Creek)': r'Muscogee|Muskogee|Mvskoke|\bCreeks?\s+(Nation|Confederacy|War|Indians)|Upper Creek|Lower Creek|\(Creek\)|(?<=, )Creeks?(?=[,;)]| and )',
    'Wichita': r'(?<!town of )\bWichita\b(?!\s+(Mountains|Falls|County|Forest))|Kitikiti',
    'Lipan Apache (Ndé Kónitsąąíí Gokíyaa)': r'Lipan|Kónitsąąíí',
    'Apache': r'Apache',
    'Jicarilla Apache (Tinde)': r'Jicarilla',
    'Pueblos': r'(?-i:(?<!Ancestral )\bPueblos?\b)|Zuni|A:shiwi|\bTewa\b|\bTiwa\b|\bKeres',
    'Apsáalooke (Crow)': r'Apsáalooke|Apsaalooke|(?-i:\bCrow\b)',
    'Hitchiti': r'Hitchiti',
    'Navajo (Diné)': r'Navajo|Diné',
    'Yankton Dakota': r'Yankton|Ihanktonwan|Ihanktunwan',
    'Erie': r'(?<!Lake )(?<!and )\bErie\b(?!\s+(Canal|County|Railroad|Basin|Lowland|Lake Plain|Shale))|Eriehronon',
    'Yamasee': r'Yamasee|Yemassee',
    'Timpanogos': r'Timpanogos(?!\s+(Cave|Mountain|Peak))',
    'Southern Paiute (Nuwuvi)': r'Paiute|Nuwuvi',
    'Eastern Shoshone': r'Shoshone|\bNewe\b',
    'Cayuse, Umatilla and Walla Walla': r'Cayuse|Umatilla|Walla Walla',
    'Mnicoujou': r'Mnicoujou|Miniconjou|Minneconjou',
    'Wahpeton': r'Wahpeton',
    'Ho-Chunk': r'Ho-?Chunk|Hoocąk|Hochungra|Winnebago',
    'Mississauga': r'Mississauga',
    'Moneton': r'Moneton',
    'Yesan (Tutelo)': r'Tutelo|Yesan',
    'Karankawa': r'Karankawa',
    'Ishak (Atakapa-Ishak)': r'Atakapa|Ishak',
}
_NATION_RX = {}


def nation_rx(cn):
    """Compiled pattern for a canonical nation label. A label with no entry in
    NATION_ALIASES falls back to its own name parts, e.g. 'Foo (Bar)' matches
    Foo or Bar."""
    if cn not in _NATION_RX:
        pat = NATION_ALIASES.get(cn)
        if pat is None:
            parts = [p.strip() for p in re.split(r'[()/]', cn) if p.strip()]
            pat = '|'.join(r'\b' + re.escape(p) + r'\b' for p in parts)
        _NATION_RX[cn] = re.compile(pat, re.I)
    return _NATION_RX[cn]


def site_nations(site, m):
    """Nations for one site under the filter rule.
    Returns (kept, dropped): kept is a list of (canonical label, source), source
    'record' (curated `nations`) or 'text' (Native Land, named in the record
    text); dropped lists canonical Native Land labels the record does not name."""
    text = ' '.join([site.get('native_lands', ''), site.get('displacement_tenure', '')])
    kept, seen, dropped = [], set(), []
    for n in m.get('nations', []):
        cn = NATION_CANON.get(n, n)
        if cn not in seen:
            seen.add(cn)
            kept.append((cn, 'record'))
    for n in m.get('nations_nld', []):
        cn = NATION_CANON.get(n, n)
        if cn in seen or cn in dropped:
            continue
        if nation_rx(cn).search(text):
            seen.add(cn)
            kept.append((cn, 'text'))
        else:
            dropped.append(cn)
    return kept, dropped


NATION_PALETTE = [
    '#e8a838', '#5b9e6e', '#5b8abf', '#bf5b7a', '#7a5bbf', '#c87840', '#5bbfbf',
    '#bf5b5b', '#8cbf5b', '#4a6ebf', '#bf9e5b', '#5bbf8c', '#bf5b9e', '#5b9ebf',
    '#9ebf5b', '#bf6e5b', '#8a5bbf', '#bfbf5b', '#e87c5b', '#5be8a8', '#c45be8',
    '#e8c45b', '#5bc4e8', '#e85b8a', '#a8e85b', '#c8a050', '#6abf9e', '#9e6abf',
]


def nation_color(name):
    """Deterministic legend color from the (canonical) label."""
    return NATION_PALETTE[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(NATION_PALETTE)]


def build_nations_geojson(sites, meta):
    """One point per (site, nation or culture), from sites_meta.json.

    Nations are the curated `nations` (documented in the site record) plus the
    `nations_nld` entries (Native Land territories containing the site, written
    by tools/nativeland_territories.py) that pass the filter in site_nations().
    Cultures come from `cultures` only. Regenerated on every build so new sites
    can never be missing from the map's territory layer.
    """
    features = []
    for site in sites:
        lat, lng = site.get('lat'), site.get('lng')
        if lat is None or lng is None:
            continue
        m = meta.get(site['slug'], {})
        kept, _ = site_nations(site, m)
        cultures, seen = [], set()
        for n in m.get('cultures', []):
            cn = NATION_CANON.get(n, n)
            if cn not in seen:
                seen.add(cn)
                cultures.append(cn)
        for group, names in (('nation', [cn for cn, _ in kept]), ('culture', cultures)):
            for cn in names:
                features.append({
                    'type': 'Feature',
                    'geometry': {'type': 'Point', 'coordinates': [lng, lat]},
                    'properties': {'slug': site['slug'], 'nation': cn,
                                   'group': group, 'color': nation_color(cn)},
                })
    return {'type': 'FeatureCollection', 'features': features}


def load_data():
    with open('sites.json') as f:
        sites = json.load(f)
    with open('sites_meta.json') as f:
        meta = json.load(f)
    with open('data/photos.json') as f:
        photos = json.load(f)
    nations_gj = build_nations_geojson(sites, meta)
    return sites, meta, photos, nations_gj


# ── Image records ──────────────────────────────────────────────────────────────

def camera_filename(entry):
    """Recover the camera filename (e.g. _DSF2909.jpg) from a photos.json entry."""
    if entry.get('thumb'):
        return os.path.basename(entry['thumb'])
    if entry.get('large'):
        return os.path.basename(entry['large'])[3:]  # strip lg_ prefix
    f = entry.get('f', '')
    if f.lower().endswith(('.jpg', '.jpeg')):
        return f
    if entry.get('r'):
        return os.path.splitext(os.path.basename(entry['r']))[0] + '.jpg'
    raise ValueError(f'cannot derive camera filename for entry {entry!r}')


def image_records(slug, entries):
    """Template-facing view of a site's photos.json entries, in caption order."""
    out = []
    for i, e in enumerate(entries):
        cam = camera_filename(e)
        out.append({
            'jpg': f'img/jpg/{slug}/{cam}',
            'camera_filename': cam,
            'caption_index': str(i + 1),
            'date': e.get('d', '') or '',
            'tif_url': e.get('t') or None,
            'commons_page': e.get('c') or None,
            'raw': e.get('r') or None,
            'xmp': e.get('x') or None,
        })
    return out


def format_obs_date(date_str):
    """Format 'YYYY-MM' as 'January 2026', or return as-is."""
    if not date_str or len(date_str) < 7:
        return date_str or ''
    try:
        dt = datetime.datetime.strptime(date_str[:7], '%Y-%m')
        return dt.strftime('%B %Y')
    except ValueError:
        return date_str


# ── Project counts (single source for every page that states them) ────────────

def site_counts(all_sites, photos):
    """The four project figures, derived from sites.json + data/photos.json.
    Photographs count unique frames: one (slug, camera filename) pair each.
    Acreage sums the numeric acreage_n field and is reported in millions to one
    decimal place. Every page that states these figures goes through here."""
    frames = {(slug, camera_filename(e))
              for slug, entries in photos.items() for e in entries}
    acres = sum(s.get('acreage_n') or 0 for s in all_sites)
    return {
        'sites': len(all_sites),
        'states': len({s['state'] for s in all_sites}),
        'photographs': len(frames),
        'acres': acres,
        'acres_m': f'{acres / 1_000_000:.1f}',
    }


def counts_line(all_sites, photos):
    """Single-line form of the four figures, used on support.html."""
    c = site_counts(all_sites, photos)
    return (f'{c["sites"]} sites, {c["states"]} states, '
            f'{c["photographs"]} photographs, {c["acres_m"]} million acres')


# ── Shared page chrome ─────────────────────────────────────────────────────────

FONT_LINKS = '''<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500&display=swap" rel="stylesheet">'''

SHARED_CSS = '''  :root {
    --bg: #161616;
    --fg: #e8e8e8;
    --muted: #8c8c8c;
    --border: rgba(255,255,255,0.16);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--fg);
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", sans-serif;
    font-weight: 300;
    line-height: 1.5;
    letter-spacing: 0.01em;
  }
  a { color: inherit; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .page {
    max-width: 1500px;
    margin: 24px auto 56px auto;
    padding: 0 18px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 28px;
    gap: 12px;
    flex-wrap: wrap;
  }
  .logotype {
    text-transform: uppercase;
    letter-spacing: 0.24em;
    font-size: 11px;
    font-weight: 500;
  }
  .header-nav {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: var(--muted);
    display: flex;
    gap: 16px;
  }
  .header-nav a.active { color: var(--fg); }
  .divider { border-bottom: 1px solid var(--border); margin: 0 0 28px 0; }
  footer {
    margin-top: 40px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    display: flex;
    justify-content: space-between;
    color: var(--muted);
    flex-wrap: wrap;
    gap: 8px;
  }
  @media (min-width: 720px) {
    .page { margin-top: 40px; padding: 0 24px; }
    header { margin-bottom: 40px; }
  }
  .gps-link {
    color: inherit;
    text-decoration: none;
    display: inline-block;
    padding: 11px 0;
    margin: -11px 0;
  }
  .gps-link:hover { text-decoration: underline; }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }'''


STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming',
}


# ── Site pages ─────────────────────────────────────────────────────────────────

# Eras/epochs matched against geological_age + epoch text; color + onset Mya.
GEO_TIMESCALE = [
    ('Archean', '#3a3a52', 4000), ('Proterozoic', '#5c5c8a', 2500),
    ('Cambrian', '#a0522d', 541), ('Ordovician', '#c8a86e', 485),
    ('Silurian', '#7ecfc0', 444), ('Devonian', '#4aaa78', 419),
    ('Mississippian', '#3d7fbf', 359), ('Pennsylvanian', '#5d5abf', 323),
    ('Permian', '#9b59b6', 299), ('Triassic', '#e07050', 252),
    ('Jurassic', '#c8a840', 201), ('Cretaceous', '#d4b840', 145),
    ('Paleogene', '#d4704a', 66), ('Eocene', '#d4704a', 56), ('Oligocene', '#d4704a', 34),
    ('Neogene', '#c85a8a', 23),
    ('Quaternary', '#8c8c8c', 2.6), ('Pleistocene', '#8c8c8c', 2.6),
]
EARTH_TIMELINE_MYA = 541


def make_geo_block(geo_text, epoch_text=''):
    """Era swatch + timeline bar + full geological_age prose, mirroring the map panel.

    Matches era names across geological_age and epoch text combined, since some
    entries state the era only in one field. Picks the oldest era mentioned as
    the headline. The Mya number badge is only attached when the winning era is
    also the first era name to appear in its clause, so a badge never gets
    paired with a number that actually belongs to a different, later-mentioned era.
    """
    if not geo_text:
        return ''
    combined = geo_text + ('; ' + epoch_text if epoch_text else '')
    clauses = re.split(r'[;.]', combined)
    best = None  # (era, color, oldest, clause)
    for clause in clauses:
        c = clause.lower()
        for era, color, oldest in GEO_TIMESCALE:
            if era.lower() in c and (best is None or oldest > best[2]):
                best = (era, color, oldest, clause)
    era_row = ''
    bar = ''
    if best:
        era, color, oldest, clause = best
        mya = ''
        m = re.search(r'~?([\d,]+)(?:\s*(?:-|to)\s*([\d,]+))?\s*[Mm]ya', clause)
        if m:
            c = clause.lower()
            positions = [(c.find(e.lower()), e) for e, _, _ in GEO_TIMESCALE if e.lower() in c]
            first_era = min(positions)[1] if positions else None
            if first_era == era:
                num = m.group(1).replace(',', '')
                if m.group(2):
                    num += '-' + m.group(2).replace(',', '')
                mya = f'<span class="geo-mya">{num} Mya</span>'
        pct = min(100, round(oldest / EARTH_TIMELINE_MYA * 100))
        era_row = (f'<div class="geo-era-row"><div class="geo-swatch" style="background:{color}"></div>'
                   f'<span class="geo-era-name">{era}</span>{mya}</div>')
        bar = (f'<div class="geo-bar-wrap"><div class="geo-bar-fill" '
               f'style="width:{pct}%;background:{color};opacity:0.55"></div></div>')
    return (f'<div class="rec-section"><div class="rec-label">Geologic Age'
            f' <a href="../glossary.html#geologic-time" class="rec-glossary-link">Glossary →</a></div>'
            f'{era_row}{bar}<p class="geo-prose">{geo_text}</p></div>')


def observations_for_site(site, entries):
    """[{date, notes, images}] groups for a site's photo pane.

    If the site has an explicit 'observations' key (see CLAUDE.md schema), its
    image_list filenames are matched against data/photos.json. Otherwise the
    photos.json order is canonical: consecutive entries sharing a capture month
    form one group. Caption numbers always come from photos.json position.
    """
    recs = image_records(site['slug'], entries)
    if 'observations' in site:
        by_cam = {r['camera_filename']: r for r in recs}
        result = []
        for obs in site['observations']:
            images = [by_cam[f] for f in obs.get('image_list', []) if f in by_cam]
            result.append({'date': obs.get('date', ''), 'notes': obs.get('notes', ''),
                           'images': images})
        return result
    result = []
    for r in recs:
        key = r['date'][:7] if r['date'] and len(r['date']) >= 7 else ''
        if not result or result[-1]['date'] != key:
            result.append({'date': key, 'notes': '', 'images': []})
        result[-1]['images'].append(r)
    return result


def make_site_page(site, all_sites, photos):
    slug  = site['slug']
    name  = site['name']
    state = site['state']
    observations = observations_for_site(site, photos.get(slug, []))

    og_image_tags = ''
    if os.path.exists(f'img/cards/{slug}.jpg'):
        og_image_tags = (
            f'<meta property="og:image" content="https://publiclandsinstitute.net/img/cards/{slug}.jpg"/>\n'
            f'<meta property="og:image:width" content="1200"/>\n'
            f'<meta property="og:image:height" content="630"/>\n'
            f'<meta name="twitter:card" content="summary_large_image"/>\n')

    idx       = next(i for i, s in enumerate(all_sites) if s['slug'] == slug)
    prev_site = all_sites[idx - 1] if idx > 0 else None
    next_site = all_sites[idx + 1] if idx < len(all_sites) - 1 else None

    nav_prev = f'<a href="{prev_site["slug"]}.html">← {prev_site["name"]}</a>' if prev_site else '<span></span>'
    nav_next = f'<a href="{next_site["slug"]}.html">{next_site["name"]} →</a>' if next_site else '<span></span>'

    def sec(label, val, glossary_anchor=None):
        if not val:
            return ''
        link = f' <a href="../glossary.html#{glossary_anchor}" class="rec-glossary-link">Glossary →</a>' if glossary_anchor else ''
        return f'<div class="rec-section"><div class="rec-label">{label}{link}</div><p>{val}</p></div>'

    gps_val = ''
    if site.get('gps'):
        lat = site.get('lat', '')
        lng = site.get('lng', '')
        gps_val = f'<a class="gps-link" href="https://maps.google.com/?q={lat},{lng}" target="_blank" rel="noopener">{site["gps"]}</a>'

    sections = make_geo_block(site.get('geological_age', ''), site.get('epoch', ''))
    sections += sec('Epoch', site.get('epoch', ''))
    sections += sec('Native lands', site.get('native_lands', ''), glossary_anchor='indigenous-nations')
    sections += sec('Displacement &amp; Tenure', site.get('displacement_tenure', ''))
    sections += sec('Shadow History', site.get('shadow_history', ''))
    sections += sec('Ecology', site.get('ecology', ''))
    sections += sec('Hydrology', site.get('hydrology', ''))
    sections += sec('Acreage', site.get('acreage', ''))
    sections += sec('GPS', gps_val)

    show_obs_headers = len(observations) > 1 or any(obs.get('notes') for obs in observations)
    total_images = sum(len(obs['images']) for obs in observations)
    view_all_label = f'View all {total_images} images →' if total_images > 1 else 'Open viewer →'
    images_html = ''
    for obs in observations:
        if show_obs_headers:
            label = format_obs_date(obs['date']) if obs['date'] else 'Undated'
            notes_html = f'<p class="obs-notes">{obs["notes"]}</p>' if obs.get('notes') else ''
            images_html += f'    <div class="obs-header"><span class="obs-date">{label}</span>{notes_html}</div>\n'
        for img in obs['images']:
            caption = f'{name} {img["caption_index"]}'
            date_str = f' &middot; {img["date"]}' if img['date'] else ''
            tif_attr = f' data-tif="{img["tif_url"]}"' if img['tif_url'] else ''
            commons_attr = f' data-commons="{img["commons_page"]}"' if img['commons_page'] else ''
            raw_attr = f' data-raw="{img["raw"]}"' if img['raw'] else ''
            xmp_attr = f' data-xmp="{img["xmp"]}"' if img['xmp'] else ''
            images_html += f'''    <figure class="ph"{tif_attr}{commons_attr}{raw_attr}{xmp_attr}>
      <a href="#" download title="{caption}">
        <img src="../{img["jpg"]}" alt="{caption}" loading="lazy"/>
      </a>
      <figcaption>
        <span class="caption-title">{caption}{date_str}</span>
        <span class="caption-filename">{img["camera_filename"]}</span>
      </figcaption>
    </figure>\n'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TMR79M95R4"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-TMR79M95R4');
</script>
<meta charset="utf-8"/>
<title>{name} — Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<meta content="{name}. Public Lands Institute photographic index. CC0 Public Domain." name="description"/>
<meta property="og:title" content="{name} — Public Lands Institute"/>
<meta property="og:description" content="{name}. An ongoing photographic index and open-access archive of American public lands. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/sites/{slug}.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
{og_image_tags}
<link href="https://publiclandsinstitute.net/sites/{slug}.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
{FONT_LINKS}
<style>
{SHARED_CSS}
  .site-header {{ margin-bottom: 28px; }}
  .site-header h1 {{
    font-size: 26px;
    font-weight: 300;
    letter-spacing: -0.01em;
    line-height: 1.2;
    margin-bottom: 4px;
  }}
  .site-header .state {{
    font-size: 11px;
    font-weight: 400;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--muted);
  }}
  .site-layout {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 32px;
  }}
  .site-record {{ align-content: start; }}
  .rec-section {{
    border-top: 1px solid var(--border);
    padding-top: 14px;
    margin-bottom: 18px;
  }}
  .rec-label {{
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
  }}
  .rec-glossary-link {{
    text-transform: none;
    letter-spacing: normal;
    font-weight: 300;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    margin-left: 8px;
  }}
  .rec-glossary-link:hover {{ color: var(--fg); border-bottom-color: var(--fg); }}
  .rec-section p {{
    font-size: 13.5px;
    font-weight: 300;
    line-height: 1.7;
  }}
  .geo-era-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .geo-swatch {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .geo-era-name {{ font-size: 14px; font-weight: 300; }}
  .geo-mya {{ font-size: 11px; font-weight: 300; color: var(--muted); margin-left: auto; letter-spacing: 0.04em; }}
  .geo-bar-wrap {{ position: relative; height: 3px; background: rgba(255,255,255,0.08); margin-bottom: 8px; border-radius: 2px; }}
  .geo-bar-fill {{ position: absolute; right: 0; top: 0; height: 100%; border-radius: 2px; }}
  .geo-prose {{ color: var(--fg); }}
  .photo-pane {{ min-width: 0; }}
  .photo-scroll {{
    display: flex; flex-direction: column; gap: 16px;
    overflow-y: auto; min-height: 0; flex: 1;
    scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.18) transparent;
  }}
  .photo-scroll::-webkit-scrollbar {{ width: 6px; }}
  .photo-scroll::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.18); }}
  .ph {{ background: #1f1f1f; flex-shrink: 0; }}
  .ph a {{ display: block; width: 100%; }}
  .ph img {{
    width: 100%; height: auto; display: block;
    filter: grayscale(100%);
    opacity: 0.92;
    transition: opacity 0.15s;
  }}
  .ph:hover img {{ opacity: 1; }}
  .ph figcaption {{ display: none; }}
  .photo-foot {{
    flex-shrink: 0;
    padding-top: 12px;
    margin-top: 4px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: flex-end;
  }}
  .plb-view-all {{
    font-family: inherit; font-size: 10px; font-weight: 400;
    letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--muted); background: none; border: none;
    cursor: pointer; padding: 0;
  }}
  .plb-view-all:hover {{ color: var(--fg); }}
  .obs-header {{
    padding: 10px 0 4px 0;
  }}
  .obs-header:first-child {{ padding-top: 0; }}
  .obs-date {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--muted);
    display: block;
  }}
  .obs-notes {{
    font-size: 12px;
    font-weight: 300;
    color: var(--fg);
    margin-top: 4px;
    line-height: 1.6;
  }}
  .site-nav {{
    margin-top: 40px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--muted);
    flex-wrap: wrap;
    gap: 8px;
  }}
  @media (min-width: 720px) {{
    .site-layout {{ grid-template-columns: 360px 1fr; gap: 48px; align-items: start; }}
    .photo-pane {{ position: sticky; top: 24px; height: calc(100vh - 48px); display: flex; flex-direction: column; }}
  }}
  @media (min-width: 1148px) {{
    .site-layout {{ grid-template-columns: 7fr 15fr; }}
  }}
  @media (max-width: 719px) {{
    .photo-pane {{ order: -1; display: flex; flex-direction: column; }}
    .photo-scroll {{ max-height: 70vh; }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="../index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="../index.html">Map</a>
    <a href="../photographs.html">Images</a>
    <a href="../archive.html">Archive</a>
    <a href="../about.html">About</a>
    <a href="../support.html">Contribute</a>
  </nav>
</header>
<div class="divider"></div>
<div class="site-header">
  <h1>{name}</h1>
  <div class="state">{state}</div>
</div>
<div class="site-layout">
  <aside class="site-record">
{sections}  </aside>
  <div class="photo-pane">
    <div class="photo-scroll">
{images_html}    </div>
    <div class="photo-foot">
      <button class="plb-view-all">{view_all_label}</button>
    </div>
  </div>
</div>
<nav class="site-nav">
  {nav_prev}
  {nav_next}
</nav>
<footer>
  <span>Public Lands Institute — ongoing project</span>
  <span>CC0 Public Domain</span>
  <span><a href="../prospective.html">Prospective sites</a> · <a href="../support.html">Contribute</a></span>
</footer>
</div>
<script src="../js/lightbox.js"></script>
</body>
</html>'''


# ── photographs.html ───────────────────────────────────────────────────────────

def make_gallery_page(all_sites, photos):
    """Visual feed of every image grouped into per-park sections.
    Sections default to most-recent order; a client-side toggle re-sorts
    alphabetically. Reuses js/lightbox.js via the shared <figure> markup."""
    groups = []
    for site in all_sites:
        slug = site['slug']
        imgs = []
        for img in image_records(slug, photos.get(slug, [])):
            thumb = f'thumbs/{slug}/{img["camera_filename"]}'
            if not os.path.exists(thumb):
                continue
            imgs.append({'img': img, 'thumb': thumb})
        if not imgs:
            continue
        # Newest image first within a park
        imgs.sort(key=lambda e: e['img'].get('date') or '', reverse=True)
        dates = [e['img'].get('date') for e in imgs if e['img'].get('date')]
        recent = max(dates) if dates else ''
        groups.append({'site': site, 'imgs': imgs, 'recent': recent})
    # Default order: most recently photographed park first
    groups.sort(key=lambda g: g['recent'], reverse=True)

    # Same helper as about/support, scoped to the images this feed actually renders
    gallery = site_counts([g['site'] for g in groups],
                          {g['site']['slug']: [{'thumb': e['thumb']} for e in g['imgs']]
                           for g in groups})
    total = gallery['photographs']
    n_sites = gallery['sites']

    sections = ''
    for g in groups:
        site = g['site']
        name, slug = site['name'], site['slug']
        date_label = format_obs_date(g['recent'][:7]) if g['recent'] else ''
        figs = ''
        for e in g['imgs']:
            img = e['img']
            caption = f'{name} {img["caption_index"]}'
            date_str = img['date'] or ''
            meta_caption = caption + (f' · {date_str}' if date_str else '')
            tif_attr = f' data-tif="{img["tif_url"]}"' if img['tif_url'] else ''
            commons_attr = f' data-commons="{img["commons_page"]}"' if img['commons_page'] else ''
            raw_attr = f' data-raw="{img["raw"]}"' if img['raw'] else ''
            xmp_attr = f' data-xmp="{img["xmp"]}"' if img['xmp'] else ''
            figs += f'''      <figure class="feed-fig"{tif_attr}{commons_attr}{raw_attr}{xmp_attr}>
        <a class="feed-link" href="{img['jpg']}" download title="{caption}"><img class="feed-img" src="{e['thumb']}" data-full="{img['jpg']}" alt="{caption}" loading="lazy"/></a>
        <span class="caption-title" style="display:none">{meta_caption}</span>
        <span class="caption-filename" style="display:none">{img['camera_filename']}</span>
      </figure>
'''
        meta_suffix = f' · {date_label}' if date_label else ''
        sections += f'''  <section class="feed-park" data-name="{name.lower()}" data-recent="{g['recent']}">
    <div class="feed-park-head">
      <a class="feed-park-name" href="sites/{slug}.html">{name}</a>
      <span class="feed-park-meta">{site['state']}{meta_suffix}</span>
    </div>
    <div class="feed-grid">
{figs}    </div>
  </section>
'''
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TMR79M95R4"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-TMR79M95R4');
</script>
<meta charset="utf-8"/>
<title>Images — Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<meta content="A visual index of American public lands, grouped by site. CC0 Public Domain." name="description"/>
<meta property="og:title" content="Images — Public Lands Institute"/>
<meta property="og:description" content="A visual index of American public lands, grouped by site. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/photographs.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
<meta property="og:image" content="https://publiclandsinstitute.net/img/cards/site.jpg"/>
<meta property="og:image:width" content="1200"/>
<meta property="og:image:height" content="630"/>
<meta name="twitter:card" content="summary_large_image"/>
<link href="https://publiclandsinstitute.net/photographs.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
{FONT_LINKS}
<style>
{SHARED_CSS}
  .feed-intro {{ font-size: 13px; color: var(--muted); margin-bottom: 14px; max-width: 640px; }}
  .feed-controls {{ display: flex; align-items: center; gap: 8px; margin-bottom: 30px; }}
  .feed-sort-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.14em; color: var(--muted); margin-right: 2px; }}
  .feed-sort-btn {{ background: transparent; border: 1px solid var(--border); color: var(--muted); font-family: inherit; font-size: 11px; letter-spacing: 0.08em; padding: 5px 11px; cursor: pointer; transition: border-color 0.2s, color 0.2s; }}
  .feed-sort-btn:hover {{ color: var(--fg); }}
  .feed-sort-btn.active {{ color: var(--fg); border-color: rgba(255,255,255,0.5); }}
  .feed-park {{ margin-bottom: 36px; }}
  .feed-park-head {{ display: flex; align-items: baseline; gap: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
  .feed-park-name {{ font-size: 14px; font-weight: 400; letter-spacing: 0.02em; color: var(--fg); }}
  .feed-park-name:hover {{ text-decoration: underline; }}
  .feed-park-meta {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); }}
  .feed-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 4px; }}
  .feed-fig {{ background: #1f1f1f; }}
  .feed-link {{ display: block; cursor: zoom-in; }}
  .feed-img {{ width: 100%; aspect-ratio: 3 / 2; object-fit: cover; display: block; filter: grayscale(100%); opacity: 0.9; transition: opacity 0.2s, filter 0.2s; }}
  .feed-link:hover .feed-img {{ opacity: 1; filter: grayscale(0%); }}
  @media (min-width: 720px) {{ .feed-grid {{ grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }} }}
  @media (max-width: 540px) {{ .feed-grid {{ grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 3px; }} }}
</style>
</head>
<body>
<div class="page">
<h1 class="sr-only">Images</h1>
<header>
  <div class="logotype"><a href="index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="index.html">Map</a>
    <a href="photographs.html" class="active">Images</a>
    <a href="archive.html">Archive</a>
    <a href="glossary.html">Glossary</a>
    <a href="about.html">About</a>
    <a href="support.html">Contribute</a>
  </nav>
</header>
<div class="divider"></div>
<p class="feed-intro">{total} images across {n_sites} sites. Click any image to view full resolution and download. CC0 Public Domain.</p>
<div class="feed-controls">
  <span class="feed-sort-label">Sort</span>
  <button class="feed-sort-btn active" data-sort="recent">Most recent</button>
  <button class="feed-sort-btn" data-sort="alpha">A to Z</button>
</div>
<div id="feed-parks">
{sections}</div>
<footer>
  <span>Public Lands Institute — ongoing project</span>
  <span>CC0 Public Domain</span>
  <span><a href="prospective.html">Prospective sites</a> · <a href="support.html">Contribute</a></span>
</footer>
</div>
<script>
(function() {{
  var container = document.getElementById('feed-parks');
  var sections = Array.prototype.slice.call(container.querySelectorAll('.feed-park'));
  var btns = Array.prototype.slice.call(document.querySelectorAll('.feed-sort-btn'));
  function apply(mode) {{
    var sorted = sections.slice().sort(function(a, b) {{
      if (mode === 'alpha') return a.getAttribute('data-name').localeCompare(b.getAttribute('data-name'));
      return (b.getAttribute('data-recent') || '').localeCompare(a.getAttribute('data-recent') || '');
    }});
    sorted.forEach(function(s) {{ container.appendChild(s); }});
  }}
  btns.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      btns.forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      apply(btn.getAttribute('data-sort'));
    }});
  }});
}})();
</script>
<script src="js/lightbox.js"></script>
</body>
</html>'''


# ── archive.html ───────────────────────────────────────────────────────────────

def make_archive_page(all_sites, photos):
    rows = ''
    for site in sorted(all_sites, key=lambda s: s['name'].lower()):
        images = image_records(site['slug'], photos.get(site['slug'], []))
        if not images:
            continue
        _search_key = f'{site["name"]} {site["state"]} {STATE_NAMES.get(site["state"], "")}'.rstrip().lower()
        rows += f'<div class="archive-location" data-name="{_search_key}">\n'
        rows += f'  <h2 class="archive-location-name"><a href="sites/{site["slug"]}.html">{site["name"]} — {site["state"]}</a></h2>\n'
        for img in images:
            caption = f'{site["name"]} {img["caption_index"]}'
            date_str = f' &middot; {img["date"]}' if img['date'] else ''
            rows += f'  <div class="archive-item">\n'
            rows += f'    <span class="archive-caption">{caption}{date_str}</span>\n'
            rows += f'    <span class="archive-filename">{img["camera_filename"]}</span>\n'
            if img['commons_page']:
                rows += f'    <a class="archive-download" href="{img["commons_page"]}" target="_blank" rel="noopener">Commons</a>\n'
            else:
                rows += f'    <span class="archive-download archive-pending">Uploading</span>\n'
            if img['raw']:
                rows += f'    <a class="archive-download" href="{img["raw"]}" download>Download RAW</a>\n'
            else:
                rows += f'    <span class="archive-download" style="visibility:hidden">Download RAW</span>\n'
            if img['xmp']:
                rows += f'    <a class="archive-download" href="{img["xmp"]}" download>XMP</a>\n'
            else:
                rows += f'    <span class="archive-download" style="visibility:hidden">XMP</span>\n'
            rows += f'  </div>\n'
        rows += '</div>\n'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TMR79M95R4"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-TMR79M95R4');
</script>
<meta charset="utf-8"/>
<title>Archive — Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<meta content="Full-resolution TIFFs and RAW files from the Public Lands Institute photographic archive. CC0 Public Domain." name="description"/>
<meta property="og:title" content="Archive — Public Lands Institute"/>
<meta property="og:description" content="Full-resolution TIFFs and RAW files from the Public Lands Institute photographic archive. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/archive.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
<meta property="og:image" content="https://publiclandsinstitute.net/img/cards/site.jpg"/>
<meta property="og:image:width" content="1200"/>
<meta property="og:image:height" content="630"/>
<meta name="twitter:card" content="summary_large_image"/>
<link href="https://publiclandsinstitute.net/archive.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
{FONT_LINKS}
<style>
{SHARED_CSS}
  .archive-intro {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 20px;
    max-width: 640px;
  }}
  .archive-search {{
    width: 100%;
    max-width: 320px;
    box-sizing: border-box;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    color: var(--fg);
    font-family: inherit;
    font-size: 12px;
    font-weight: 300;
    letter-spacing: 0.06em;
    padding: 8px 12px;
    margin-bottom: 28px;
    outline: none;
    transition: border-color 0.2s;
  }}
  .archive-search::placeholder {{ color: var(--muted); letter-spacing: 0.12em; text-transform: uppercase; font-size: 11px; }}
  .archive-search:focus {{ border-color: rgba(255,255,255,0.45); }}
  .archive-noresults {{ color: var(--muted); font-size: 12px; padding: 12px 0; display: none; }}
  .archive-location {{
    border-top: 1px solid var(--border);
    padding: 16px 0 8px 0;
  }}
  .archive-location-name {{
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    margin-bottom: 10px;
  }}
  .archive-item {{
    display: grid;
    grid-template-columns: 1fr max-content max-content max-content max-content;
    gap: 24px;
    align-items: baseline;
    padding: 4px 0;
    font-size: 11px;
    border-top: 1px solid rgba(255,255,255,0.07);
  }}
  .archive-caption {{ color: var(--fg); letter-spacing: 0.04em; }}
  .archive-filename {{
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0.04em;
    font-family: monospace;
  }}
  .archive-download {{
    color: var(--muted);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    white-space: nowrap;
  }}
  .archive-pending {{
    border: 1px solid rgba(200,144,74,0.5);
    padding: 2px 8px;
  }}
  @media (max-width: 540px) {{
    .archive-item {{ grid-template-columns: 1fr max-content max-content max-content; }}
    .archive-filename {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="page">
<h1 class="sr-only">Archive</h1>
<header>
  <div class="logotype"><a href="index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="index.html">Map</a>
    <a href="photographs.html">Images</a>
    <a href="archive.html" class="active">Archive</a>
    <a href="glossary.html">Glossary</a>
    <a href="about.html">About</a>
    <a href="support.html">Contribute</a>
  </nav>
</header>
<div class="divider"></div>
<p class="archive-intro">All photographs are dedicated to the Public Domain under the Creative Commons CC0 license. Full-resolution TIFFs and RAW files are available for download below.</p>
<input id="archive-search" class="archive-search" type="text" placeholder="Filter by site or state" autocomplete="off" spellcheck="false">
<p id="archive-noresults" class="archive-noresults">No sites match your search.</p>
{rows}
<footer>
  <span>Public Lands Institute — ongoing project</span>
  <span>CC0 Public Domain</span>
  <span><a href="prospective.html">Prospective sites</a> · <a href="support.html">Contribute</a></span>
</footer>
</div>
<script>
(function() {{
  var input = document.getElementById('archive-search');
  var locations = Array.prototype.slice.call(document.querySelectorAll('.archive-location'));
  var noResults = document.getElementById('archive-noresults');
  input.addEventListener('input', function() {{
    var q = input.value.trim().toLowerCase();
    var shown = 0;
    locations.forEach(function(loc) {{
      var match = !q || loc.getAttribute('data-name').indexOf(q) !== -1;
      loc.style.display = match ? '' : 'none';
      if (match) shown++;
    }});
    noResults.style.display = shown ? 'none' : 'block';
  }});
}})();
</script>
</body>
</html>'''


# ── about.html (stats sentence only) ──────────────────────────────────────────

STATS_RE = re.compile(
    r'The index currently holds \d[\d,]* sites across \d[\d,]* states, '
    r'documented in \d[\d,]* photographs')


def update_about_stats(all_sites, photos):
    """Rewrite the stats sentence in about.html in place, from site_counts()."""
    c = site_counts(all_sites, photos)
    sentence = (f'The index currently holds {c["sites"]} sites across {c["states"]} states, '
                f'documented in {c["photographs"]} photographs')
    with open('about.html') as f:
        html = f.read()
    new_html, n = STATS_RE.subn(sentence, html)
    if n != 1:
        raise RuntimeError(f'about.html stats sentence: expected 1 match, found {n}')
    if new_html != html:
        with open('about.html', 'w') as f:
            f.write(new_html)
    return new_html != html


# ── support.html (counts line only) ───────────────────────────────────────────

SUPPORT_COUNTS_RE = re.compile(
    r'\d[\d,]* sites, \d[\d,]* states, \d[\d,]* photographs, '
    r'\d+\.\d million acres')


def update_support_counts(all_sites, photos):
    """Rewrite the counts line in support.html in place, from counts_line()."""
    line = counts_line(all_sites, photos)
    with open('support.html') as f:
        html = f.read()
    new_html, n = SUPPORT_COUNTS_RE.subn(line, html)
    if n != 1:
        raise RuntimeError(f'support.html counts line: expected 1 match, found {n}')
    if new_html != html:
        with open('support.html', 'w') as f:
            f.write(new_html)
    return new_html != html


# ── sitemap.xml ────────────────────────────────────────────────────────────────

BASE_URL = 'https://publiclandsinstitute.net'


def make_sitemap(all_sites):
    entries = [
        (f'{BASE_URL}/', 'index.html'),
        (f'{BASE_URL}/photographs.html', 'photographs.html'),
        (f'{BASE_URL}/archive.html', 'archive.html'),
        (f'{BASE_URL}/about.html', 'about.html'),
        (f'{BASE_URL}/glossary.html', 'glossary.html'),
        (f'{BASE_URL}/support.html', 'support.html'),
        (f'{BASE_URL}/prospective.html', 'prospective.html'),
    ]
    entries += [(f'{BASE_URL}/sites/{s["slug"]}.html', f'sites/{s["slug"]}.html')
                for s in all_sites]
    out = '<?xml version="1.0" encoding="UTF-8"?>\n'
    out += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, path in entries:
        lastmod = datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
        out += f'  <url><loc>{url}</loc><lastmod>{lastmod}</lastmod></url>\n'
    out += '</urlset>\n'
    return out


# ── data/sites-map.js + index.html version string ─────────────────────────────

def build_sites_geojson(all_sites, meta):
    features = []
    for site in all_sites:
        slug = site['slug']
        lat = site.get('lat')
        lng = site.get('lng')
        if lat is None or lng is None:
            continue
        m = meta.get(slug, {})
        # primary_nation (dot color): first nation that survives the filter,
        # else first culture, in the canonical spelling used by NATION_COLORS
        kept, _ = site_nations(site, m)
        territory = [cn for cn, _ in kept] + [NATION_CANON.get(c, c) for c in m.get('cultures', [])]
        props = {
            'slug': slug,
            'name': site['name'],
            'state': site['state'],
            'acreage': site.get('acreage', ''),
            'geology': site.get('geological_age', ''),
            'epoch': site.get('epoch', ''),
            'hydrology': site.get('hydrology', ''),
            'native_lands': site.get('native_lands', ''),
            'displacement_tenure': site.get('displacement_tenure', ''),
            'shadow_history': site.get('shadow_history', ''),
            'ecology': site.get('ecology', ''),
            'conservation_status': site.get('conservation_status', ''),
            'endangered_species': site.get('endangered_species', ''),
            'gps': site.get('gps', ''),
            'primary_nation': territory[0] if territory else '',
            'agency_type': m.get('agency_type', ''),
        }
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lng, lat]},
            'properties': props,
        })
    return {'type': 'FeatureCollection', 'features': features}


def make_sites_map_js(all_sites, meta, photos, nations_gj):
    def dump(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))

    sites_gj = build_sites_geojson(all_sites, meta)
    # Distinct-site count per nation/culture (the legend shows and sorts by this)
    nation_sites = defaultdict(set)
    for f in nations_gj['features']:
        nation_sites[f['properties']['nation']].add(f['properties']['slug'])
    nation_counts = {n: len(s) for n, s in nation_sites.items()}
    # NATION_COLORS in first-encounter order; NATION_LIST (nations) and
    # CULTURE_LIST (archaeological cultures) sorted by site count descending
    nation_colors, groups = {}, {}
    for f in nations_gj['features']:
        n = f['properties']['nation']
        nation_colors.setdefault(n, f['properties']['color'])
        groups.setdefault(n, f['properties']['group'])
    by_count = lambda n: (-nation_counts.get(n, 0), n)
    nation_list = sorted((n for n in nation_colors if groups[n] == 'nation'), key=by_count)
    culture_list = sorted((n for n in nation_colors if groups[n] == 'culture'), key=by_count)
    return (f'const SITES={dump(sites_gj)};\n'
            f'const NATIONS_GJ={dump(nations_gj)};\n'
            f'const PHOTOS={dump(photos)};\n'
            f'const NATION_COLORS={dump(nation_colors)};\n'
            f'const NATION_LIST={dump(nation_list)};\n'
            f'const CULTURE_LIST={dump(culture_list)};\n'
            f'const NATION_COUNTS={dump(nation_counts)};\n')


MAPJS_SRC_RE = re.compile(r'src="data/sites-map\.js\?v=[0-9a-f]+"')


def write_sites_map_js(all_sites, meta, photos, nations_gj):
    content = make_sites_map_js(all_sites, meta, photos, nations_gj)
    with open('data/sites-map.js', 'w') as f:
        f.write(content)
    version = hashlib.md5(content.encode()).hexdigest()[:10]
    with open('index.html') as f:
        html = f.read()
    new_html, n = MAPJS_SRC_RE.subn(f'src="data/sites-map.js?v={version}"', html)
    if n != 1:
        raise RuntimeError(f'index.html sites-map.js script tag: expected 1 match, found {n}')
    if new_html != html:
        with open('index.html', 'w') as f:
            f.write(new_html)
    return version


# ── prospective.html + data/suggestions-map.js ────────────────────────────────
# Source: submissions/suggestions.json (private; submissions/ is never deployed).
# Only entries with public true and a status other than declined are published,
# and only the fields in SUGGESTION_PUBLIC_FIELDS leave the private file:
# review notes, sources, and anything from submitters stay behind.

SUGGESTIONS_PATH = 'submissions/suggestions.json'
SUGGESTION_PUBLIC_FIELDS = ['id', 'name', 'state', 'agency', 'agency_type', 'designated',
                            'acreage', 'status', 'times_suggested', 'themes', 'note']
SUGGESTION_STATUS_LABELS = {
    'received': 'Under review',
    'researching': 'Researching',
    'pending': 'Seeking funding',
    'planned': 'Planned for fieldwork',
    'documented': 'Documented',
}


def load_public_suggestions():
    if not os.path.exists(SUGGESTIONS_PATH):
        return []
    with open(SUGGESTIONS_PATH) as f:
        allsug = json.load(f)
    out = []
    for s in allsug:
        if not s.get('public') or s.get('status') not in SUGGESTION_STATUS_LABELS:
            continue
        if s.get('lat') is None or s.get('lng') is None:
            continue
        out.append(s)
    return out


def suggestions_geojson(suggestions):
    features = []
    for s in suggestions:
        props = {k: s.get(k, '') for k in SUGGESTION_PUBLIC_FIELDS}
        props['status_label'] = SUGGESTION_STATUS_LABELS[s['status']]
        features.append({'type': 'Feature',
                         'geometry': {'type': 'Point', 'coordinates': [s['lng'], s['lat']]},
                         'properties': props})
    return {'type': 'FeatureCollection', 'features': features}


SUGMAP_SRC_RE = re.compile(r'src="data/suggestions-map\.js\?v=[0-9a-f]+"')


def write_suggestions_map_js(suggestions):
    gj = suggestions_geojson(suggestions)
    content = ('const SUGGESTIONS=' +
               json.dumps(gj, ensure_ascii=False, separators=(',', ':')) + ';\n')
    with open('data/suggestions-map.js', 'w') as f:
        f.write(content)
    version = hashlib.md5(content.encode()).hexdigest()[:10]
    for page in ('index.html', 'prospective.html'):
        if not os.path.exists(page):
            continue
        with open(page) as f:
            html = f.read()
        new_html, n = SUGMAP_SRC_RE.subn(f'src="data/suggestions-map.js?v={version}"', html)
        if n != 1:
            raise RuntimeError(f'{page} suggestions-map.js script tag: expected 1 match, found {n}')
        if new_html != html:
            with open(page, 'w') as f:
                f.write(new_html)
    return version


def esc(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def format_designated(date_str):
    try:
        d = datetime.date.fromisoformat(date_str)
    except (TypeError, ValueError):
        return ''
    return f'{d.strftime("%B")} {d.day}, {d.year}'


def make_suggested_page(suggestions):
    order = {'documented': 0, 'planned': 1, 'pending': 2, 'researching': 3, 'received': 4}
    rows = sorted(suggestions, key=lambda s: (order[s['status']], s['name']))
    cards = []
    for s in rows:
        meta = [STATE_NAMES.get(s.get('state', ''), s.get('state', ''))]
        if s.get('agency'):
            meta.append(esc(s['agency']))
        facts = []
        if s.get('designated'):
            facts.append(f'Designated {format_designated(s["designated"])}')
        if s.get('origin') != 'grant':
            n = s.get('times_suggested', 1)
            facts.append(f'Suggested {n} time{"s" if n != 1 else ""}')
        themes = ''.join(f'<span class="sg-theme">{esc(t)}</span>' for t in s.get('themes', []))
        cards.append(f'''  <article class="sg-card" id="{esc(s['id'])}" data-lng="{s['lng']}" data-lat="{s['lat']}">
    <div class="sg-head">
      <h2 class="sg-name">{esc(s['name'])}</h2>
      <span class="sg-status sg-{s['status']}">{SUGGESTION_STATUS_LABELS[s['status']]}</span>
    </div>
    <div class="sg-meta">{' · '.join(meta)}</div>
    <div class="sg-facts">{' · '.join(facts)}</div>
    {f'<div class="sg-themes">{themes}</div>' if themes else ''}
    {f'<p class="sg-note">{esc(s["note"])}</p>' if s.get('note') else ''}
    {'<p class="sg-support"><a href="support.html#give">Support this fieldwork</a></p>' if s['status'] == 'pending' else ''}
  </article>''')
    n_total = len(rows)
    n_states = len({s.get('state') for s in rows if s.get('state')})
    intro = (f'{n_total} site{"s" if n_total != 1 else ""} in {n_states} '
             f'state{"s" if n_states != 1 else ""} under consideration for the index, from visitor '
             f'suggestions and project research, each researched before fieldwork.')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TMR79M95R4"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-TMR79M95R4');
</script>
<meta charset="utf-8"/>
<title>Prospective Sites · Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<meta content="Public and protected lands under consideration for the Public Lands Institute index, with research notes and fieldwork status." name="description"/>
<meta property="og:title" content="Prospective Sites · Public Lands Institute"/>
<meta property="og:description" content="Public and protected lands under consideration for the Public Lands Institute index, with research notes and fieldwork status."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/prospective.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
<meta property="og:image" content="https://publiclandsinstitute.net/img/cards/site.jpg"/>
<meta property="og:image:width" content="1200"/>
<meta property="og:image:height" content="630"/>
<meta name="twitter:card" content="summary_large_image"/>
<link href="https://publiclandsinstitute.net/prospective.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
{FONT_LINKS}
<link rel="stylesheet" href="vendor/maplibre-gl-4.7.1/maplibre-gl.css">
<style>
{SHARED_CSS}
  .sg-intro {{ font-size: 13px; color: var(--muted); margin-bottom: 18px; max-width: 680px; line-height: 1.6; }}
  .sg-intro a {{ color: var(--fg); border-bottom: 1px solid var(--border); }}
  .sg-intro a:hover {{ text-decoration: none; border-bottom-color: var(--fg); }}
  .sg-legend {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }}
  .sg-legend span {{ display: inline-flex; align-items: center; gap: 7px; }}
  #sg-map {{ width: 100%; height: 56vh; min-height: 320px; border: 1px solid var(--border); margin-bottom: 28px; background: #1b1b1b; }}
  .sg-list {{ display: grid; grid-template-columns: 1fr; gap: 0 32px; }}
  @media (min-width: 900px) {{ .sg-list {{ grid-template-columns: 1fr 1fr; }} }}
  .sg-card {{ border-top: 1px solid var(--border); padding: 16px 0 22px; scroll-margin-top: 24px; }}
  .sg-card.focus .sg-name {{ text-decoration: underline; }}
  .sg-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }}
  .sg-name {{ font-size: 16px; font-weight: 400; letter-spacing: 0.01em; cursor: pointer; }}
  .sg-status {{ font-size: 10px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted); border: 1px solid var(--border); padding: 3px 8px; white-space: nowrap; }}
  .sg-status.sg-planned, .sg-status.sg-documented {{ color: var(--fg); border-color: var(--fg); }}
  .sg-status.sg-pending {{ color: var(--fg); border-style: dashed; border-color: var(--fg); }}
  .sg-meta, .sg-facts {{ font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }}
  .sg-themes {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px; }}
  .sg-theme {{ font-size: 11px; color: var(--fg); border: 1px solid var(--border); padding: 2px 8px; }}
  .sg-note {{ font-size: 13.5px; line-height: 1.7; margin-top: 10px; max-width: 680px; }}
  .sg-support {{ margin-top: 10px; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; }}
  .sg-support a {{ border-bottom: 1px solid var(--border); }}
  .sg-support a:hover {{ text-decoration: none; border-bottom-color: var(--fg); }}
  .maplibregl-popup-content {{ background: var(--bg); color: var(--fg); font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 300; padding: 8px 12px; border-radius: 0; box-shadow: none; border: 1px solid var(--border); }}
  .maplibregl-popup-tip {{ display: none; }}
  .maplibregl-ctrl-attrib {{ font-size: 9px; opacity: 0.4; }}
</style>
</head>
<body>
<div class="page">
<h1 class="sr-only">Prospective Sites</h1>
<header>
  <div class="logotype"><a href="index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="index.html">Map</a>
    <a href="photographs.html">Images</a>
    <a href="archive.html">Archive</a>
    <a href="glossary.html">Glossary</a>
    <a href="about.html">About</a>
    <a href="support.html">Contribute</a>
  </nav>
</header>
<div class="divider"></div>
<p class="sg-intro">{intro} Know a place that belongs here? <a href="support.html#suggest">Suggest a site</a>.</p>
<div class="sg-legend" aria-hidden="true"><span><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="none" stroke="#e8e8e8" stroke-width="1.5"/></svg>Researching</span><span><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="none" stroke="#e8e8e8" stroke-width="1.5"/><circle cx="7" cy="7" r="1.8" fill="#e8e8e8"/></svg>Seeking funding</span><span><svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="none" stroke="#e8e8e8" stroke-width="3"/></svg>Planned for fieldwork</span><span><svg width="14" height="14"><circle cx="7" cy="7" r="3.5" fill="#8c8c8c" fill-opacity="0.7"/></svg>Documented site</span></div>
<div id="sg-map" role="region" aria-label="Map of prospective sites"></div>
<div class="sg-list">
{chr(10).join(cards)}
</div>
<footer>
  <span>Public Lands Institute · ongoing project</span>
  <span>CC0 Public Domain</span>
  <span><a href="prospective.html">Prospective sites</a> · <a href="support.html">Contribute</a></span>
</footer>
</div>
<script src="vendor/maplibre-gl-4.7.1/maplibre-gl.js"></script>
<script src="data/sites-map.js?v=0"></script>
<script src="data/suggestions-map.js?v=0000000000"></script>
<script>
(function () {{
  var feats = SUGGESTIONS.features;
  if (!feats.length) {{ document.getElementById('sg-map').hidden = true; return; }}
  var lngs = feats.map(function (f) {{ return f.geometry.coordinates[0]; }});
  var lats = feats.map(function (f) {{ return f.geometry.coordinates[1]; }});
  var narrow = window.innerWidth < 640;
  var map = new maplibregl.Map({{
    container: 'sg-map',
    style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
    bounds: [[Math.min.apply(null, lngs), Math.min.apply(null, lats)], [Math.max.apply(null, lngs), Math.max.apply(null, lats)]],
    fitBoundsOptions: {{ padding: narrow ? 40 : 80, maxZoom: 7 }},
    minZoom: 2, maxZoom: 14, cooperativeGestures: true
  }});
  map.addControl(new maplibregl.NavigationControl({{ showCompass: false }}), 'top-right');
  map.on('load', function () {{
    map.addSource('sites', {{ type: 'geojson', data: SITES }});
    map.addSource('suggestions', {{ type: 'geojson', data: SUGGESTIONS }});
    map.addLayer({{ id: 'sites-dot', type: 'circle', source: 'sites',
      paint: {{ 'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 10, 5],
               'circle-color': '#8c8c8c', 'circle-opacity': 0.7 }} }});
    map.addLayer({{ id: 'sg-hit', type: 'circle', source: 'suggestions',
      paint: {{ 'circle-radius': 16, 'circle-opacity': 0 }} }});
    map.addLayer({{ id: 'sg-ring', type: 'circle', source: 'suggestions',
      paint: {{ 'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 6, 10, 9],
               'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#e8e8e8',
               'circle-stroke-width': ['match', ['get', 'status'], 'planned', 3, 1.5] }} }});
    map.addLayer({{ id: 'sg-core', type: 'circle', source: 'suggestions',
      filter: ['==', ['get', 'status'], 'pending'],
      paint: {{ 'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 1.8, 10, 2.8],
               'circle-color': '#e8e8e8' }} }});
    var popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12 }});
    function label(p) {{ return '<span style="letter-spacing:.07em">' + p.name + '</span><br><span style="opacity:.6;font-size:10px;letter-spacing:.14em;text-transform:uppercase">' + p.status_label + '</span>'; }}
    map.on('mouseenter', 'sg-hit', function (e) {{
      map.getCanvas().style.cursor = 'pointer';
      popup.setLngLat(e.features[0].geometry.coordinates).setHTML(label(e.features[0].properties)).addTo(map);
    }});
    map.on('mouseleave', 'sg-hit', function () {{ map.getCanvas().style.cursor = ''; popup.remove(); }});
    map.on('click', 'sg-hit', function (e) {{ focus(e.features[0].properties.id, false); }});
    function focus(id, fly) {{
      document.querySelectorAll('.sg-card.focus').forEach(function (c) {{ c.classList.remove('focus'); }});
      var card = document.getElementById(id);
      if (!card) return;
      card.classList.add('focus');
      if (fly) {{
        map.flyTo({{ center: [+card.dataset.lng, +card.dataset.lat], zoom: 7, duration: 900 }});
        document.getElementById('sg-map').scrollIntoView({{ behavior: 'smooth' }});
      }} else {{
        card.scrollIntoView({{ behavior: 'smooth' }});
      }}
    }}
    document.querySelectorAll('.sg-name').forEach(function (n) {{
      n.addEventListener('click', function () {{ focus(n.closest('.sg-card').id, true); }});
    }});
    if (location.hash) focus(location.hash.slice(1), true);
  }});
}})();
</script>
</body>
</html>'''


# ── Main ───────────────────────────────────────────────────────────────────────

ALL_TARGETS = ['sites', 'archive', 'photographs', 'about', 'support', 'mapjs',
               'prospective', 'sitemap']


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    validate = '--no-validate' not in argv
    targets = args or ALL_TARGETS

    sites, meta, photos, nations_gj = load_data()

    if 'sites' in targets:
        os.makedirs('sites', exist_ok=True)
        for site in sites:
            with open(f'sites/{site["slug"]}.html', 'w') as f:
                f.write(make_site_page(site, sites, photos))
        print(f'sites/ ({len(sites)} pages)')
    if 'archive' in targets:
        with open('archive.html', 'w') as f:
            f.write(make_archive_page(sites, photos))
        print('archive.html')
    if 'photographs' in targets:
        with open('photographs.html', 'w') as f:
            f.write(make_gallery_page(sites, photos))
        print('photographs.html')
    if 'about' in targets:
        changed = update_about_stats(sites, photos)
        print(f'about.html stats sentence{"" if changed else " (unchanged)"}')
    if 'support' in targets:
        changed = update_support_counts(sites, photos)
        print(f'support.html counts line{"" if changed else " (unchanged)"}')
    if 'mapjs' in targets:
        with open('data/nations.geojson', 'w') as f:
            json.dump(nations_gj, f, ensure_ascii=False, indent=2)
            f.write('\n')
        version = write_sites_map_js(sites, meta, photos, nations_gj)
        print(f'data/sites-map.js (v={version})')
    if 'prospective' in targets:
        suggestions = load_public_suggestions()
        page = make_suggested_page(suggestions)
        with open('data/sites-map.js') as f:
            sites_v = hashlib.md5(f.read().encode()).hexdigest()[:10]
        page = MAPJS_SRC_RE.sub(f'src="data/sites-map.js?v={sites_v}"', page)
        with open('prospective.html', 'w') as f:
            f.write(page)
        version = write_suggestions_map_js(suggestions)
        print(f'prospective.html + data/suggestions-map.js ({len(suggestions)} public, v={version})')
    if 'sitemap' in targets:
        # Last so lastmod reflects the files written above
        with open('sitemap.xml', 'w') as f:
            f.write(make_sitemap(sites))
        print('sitemap.xml')

    if validate:
        sys.stdout.flush()
        result = subprocess.run([sys.executable, 'tools/validate_pli.py'])
        if result.returncode != 0:
            print('build.py: validation failed', file=sys.stderr)
            sys.exit(result.returncode)


if __name__ == '__main__':
    main(sys.argv[1:])
