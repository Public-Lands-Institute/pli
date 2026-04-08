#!/usr/bin/env python3
"""
Public Lands Institute — site page generator
Run from the root of the PLI site folder:
    python3 generate_sites.py

Reads sites.json for location metadata.
Scans img/jpg/<slug>/ for images — no filenames needed in the JSON.
Writes one HTML file per location into sites/
Also writes archive.html — the plain-text download index.

Add new images by dropping them into the location's image folder and re-running.
"""

import json, os, glob, time, urllib.request, urllib.parse
from dotenv import load_dotenv
load_dotenv()
from PIL import Image
from PIL.ExifTags import TAGS

with open('sites.json', 'r') as f:
    sites = json.load(f)

# ── iNaturalist data ───────────────────────────────────────────────────────────

INAT_CACHE_FILE = 'inaturalist_cache.json'
INAT_CACHE = {}
if os.path.exists(INAT_CACHE_FILE):
    with open(INAT_CACHE_FILE, 'r') as f:
        INAT_CACHE = json.load(f)

INAT_TAXA = [
    ('Plantae',    'Plants'),
    ('Aves',       'Birds'),
    ('Insecta',    'Insects'),
    ('Mammalia',   'Mammals'),
    ('Fungi',      'Fungi'),
    ('Reptilia',   'Reptiles'),
    ('Amphibia',   'Amphibians'),
    ('Arachnida',  'Arachnids'),
]

def inat_get(endpoint, params):
    """Fetch from iNat API v1 with rate limiting. Returns parsed JSON or None."""
    url = f'https://api.inaturalist.org/v1/{endpoint}?' + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'PublicLandsInstitute/1.0 (publiclandsinstitute.net)'
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        time.sleep(0.6)  # respect API rate limits
        return data
    except Exception as e:
        print(f'    iNat API error ({endpoint}): {e}')
        return None

def fetch_inaturalist(slug, lat, lng, radius_km=5):
    """Fetch iNat data for a site. Uses cache; pass force=True to refresh."""
    cache_key = f'{slug}:{radius_km}'
    if cache_key in INAT_CACHE:
        return INAT_CACHE[cache_key]

    print(f'    Fetching iNaturalist data for {slug} (radius {radius_km}km)...')
    base_params = {
        'lat': lat, 'lng': lng, 'radius': radius_km,
        'quality_grade': 'research'
    }

    result = {
        'total_observations': 0,
        'total_species': 0,
        'taxa_counts': [],
        'top_species': [],
    }

    # 1. Total observation count
    obs_data = inat_get('observations', {**base_params, 'per_page': 0})
    if obs_data:
        result['total_observations'] = obs_data.get('total_results', 0)

    # 2. Total species count + top 5
    sp_data = inat_get('observations/species_counts', {**base_params, 'per_page': 10})
    if sp_data:
        result['total_species'] = sp_data.get('total_results', 0)
        for item in sp_data.get('results', [])[:5]:
            taxon = item.get('taxon', {})
            name = taxon.get('preferred_common_name') or taxon.get('name', '')
            sci  = taxon.get('name', '')
            count = item.get('count', 0)
            result['top_species'].append({
                'name': name,
                'scientific': sci,
                'count': count,
                'id': taxon.get('id')
            })

    # 3. Taxa breakdown
    for iconic_taxon, label in INAT_TAXA:
        taxa_data = inat_get('observations/species_counts', {
            **base_params,
            'iconic_taxa[]': iconic_taxon,
            'per_page': 0
        })
        if taxa_data:
            count = taxa_data.get('total_results', 0)
            if count > 0:
                result['taxa_counts'].append({'label': label, 'count': count})

    INAT_CACHE[cache_key] = result
    with open(INAT_CACHE_FILE, 'w') as f:
        json.dump(INAT_CACHE, f, indent=2)

    return result

def format_inaturalist_html(inat, for_index=False):
    """Render iNaturalist data as dt/dd rows for the site-data dl."""
    if not inat or inat.get('total_observations', 0) == 0:
        return ''

    rows = ''

    # Taxa breakdown
    if inat.get('taxa_counts'):
        parts = ', '.join(f'{t["count"]:,} {t["label"].lower()}' for t in inat['taxa_counts'])
        rows += f'      <dt>Taxa</dt><dd>{parts}</dd>\n'

    # Top species
    if inat.get('top_species') and not for_index:
        species_parts = []
        for s in inat['top_species']:
            name = s['name'] or s['scientific']
            sci  = s['scientific']
            species_parts.append(f'{name} <span class="inat-sci">({sci})</span>')
        rows += f'      <dt>Most observed</dt><dd class="inat-species">{"<br>".join(species_parts)}</dd>\n'

    return rows

# ── native-land.ca data ────────────────────────────────────────────────────────

NATIVELAND_CACHE_FILE = 'nativeland_cache.json'
NATIVELAND_CACHE = {}
if os.path.exists(NATIVELAND_CACHE_FILE):
    with open(NATIVELAND_CACHE_FILE, 'r') as f:
        NATIVELAND_CACHE = json.load(f)

def fetch_nativeland(slug, lat, lng):
    """Fetch indigenous territory names from native-land.ca. Uses cache."""
    if slug in NATIVELAND_CACHE:
        return NATIVELAND_CACHE[slug]

    api_key = os.environ.get('NATIVELAND_API_KEY', '')
    if not api_key:
        return []

    print(f'    Fetching native-land.ca data for {slug}...')
    url = f'https://native-land.ca/api/index.php?maps=territories&position={lat},{lng}&key={api_key}'
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'PublicLandsInstitute/1.0 (publiclandsinstitute.net)'
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        time.sleep(0.6)
    except Exception as e:
        print(f'    native-land.ca API error: {e}')
        return []

    names = [f['properties']['Name'] for f in data if f.get('properties', {}).get('Name')]

    NATIVELAND_CACHE[slug] = names
    with open(NATIVELAND_CACHE_FILE, 'w') as f:
        json.dump(NATIVELAND_CACHE, f, indent=2)

    return names

SITES_META_FILE = 'sites_meta.json'
SITES_META = {}
if os.path.exists(SITES_META_FILE):
    with open(SITES_META_FILE, 'r') as f:
        SITES_META = json.load(f)

# Populate native_lands_api for any sites that don't have it yet
sites_updated = False
for site in sites:
    if 'native_lands_api' not in site and site.get('lat') and site.get('lng'):
        names = fetch_nativeland(site['slug'], site['lat'], site['lng'])
        if names is not None:
            site['native_lands_api'] = names
            sites_updated = True

if sites_updated:
    with open('sites.json', 'w') as f:
        json.dump(sites, f, indent=2)

os.makedirs('sites', exist_ok=True)

FIELDS = [
    ('geological_age',      'Geological age'),
    ('epoch',               'Epoch'),
    ('native_lands',        'Native lands'),
    ('displacement_tenure', 'Displacement & Tenure'),
    ('shadow_history',      'Shadow History'),
    ('ecology',             'Ecology'),
    ('hydrology',           'Hydrology'),
    ('acreage',             'Acreage'),
    ('gps',                 'GPS'),
]

ROMAN = ['I','II','III','IV','V','VI','VII','VIII','IX','X',
         'XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX',
         'XXI','XXII','XXIII','XXIV','XXV','XXVI','XXVII','XXVIII','XXIX','XXX',
         'XXXI','XXXII','XXXIII','XXXIV','XXXV','XXXVI','XXXVII','XXXVIII','XXXIX','XL',
         'XLI','XLII','XLIII','XLIV','XLV','XLVI','XLVII','XLVIII','XLIX','L']

def get_exif_date(jpg_path):
    """Return date string from EXIF DateTimeOriginal, or empty string if unavailable."""
    try:
        img = Image.open(jpg_path)
        exif = img._getexif()
        if not exif:
            return ''
        for tag_id, val in exif.items():
            if TAGS.get(tag_id) == 'DateTimeOriginal':
                # Format: '2024:09:14 07:23:45' -> '2024-09-14'
                return val[:10].replace(':', '-')
    except Exception:
        pass
    return ''

import datetime as _dt

def format_obs_date(date_str):
    """Format 'YYYY-MM' as 'January 2026', or return as-is."""
    if not date_str or len(date_str) < 7:
        return date_str or ''
    try:
        dt = _dt.datetime.strptime(date_str[:7], '%Y-%m')
        return dt.strftime('%B %Y')
    except ValueError:
        return date_str

def _make_image_entry(slug, filename, caption_idx):
    jpg_path = os.path.join('img', 'jpg', slug, filename).replace('\\', '/')
    stem = os.path.splitext(filename)[0]
    tif_path = os.path.join('img', 'full', slug, stem + '.tif').replace('\\', '/')
    raw_path = None
    for raw_ext in ('.RAF', '.NEF'):
        candidate = os.path.join('img', 'RAW', stem + raw_ext)
        if os.path.exists(candidate):
            raw_path = candidate.replace('\\', '/')
            break
    return {
        'jpg': jpg_path,
        'tif': tif_path,
        'raw': raw_path,
        'camera_filename': filename,
        'caption_index': ROMAN[caption_idx] if caption_idx < len(ROMAN) else str(caption_idx + 1),
        'date': get_exif_date(jpg_path),
    }

def get_observations_for_site(site):
    """
    Returns [{date, notes, images}] sorted chronologically.
    If site has an 'observations' key, uses those (explicit image_list per visit).
    Otherwise scans img/jpg/<slug>/ and groups images by EXIF month (YYYY-MM).
    Roman numeral caption indices are assigned globally across all observations.
    """
    slug = site['slug']

    if 'observations' in site:
        result = []
        caption_counter = 0
        for obs in site['observations']:
            images = []
            for filename in obs.get('image_list', []):
                entry = _make_image_entry(slug, filename, caption_counter)
                images.append(entry)
                caption_counter += 1
            result.append({'date': obs.get('date', ''), 'notes': obs.get('notes', ''), 'images': images})
        return result

    # Fallback: scan folder, group by EXIF month
    jpg_dir = os.path.join('img', 'jpg', slug)
    if not os.path.isdir(jpg_dir):
        return []
    files = []
    for ext in ('*.jpg', '*.jpeg', '*.JPG', '*.JPEG'):
        files.extend(glob.glob(os.path.join(jpg_dir, ext)))
    files = sorted(set(files))
    if not files:
        return []

    # Build raw image list with propagated EXIF dates
    raw = []
    last_date = ''
    for jpg_path in files:
        filename = os.path.basename(jpg_path)
        date = get_exif_date(jpg_path)
        if not date:
            date = last_date
        else:
            last_date = date
        raw.append((filename, date))

    # Group by YYYY-MM
    from collections import defaultdict
    groups = defaultdict(list)
    for filename, date in raw:
        key = date[:7] if date and len(date) >= 7 else ''
        groups[key].append(filename)

    sorted_keys = sorted(k for k in groups if k) + [k for k in groups if not k]

    result = []
    caption_counter = 0
    for key in sorted_keys:
        images = []
        for filename in groups[key]:
            entry = _make_image_entry(slug, filename, caption_counter)
            images.append(entry)
            caption_counter += 1
        result.append({'date': key, 'notes': '', 'images': images})
    return result

def get_all_images_for_site(site):
    """Flat list of all images across observations. Used by archive and index pages."""
    return [img for obs in get_observations_for_site(site) for img in obs['images']]

SHARED_CSS = '''  :root {
    --bg: #f5f5f5;
    --fg: #111111;
    --muted: #777777;
    --border: #dddddd;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--fg);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", sans-serif;
    line-height: 1.5;
    letter-spacing: 0.01em;
  }
  a { color: inherit; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .page {
    max-width: 1120px;
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
  }'''

def make_site_page(site, all_sites):
    slug  = site['slug']
    name  = site['name']
    state = site['state']
    observations = get_observations_for_site(site)

    idx       = next(i for i, s in enumerate(all_sites) if s['slug'] == slug)
    prev_site = all_sites[idx - 1] if idx > 0 else None
    next_site = all_sites[idx + 1] if idx < len(all_sites) - 1 else None

    nav_prev = f'<a href="{prev_site["slug"]}.html">\u2190 {prev_site["name"]}</a>' if prev_site else '<span></span>'
    nav_next = f'<a href="{next_site["slug"]}.html">{next_site["name"]} \u2192</a>' if next_site else '<span></span>'

    # Fetch iNaturalist data
    lat = site.get('lat')
    lng = site.get('lng')
    radius = site.get('inat_radius_km', 5)
    inat = fetch_inaturalist(slug, lat, lng, radius) if lat and lng else None

    # Build fields: geological fields, then iNat section, then remaining fields
    GEO_KEYS = {'geological_age', 'epoch'}
    REMAINING_KEYS = {'native_lands', 'displacement_tenure', 'ecology', 'hydrology', 'acreage', 'gps', 'shadow_history'}

    fields_html = ''
    for key, label in FIELDS:
        if key in GEO_KEYS:
            val = site.get(key, '')
            if val:
                fields_html += f'      <dt>{label}</dt><dd>{val}</dd>\n'

    if inat and inat.get('total_observations', 0) > 0:
        fields_html += format_inaturalist_html(inat, for_index=False)

    for key, label in FIELDS:
        if key in REMAINING_KEYS:
            val = site.get(key, '')
            if val:
                fields_html += f'      <dt>{label}</dt><dd>{val}</dd>\n'

    show_obs_headers = len(observations) > 1 or any(obs.get('notes') for obs in observations)
    images_html = ''
    for obs in observations:
        if show_obs_headers:
            label = format_obs_date(obs['date']) if obs['date'] else 'Undated'
            notes_html = f'\n      <p class="obs-notes">{obs["notes"]}</p>' if obs.get('notes') else ''
            images_html += f'    <div class="obs-header">\n      <span class="obs-date">{label}</span>{notes_html}\n    </div>\n'
        for img in obs['images']:
            caption = f'{name} {img["caption_index"]}'
            date_str = f' &middot; {img["date"]}' if img['date'] else ''
            images_html += f'''    <figure class="site-figure">
      <a href="../{img["tif"]}" download title="Download {img["camera_filename"]}">
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
<meta charset="utf-8"/>
<title>{name} \u2014 Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<link href="https://publiclandsinstitute.net/sites/{slug}.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<style>
{SHARED_CSS}
  .site-header {{ margin-bottom: 24px; }}
  .site-header h1 {{
    font-size: 20px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    margin-bottom: 2px;
  }}
  .site-header .state {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--muted);
  }}
  .site-layout {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 32px;
  }}
  .site-data {{
    display: grid;
    grid-template-columns: 148px 1fr;
    font-size: 11px;
    line-height: 1.55;
    border-top: 1px solid var(--border);
    padding-top: 8px;
    align-items: baseline;
    align-content: start;
  }}
  .site-data dt {{
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 10px;
    padding: 4px 0;
  }}
  .site-data dd {{
    color: var(--fg);
    padding: 4px 0 4px 12px;
    margin: 0;
  }}
  .site-images {{ display: flex; flex-direction: column; gap: 14px; }}
  .site-figure {{ border: 1px solid var(--border); background: #e1e1e1; }}
  .site-figure img {{ width: 100%; height: auto; display: block; filter: grayscale(100%); }}
  .site-figure figcaption {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--muted);
    padding: 6px 8px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }}
  .caption-filename {{
    color: var(--muted);
    font-size: 9px;
    letter-spacing: 0.08em;
    flex-shrink: 0;
    font-family: monospace;
  }}
  .inat-section-label {{
    color: var(--fg) !important;
    font-weight: 500;
    padding-top: 12px !important;
    border-top: 1px solid var(--border);
    margin-top: 4px;
  }}
  .inat-section-spacer {{
    padding-top: 12px !important;
    border-top: 1px solid var(--border);
    margin-top: 4px;
  }}
  .inat-species {{
    line-height: 1.8;
  }}
  .inat-sci {{
    color: var(--muted);
    font-style: italic;
  }}
  .obs-header {{
    border-top: 1px solid var(--border);
    padding: 10px 0 4px 0;
    margin-top: 6px;
  }}
  .obs-header:first-child {{
    border-top: none;
    padding-top: 0;
    margin-top: 0;
  }}
  .obs-date {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--muted);
    display: block;
  }}
  .obs-notes {{
    font-size: 11px;
    color: var(--fg);
    margin-top: 4px;
    line-height: 1.5;
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
    .site-layout {{ grid-template-columns: 300px 1fr; gap: 48px; align-items: start; }}
    .site-data {{ position: sticky; top: 24px; }}
  }}
  @media (max-width: 480px) {{
    .site-data {{ grid-template-columns: 110px 1fr; }}
    .site-images {{ order: -1; }}
    .site-data {{ order: 0; }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="../index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="../index.html">Index</a>
    <a href="../archive.html">Archive</a>
  </nav>
</header>
<div class="divider"></div>
<div class="site-header">
  <h1>{name}</h1>
  <div class="state">{state}</div>
</div>
<div class="site-layout">
  <aside>
    <dl class="site-data">
{fields_html}    </dl>
  </aside>
  <div class="site-images">
{images_html}  </div>
</div>
<nav class="site-nav">
  {nav_prev}
  {nav_next}
</nav>
<footer>
  <span>Public Lands Institute \u2014 ongoing project</span>
  <span>CC0 Public Domain</span>
</footer>
</div>
<script src="../js/lightbox.js"></script>
</body>
</html>'''


def make_archive_page(all_sites):
    rows = ''
    for site in all_sites:
        images = get_all_images_for_site(site)
        if not images:
            continue
        rows += f'<div class="archive-location">\n'
        rows += f'  <h2 class="archive-location-name"><a href="sites/{site["slug"]}.html">{site["name"]} \u2014 {site["state"]}</a></h2>\n'
        for img in images:
            caption = f'{site["name"]} {img["caption_index"]}'
            date_str = f' &middot; {img["date"]}' if img['date'] else ''
            rows += f'  <div class="archive-item">\n'
            rows += f'    <span class="archive-caption">{caption}{date_str}</span>\n'
            rows += f'    <span class="archive-filename">{img["camera_filename"]}</span>\n'
            rows += f'    <a class="archive-download" href="{img["tif"]}" download>Download TIFF</a>\n'
            if img['raw']:
                rows += f'    <a class="archive-download" href="{img["raw"]}" download>Download RAW</a>\n'
            else:
                rows += f'    <span class="archive-download" style="visibility:hidden">Download RAW</span>\n'
            rows += f'  </div>\n'
        rows += '</div>\n'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Archive \u2014 Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<link href="https://publiclandsinstitute.net/archive.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<style>
{SHARED_CSS}
  .archive-intro {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 32px;
    max-width: 520px;
  }}
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
    grid-template-columns: 1fr max-content max-content max-content;
    gap: 24px;
    align-items: baseline;
    padding: 4px 0;
    font-size: 11px;
    border-top: 1px solid #eeeeee;
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
  @media (max-width: 540px) {{
    .archive-item {{ grid-template-columns: 1fr max-content max-content; }}
    .archive-filename {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="index.html">Index</a>
  </nav>
</header>
<div class="divider"></div>
<p class="archive-intro">All photographs are dedicated to the Public Domain under the Creative Commons CC0 license. Full-resolution TIFFs and RAW files are available for download below.</p>
{rows}
<footer>
  <span>Public Lands Institute \u2014 ongoing project</span>
  <span>CC0 Public Domain</span>
</footer>
</div>
</body>
</html>'''


# ── Sites index page builder (sites.html) ─────────────────────────────────────

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

GEOLOGY_PERIODS = [
    'Hadean', 'Archean', 'Proterozoic', 'Cambrian', 'Ordovician',
    'Silurian', 'Devonian', 'Mississippian', 'Pennsylvanian',
    'Permian', 'Triassic', 'Jurassic', 'Cretaceous',
    'Paleogene', 'Neogene', 'Holocene', 'Pleistocene',
    'Pliocene', 'Miocene', 'Oligocene', 'Eocene', 'Paleocene', 'Quaternary',
]

SITES_INDEX_CSS = '''  @import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&display=swap');

  *, *::before, *::after {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  :root {
    --black: #111;
    --white: #fff;
    --gray-100: #f5f5f5;
    --gray-200: #e5e5e5;
    --gray-300: #d4d4d4;
    --gray-400: #a3a3a3;
    --gray-500: #737373;
    --gray-600: #525252;
    --font-serif: 'EB Garamond', 'Georgia', serif;
    --font-mono: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Mono', monospace;
  }

  html {
    font-size: 16px;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    font-family: var(--font-serif);
    color: var(--black);
    background: var(--white);
    line-height: 1.6;
  }

  a { color: var(--black); text-decoration: none; }
  a:hover { text-decoration: underline; }

  .header {
    padding: 3rem 2rem 1.5rem;
    max-width: 1200px;
    margin: 0 auto;
  }

  .header h1 {
    font-family: var(--font-serif);
    font-size: 1.5rem;
    font-weight: 400;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
  }

  .header h1 a { text-decoration: none; }

  .header nav {
    font-family: var(--font-serif);
    font-size: 0.875rem;
    color: var(--gray-500);
    margin-top: 0.5rem;
  }

  .header nav a {
    color: var(--gray-500);
    margin-right: 1.5rem;
  }

  .header nav a:hover { color: var(--black); }
  .header nav a.active { color: var(--black); }

  .filters {
    padding: 1.5rem 2rem;
    max-width: 1200px;
    margin: 0 auto;
    border-top: 1px solid var(--gray-200);
    border-bottom: 1px solid var(--gray-200);
  }

  .filter-row {
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
    align-items: flex-start;
  }

  .filter-group { flex: 1; min-width: 200px; }

  .filter-label {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--gray-500);
    margin-bottom: 0.5rem;
    display: block;
  }

  .filter-select {
    width: 100%;
    font-family: var(--font-serif);
    font-size: 0.9375rem;
    padding: 0.4rem 0;
    border: none;
    border-bottom: 1px solid var(--gray-300);
    background: transparent;
    color: var(--black);
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    border-radius: 0;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23737373'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0 center;
    padding-right: 1.25rem;
  }

  .filter-select:focus { outline: none; border-bottom-color: var(--black); }

  .results-bar {
    padding: 1rem 2rem;
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .results-count {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--gray-500);
    letter-spacing: 0.04em;
  }

  .clear-filters {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--gray-400);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    display: none;
  }

  .clear-filters:hover { color: var(--black); }
  .clear-filters.visible { display: block; }

  .index-table {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 2rem 4rem;
  }

  table { width: 100%; border-collapse: collapse; }

  thead th {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    font-weight: 400;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--gray-500);
    text-align: left;
    padding: 0.75rem 1rem 0.75rem 0;
    border-bottom: 1px solid var(--gray-300);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }

  thead th:hover { color: var(--black); }

  thead th .sort-indicator {
    display: inline-block;
    margin-left: 0.25rem;
    opacity: 0;
    transition: opacity 0.15s;
  }

  thead th:hover .sort-indicator,
  thead th.sorted .sort-indicator { opacity: 1; }

  tbody tr {
    border-bottom: 1px solid var(--gray-100);
    transition: background 0.1s;
  }

  tbody tr:hover { background: var(--gray-100); }

  tbody td {
    font-family: var(--font-serif);
    font-size: 0.9375rem;
    padding: 0.75rem 1rem 0.75rem 0;
    vertical-align: top;
  }

  td.site-name { font-weight: 500; min-width: 220px; }

  td.site-name a { border-bottom: 1px solid transparent; }

  td.site-name a:hover {
    text-decoration: none;
    border-bottom-color: var(--black);
  }

  td.state {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    letter-spacing: 0.02em;
    color: var(--gray-600);
    white-space: nowrap;
  }

  td.agency { font-size: 0.875rem; color: var(--gray-600); }
  td.geology { font-size: 0.875rem; color: var(--gray-600); }

  td.acreage {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    color: var(--gray-600);
    text-align: right;
    white-space: nowrap;
  }

  td.native-lands {
    font-size: 0.875rem;
    color: var(--gray-600);
    max-width: 200px;
  }

  .empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--gray-400);
    font-style: italic;
    font-size: 0.9375rem;
    display: none;
  }

  .footer {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
    border-top: 1px solid var(--gray-200);
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    color: var(--gray-400);
    letter-spacing: 0.04em;
  }

  @media (max-width: 900px) {
    .filter-group { min-width: 150px; }
    td.native-lands, th.native-lands-col { display: none; }
  }

  @media (max-width: 600px) {
    .header { padding: 2rem 1.25rem 1rem; }
    .filters { padding: 1.25rem; }
    .filter-row { gap: 1rem; }
    .filter-group { min-width: 100%; }
    .results-bar { padding: 0.75rem 1.25rem; }
    .index-table { padding: 0 1.25rem 3rem; overflow-x: auto; }
    table { min-width: 600px; }
    .footer { padding: 1.5rem 1.25rem; }
  }'''


def make_sites_index_page(all_sites, meta):
    import re as _re

    def geology_period(epoch):
        for p in GEOLOGY_PERIODS:
            if p.lower() in epoch.lower():
                return p
        return epoch.split(';')[0].split(',')[0].strip()

    def acreage_int(s):
        m = _re.search(r'[\d,]+', str(s))
        return int(m.group().replace(',', '')) if m else 0

    js_sites = []
    for site in all_sites:
        slug = site['slug']
        m = meta.get(slug, {})
        js_sites.append({
            'name': site['name'],
            'state': STATE_NAMES.get(site['state'], site['state']),
            'stateAbbr': site['state'],
            'agency': m.get('agency', ''),
            'agencyType': m.get('agency_type', ''),
            'geology': geology_period(site.get('epoch', '')),
            'geologyDetail': site.get('geological_age', ''),
            'acreage': acreage_int(site.get('acreage', '0')),
            'territory': m.get('territory', []),
            'url': f'https://publiclandsinstitute.net/sites/{slug}.html',
        })

    js_array = json.dumps(js_sites, indent=2, ensure_ascii=False)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Public Lands Institute \u2014 Index</title>
<style>
{SITES_INDEX_CSS}
</style>
</head>
<body>

<div class="header">
  <h1><a href="https://publiclandsinstitute.net/">Public Lands Institute</a></h1>
  <nav>
    <a href="https://publiclandsinstitute.net/">Sites</a>
    <a href="https://publiclandsinstitute.net/archive.html">Archive</a>
    <a href="#" class="active">Index</a>
  </nav>
</div>

<div class="filters">
  <div class="filter-row">
    <div class="filter-group">
      <span class="filter-label">State</span>
      <select class="filter-select" id="filter-state">
        <option value="">All states</option>
      </select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Managing agency</span>
      <select class="filter-select" id="filter-agency">
        <option value="">All agencies</option>
      </select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Geological period</span>
      <select class="filter-select" id="filter-geology">
        <option value="">All periods</option>
      </select>
    </div>
    <div class="filter-group">
      <span class="filter-label">Indigenous territory</span>
      <select class="filter-select" id="filter-territory">
        <option value="">All territories</option>
      </select>
    </div>
  </div>
</div>

<div class="results-bar">
  <span class="results-count" id="results-count"></span>
  <button class="clear-filters" id="clear-filters">Clear filters</button>
</div>

<div class="index-table">
  <table>
    <thead>
      <tr>
        <th data-sort="name">Site <span class="sort-indicator">&#9650;</span></th>
        <th data-sort="state">State <span class="sort-indicator">&#9650;</span></th>
        <th data-sort="agency">Agency <span class="sort-indicator">&#9650;</span></th>
        <th data-sort="geology">Geology <span class="sort-indicator">&#9650;</span></th>
        <th data-sort="acreage">Acreage <span class="sort-indicator">&#9650;</span></th>
        <th class="native-lands-col" data-sort="territory">Indigenous territory <span class="sort-indicator">&#9650;</span></th>
      </tr>
    </thead>
    <tbody id="site-tbody">
    </tbody>
  </table>
  <div class="empty-state" id="empty-state">No sites match the current filters.</div>
</div>

<div class="footer">
  Public Lands Institute &#183; CC0 Public Domain &#183; <a href="https://publiclandsinstitute.net/" style="color: var(--gray-400);">publiclandsinstitute.net</a>
</div>

<script>
const sites = {js_array};

function getUnique(arr, key) {{
  const vals = new Set();
  arr.forEach(s => {{
    if (Array.isArray(s[key])) {{
      s[key].forEach(v => vals.add(v));
    }} else if (s[key]) {{
      vals.add(s[key]);
    }}
  }});
  return [...vals].sort();
}}

function populateFilter(selectId, values) {{
  const select = document.getElementById(selectId);
  const defaultOption = select.options[0];
  select.innerHTML = '';
  select.appendChild(defaultOption);
  values.forEach(v => {{
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    select.appendChild(opt);
  }});
}}

populateFilter('filter-state', getUnique(sites, 'state'));
populateFilter('filter-agency', getUnique(sites, 'agency'));
populateFilter('filter-geology', getUnique(sites, 'geology'));
populateFilter('filter-territory', getUnique(sites, 'territory'));

let sortKey = 'name';
let sortAsc = true;

function sortSites(filtered) {{
  return filtered.sort((a, b) => {{
    let valA, valB;
    if (sortKey === 'acreage') {{
      valA = a.acreage || 0;
      valB = b.acreage || 0;
      return sortAsc ? valA - valB : valB - valA;
    }}
    if (sortKey === 'territory') {{
      valA = (a.territory || []).join(', ').toLowerCase();
      valB = (b.territory || []).join(', ').toLowerCase();
    }} else {{
      valA = (a[sortKey] || '').toLowerCase();
      valB = (b[sortKey] || '').toLowerCase();
    }}
    if (valA < valB) return sortAsc ? -1 : 1;
    if (valA > valB) return sortAsc ? 1 : -1;
    return 0;
  }});
}}

function formatAcreage(n) {{
  if (!n) return '';
  return n.toLocaleString();
}}

function render() {{
  const stateFilter = document.getElementById('filter-state').value;
  const agencyFilter = document.getElementById('filter-agency').value;
  const geologyFilter = document.getElementById('filter-geology').value;
  const territoryFilter = document.getElementById('filter-territory').value;

  let filtered = sites.filter(s => {{
    if (stateFilter && s.state !== stateFilter) return false;
    if (agencyFilter && s.agency !== agencyFilter) return false;
    if (geologyFilter && s.geology !== geologyFilter) return false;
    if (territoryFilter && !s.territory.includes(territoryFilter)) return false;
    return true;
  }});

  filtered = sortSites(filtered);

  const tbody = document.getElementById('site-tbody');
  tbody.innerHTML = '';

  filtered.forEach(s => {{
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="site-name"><a href="${{s.url}}">${{s.name}}</a></td>
      <td class="state">${{s.stateAbbr}}</td>
      <td class="agency">${{s.agency}}</td>
      <td class="geology">${{s.geologyDetail}}</td>
      <td class="acreage">${{formatAcreage(s.acreage)}}</td>
      <td class="native-lands">${{s.territory.join(', ')}}</td>
    `;
    tbody.appendChild(tr);
  }});

  const total = sites.length;
  const shown = filtered.length;
  const countEl = document.getElementById('results-count');
  if (shown === total) {{
    countEl.textContent = `${{total}} sites`;
  }} else {{
    countEl.textContent = `${{shown}} of ${{total}} sites`;
  }}

  document.getElementById('empty-state').style.display = shown === 0 ? 'block' : 'none';

  const hasFilters = stateFilter || agencyFilter || geologyFilter || territoryFilter;
  document.getElementById('clear-filters').classList.toggle('visible', hasFilters);

  document.querySelectorAll('thead th').forEach(th => {{
    const key = th.dataset.sort;
    th.classList.toggle('sorted', key === sortKey);
    const indicator = th.querySelector('.sort-indicator');
    if (indicator) {{
      indicator.innerHTML = (key === sortKey && !sortAsc) ? '&#9660;' : '&#9650;';
    }}
  }});
}}

['filter-state', 'filter-agency', 'filter-geology', 'filter-territory'].forEach(id => {{
  document.getElementById(id).addEventListener('change', render);
}});

document.getElementById('clear-filters').addEventListener('click', () => {{
  document.getElementById('filter-state').value = '';
  document.getElementById('filter-agency').value = '';
  document.getElementById('filter-geology').value = '';
  document.getElementById('filter-territory').value = '';
  render();
}});

document.querySelectorAll('thead th[data-sort]').forEach(th => {{
  th.addEventListener('click', () => {{
    const key = th.dataset.sort;
    if (sortKey === key) {{
      sortAsc = !sortAsc;
    }} else {{
      sortKey = key;
      sortAsc = true;
    }}
    render();
  }});
}});

render();
</script>

</body>
</html>'''


# ── Index page builder ─────────────────────────────────────────────────────────

def make_index_page(all_sites):
    rows = ''
    for site in all_sites:
        images = get_all_images_for_site(site)
        first_img = images[0]['jpg'] if images else None

        thumb_html = ''
        if first_img:
            thumb_html = f'''    <a class="loc-thumb" href="sites/{site["slug"]}.html">
      <img src="{first_img}" alt="{site["name"]} I" loading="lazy"/>
    </a>\n'''

        field_rows = ''
        for key, label in FIELDS:
            if key in ('geological_age', 'epoch'):
                val = site.get(key, '')
                if val:
                    field_rows += f'<dt>{label}</dt><dd>{val}</dd>'

        for key, label in FIELDS:
            if key in ('native_lands', 'displacement_tenure', 'shadow_history', 'acreage', 'gps'):
                val = site.get(key, '')
                if val:
                    field_rows += f'<dt>{label}</dt><dd>{val}</dd>'

        rows += f'''  <div class="location-row">
    <div class="location-row-header">
      <span class="loc-name">{site["name"]}<span class="loc-state">{site["state"]}</span></span>
      <a class="loc-link" href="sites/{site["slug"]}.html">Images</a>
    </div>
{thumb_html}    <dl class="site-data">{field_rows}</dl>
  </div>\n'''

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
<title>Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="Public Lands Institute is an ongoing photographic index of public lands. CC0 Public Domain." name="description"/>
<meta content="index, follow" name="robots"/>
<link href="https://publiclandsinstitute.net/" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
<style>
{SHARED_CSS}
  .intro-text {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 32px;
  }}
  .section-label {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--muted);
    margin-bottom: 0;
  }}
  .location-row {{
    border-top: 1px solid var(--border);
    padding: 10px 0 14px 0;
  }}
  .location-row-header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    font-size: 13px;
    margin-bottom: 8px;
  }}
  .loc-name {{ color: var(--fg); font-weight: 500; }}
  .loc-state {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: var(--muted);
    margin-left: 6px;
    font-weight: 400;
  }}
  .loc-link {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: var(--muted);
    white-space: nowrap;
    flex-shrink: 0;
  }}
  .loc-thumb {{
    display: block;
    border: 1px solid var(--border);
    background: #e1e1e1;
    overflow: hidden;
    margin-bottom: 10px;
    width: 100%;
  }}
  .loc-thumb img {{
    width: 100%;
    height: 220px;
    display: block;
    filter: grayscale(100%);
    object-fit: cover;
    object-position: center;
    transition: opacity 0.2s ease;
  }}
  .loc-thumb:hover img {{ opacity: 0.85; }}
  .site-data {{
    display: grid;
    grid-template-columns: 172px 1fr;
    font-size: 11px;
    line-height: 1.55;
    border-top: 1px solid var(--border);
    padding-top: 8px;
    align-items: baseline;
    align-content: start;
  }}
  .site-data dt {{
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 10px;
    padding: 4px 0;
  }}
  .site-data dd {{
    color: var(--fg);
    padding: 4px 0 4px 12px;
    margin: 0;
  }}
  .inat-section-label {{
    color: var(--fg) !important;
    font-weight: 500;
    padding-top: 10px !important;
    border-top: 1px solid var(--border);
  }}
  .inat-section-spacer {{
    padding-top: 10px !important;
    border-top: 1px solid var(--border);
  }}
  .inat-sci {{
    color: var(--muted);
    font-style: italic;
  }}
  .nav-toggle {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 4px 10px;
    background: transparent;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    cursor: pointer;
  }}
  .nav-toggle {{ display: none; }}
  .site-nav-mobile {{ display: none; }}
  @media (max-width: 480px) {{
    .site-data {{ grid-template-columns: 120px 1fr; }}
  }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 28px;
    gap: 12px;
    flex-wrap: wrap;
  }}
  @media (min-width: 720px) {{
    .site-data {{ grid-template-columns: 172px 1fr; }}
    header {{ margin-bottom: 40px; }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype">Public Lands Institute</div>
  <nav class="header-nav">
    <a href="sites.html">Index</a>
    <a href="archive.html">Archive</a>
  </nav>
</header>
<div class="divider"></div>
<p class="intro-text">Public Lands Institute is an ongoing photographic index of public lands. All Public Lands Institute images are dedicated to the Public Domain under the Creative Commons CC0 (Public Domain Dedication) license.</p><div class="section-label">Locations</div>
{rows}
<footer>
  <span>Public Lands Institute \u2014 ongoing project</span>
  <span>US \u00b7 established MMXXV</span>
</footer>
</div>
</body>
</html>'''


# ── Generate ───────────────────────────────────────────────────────────────────

print('Generating site pages...')
for site in sites:
    html = make_site_page(site, sites)
    path = os.path.join('sites', f'{site["slug"]}.html')
    with open(path, 'w') as f:
        f.write(html)
    all_imgs = get_all_images_for_site(site)
    print(f'  {site["slug"]}.html  ({len(all_imgs)} images)')

print('\nGenerating archive.html...')
with open('archive.html', 'w') as f:
    f.write(make_archive_page(sites))
print('  archive.html')

print('\nGenerating index.html...')
with open('index.html', 'w') as f:
    f.write(make_index_page(sites))
print('  index.html')

print('\nGenerating sites.html...')
with open('sites.html', 'w') as f:
    f.write(make_sites_index_page(sites, SITES_META))
print('  sites.html')

print(f'\nDone \u2014 {len(sites)} site pages + archive + index + sites index.')
