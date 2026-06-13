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

import json, os, glob, re, time, urllib.request, urllib.parse
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

# ── Wikimedia Commons upload log ──────────────────────────────────────────────
# Commons is the canonical source for TIFF downloads. The upload log maps each
# (slug, camera filename) to its exact Commons filename; images without a log
# entry hide their TIFF action until uploaded.

COMMONS_LOG_FILE = os.path.expanduser(
    '~/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli-commons/upload_log.json'
)
COMMONS_FILES = {}
if os.path.exists(COMMONS_LOG_FILE):
    with open(COMMONS_LOG_FILE, 'r') as f:
        for entry in json.load(f):
            stem = os.path.splitext(os.path.basename(entry['source_path']))[0]
            COMMONS_FILES[(entry['slug'], stem)] = entry['commons_filename']

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
    xmp_path = None
    for xmp_ext in ('.xmp', '.XMP'):
        candidate = os.path.join('img', 'RAW', stem + xmp_ext)
        if os.path.exists(candidate):
            xmp_path = candidate.replace('\\', '/')
            break
    commons_name = COMMONS_FILES.get((slug, stem))
    tif_url = None
    commons_page = None
    if commons_name:
        tif_url = 'https://commons.wikimedia.org/wiki/Special:FilePath/' + urllib.parse.quote(commons_name)
        commons_page = 'https://commons.wikimedia.org/wiki/File:' + urllib.parse.quote(commons_name.replace(' ', '_'))
    return {
        'jpg': jpg_path,
        'tif': tif_path,
        'raw': raw_path,
        'xmp': xmp_path,
        'commons_name': commons_name,
        'tif_url': tif_url,
        'commons_page': commons_page,
        'camera_filename': filename,
        'caption_index': str(caption_idx + 1),
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
  .gps-link:hover { text-decoration: underline; }'''

# Paleozoic-and-later eras matched against geological_age text; color + onset Mya
GEO_TIMESCALE = [
    ('Cambrian', '#a0522d', 541), ('Ordovician', '#c8a86e', 485),
    ('Silurian', '#7ecfc0', 444), ('Devonian', '#4aaa78', 419),
    ('Mississippian', '#3d7fbf', 359), ('Pennsylvanian', '#5d5abf', 323),
    ('Permian', '#9b59b6', 299), ('Triassic', '#e07050', 252),
    ('Jurassic', '#c8a840', 201), ('Cretaceous', '#d4b840', 145),
    ('Paleogene', '#d4704a', 66), ('Neogene', '#c85a8a', 23),
    ('Quaternary', '#8c8c8c', 2.6), ('Pleistocene', '#8c8c8c', 2.6),
]
EARTH_TIMELINE_MYA = 541

def make_geo_block(geo_text):
    """Era swatch + timeline bar + full geological_age prose, mirroring the map panel."""
    if not geo_text:
        return ''
    g = geo_text.lower()
    matched = [(e, c, o) for e, c, o in GEO_TIMESCALE if e.lower() in g]
    era_row = ''
    bar = ''
    if matched:
        era, color, oldest = max(matched, key=lambda t: t[2])
        m = re.search(r'~?([\d,]+(?:-[\d,]+)?)\s*[Mm]ya', geo_text)
        mya = f'<span class="geo-mya">{m.group(1).replace(",", "")} Mya</span>' if m else ''
        pct = min(100, round(oldest / EARTH_TIMELINE_MYA * 100))
        era_row = (f'<div class="geo-era-row"><div class="geo-swatch" style="background:{color}"></div>'
                   f'<span class="geo-era-name">{era}</span>{mya}</div>')
        bar = (f'<div class="geo-bar-wrap"><div class="geo-bar-fill" '
               f'style="width:{pct}%;background:{color};opacity:0.55"></div></div>')
    return (f'<div class="rec-section"><div class="rec-label">Geology</div>'
            f'{era_row}{bar}<p class="geo-prose">{geo_text}</p></div>')

def make_site_page(site, all_sites):
    slug  = site['slug']
    name  = site['name']
    state = site['state']
    observations = get_observations_for_site(site)

    og_image = ''
    for _obs in observations:
        if _obs['images']:
            og_image = 'https://publiclandsinstitute.net/' + _obs['images'][0]['jpg']
            break
    og_image_tags = ''
    if og_image:
        og_image_tags = (f'<meta property="og:image" content="{og_image}"/>\n'
                         f'<meta name="twitter:card" content="summary_large_image"/>\n')

    idx       = next(i for i, s in enumerate(all_sites) if s['slug'] == slug)
    prev_site = all_sites[idx - 1] if idx > 0 else None
    next_site = all_sites[idx + 1] if idx < len(all_sites) - 1 else None

    nav_prev = f'<a href="{prev_site["slug"]}.html">← {prev_site["name"]}</a>' if prev_site else '<span></span>'
    nav_next = f'<a href="{next_site["slug"]}.html">{next_site["name"]} →</a>' if next_site else '<span></span>'

    def sec(label, val):
        if not val:
            return ''
        return f'<div class="rec-section"><div class="rec-label">{label}</div><p>{val}</p></div>'

    gps_val = ''
    if site.get('gps'):
        lat = site.get('lat', '')
        lng = site.get('lng', '')
        gps_val = f'<a class="gps-link" href="https://maps.google.com/?q={lat},{lng}" target="_blank" rel="noopener">{site["gps"]}</a>'

    sections = make_geo_block(site.get('geological_age', ''))
    sections += sec('Epoch', site.get('epoch', ''))
    sections += sec('Native lands', site.get('native_lands', ''))
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
            raw_attr = f' data-raw="../{img["raw"]}"' if img['raw'] else ''
            xmp_attr = f' data-xmp="../{img["xmp"]}"' if img['xmp'] else ''
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
    <a href="../archive.html">Archive</a>
    <a href="../about.html">About</a>
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
            if img['commons_page']:
                rows += f'    <a class="archive-download" href="{img["commons_page"]}" target="_blank" rel="noopener">Commons</a>\n'
            else:
                rows += f'    <span class="archive-download" style="visibility:hidden">Commons</span>\n'
            if img['raw']:
                rows += f'    <a class="archive-download" href="{img["raw"]}" download>Download RAW</a>\n'
            else:
                rows += f'    <span class="archive-download" style="visibility:hidden">Download RAW</span>\n'
            if img['xmp']:
                rows += f'    <a class="archive-download" href="{img["xmp"]}" download>XML</a>\n'
            else:
                rows += f'    <span class="archive-download" style="visibility:hidden">XML</span>\n'
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
<title>Archive \u2014 Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<meta content="Full-resolution TIFFs and RAW files from the Public Lands Institute photographic archive. CC0 Public Domain." name="description"/>
<meta property="og:title" content="Archive \u2014 Public Lands Institute"/>
<meta property="og:description" content="Full-resolution TIFFs and RAW files from the Public Lands Institute photographic archive. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/archive.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
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
    margin-bottom: 32px;
    max-width: 640px;
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
  @media (max-width: 540px) {{
    .archive-item {{ grid-template-columns: 1fr max-content max-content max-content; }}
    .archive-filename {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="index.html">Map</a>
    <a href="archive.html" class="active">Archive</a>
    <a href="about.html">About</a>
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


def make_about_page(all_sites):
    total_images = sum(len(get_all_images_for_site(s)) for s in all_sites)
    n_states = len({s['state'] for s in all_sites})

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
<title>About — Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<meta content="About the Public Lands Institute: an ongoing photographic index and open-access archive of American public lands. CC0 Public Domain." name="description"/>
<meta property="og:title" content="About — Public Lands Institute"/>
<meta property="og:description" content="About the Public Lands Institute: an ongoing photographic index and open-access archive of American public lands. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/about.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
<link href="https://publiclandsinstitute.net/about.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
{FONT_LINKS}
<style>
{SHARED_CSS}
  .about-body {{
    max-width: 760px;
  }}
  .about-body h2 {{
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--muted);
    margin: 36px 0 10px 0;
  }}
  .about-body h2:first-child {{ margin-top: 0; }}
  .about-body p {{
    font-size: 14px;
    line-height: 1.7;
    margin-bottom: 14px;
  }}
  .about-body a {{ border-bottom: 1px solid var(--border); }}
  .about-body a:hover {{ text-decoration: none; border-bottom-color: var(--fg); }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="index.html">Map</a>
    <a href="archive.html">Archive</a>
    <a href="about.html" class="active">About</a>
  </nav>
</header>
<div class="divider"></div>
<div class="about-body">
  <h2>The project</h2>
  <p>The Public Lands Institute is an ongoing photographic index and open-access archive of American public lands. The project pairs field photography with structured documentation, treating each site as a subject with multiple layers of recorded history rather than as scenic landscape. The index currently holds {len(all_sites)} sites across {n_states} states, documented in {total_images} photographs, all dedicated to the public domain.</p>

  <h2>Sources</h2>
  <p>Site records draw on primary repositories: EPA Superfund and cleanup databases; National Park Service administrative histories; National Archives Civilian Conservation Corps records; Library of Congress Chronicling America; federal and state court records; Royce cession maps and treaty texts; <a href="https://native-land.ca" target="_blank" rel="noopener">native-land.ca</a> territory data; and <a href="https://www.inaturalist.org" target="_blank" rel="noopener">iNaturalist</a> research grade observations. Travel writing, tourism copy, and managing agency press releases are not accepted as sources.</p>

  <h2>Public domain</h2>
  <p>Every photograph is dedicated to the public domain under <a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">Creative Commons CC0 1.0 Universal</a>. Full resolution TIFF and RAW files are freely downloadable from the <a href="archive.html">archive</a> and from <a href="https://commons.wikimedia.org/w/index.php?title=Special:MediaSearch&search=Public+Lands+Institute" target="_blank" rel="noopener">Wikimedia Commons</a>. No attribution is required and no permission is needed for any use. The intent is infrastructural: imagery and research about public land should be public in the same way the land is.</p>
</div>
<footer>
  <span>Public Lands Institute — ongoing project</span>
  <span>CC0 Public Domain</span>
</footer>
</div>
</body>
</html>'''


# ── Map index page builder (index.html) ─────────────────────────────────────

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

def make_sites_index_page(all_sites, meta):
    import re as _re
    import hashlib

    # Social card: first image of the most recently added site (top of sites.json)
    og_image = ''
    for _site in all_sites:
        for _obs in get_observations_for_site(_site):
            if _obs['images']:
                og_image = 'https://publiclandsinstitute.net/' + _obs['images'][0]['jpg']
                break
        if og_image:
            break
    og_image_tags = ''
    if og_image:
        og_image_tags = (f'<meta property="og:image" content="{og_image}">\n'
                         f'<meta name="twitter:card" content="summary_large_image">\n')

    # Deterministic color from nation name
    def nation_color(name):
        palette = [
            '#e8a838','#5b9e6e','#5b8abf','#bf5b7a','#7a5bbf','#c87840','#5bbfbf',
            '#bf5b5b','#8cbf5b','#4a6ebf','#bf9e5b','#5bbf8c','#bf5b9e','#5b9ebf',
            '#9ebf5b','#bf6e5b','#8a5bbf','#bfbf5b','#e87c5b','#5be8a8','#c45be8',
            '#e8c45b','#5bc4e8','#e85b8a','#a8e85b','#c8a050','#6abf9e','#9e6abf',
        ]
        idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(palette)
        return palette[idx]

    # Collect all unique nations across all sites
    all_nations = []
    seen_nations = set()
    for site in all_sites:
        slug = site['slug']
        m = meta.get(slug, {})
        for n in m.get('territory', []):
            if n not in seen_nations:
                all_nations.append(n)
                seen_nations.add(n)

    nation_colors = {n: nation_color(n) for n in all_nations}

    # Build SITES GeoJSON
    sites_features = []
    for site in all_sites:
        slug = site['slug']
        lat = site.get('lat')
        lng = site.get('lng')
        if lat is None or lng is None:
            continue
        m = meta.get(slug, {})
        territory = m.get('territory', [])
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
        sites_features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [lng, lat]},
            'properties': props,
        })
    sites_gj = json.dumps({'type': 'FeatureCollection', 'features': sites_features}, ensure_ascii=False, separators=(',', ':'))

    # Build NATIONS_GJ — one feature per (site, nation)
    nations_features = []
    for site in all_sites:
        slug = site['slug']
        lat = site.get('lat')
        lng = site.get('lng')
        if lat is None or lng is None:
            continue
        m = meta.get(slug, {})
        for n in m.get('territory', []):
            nations_features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [lng, lat]},
                'properties': {'slug': slug, 'nation': n, 'color': nation_colors.get(n, '#8c8c8c')},
            })
    nations_gj = json.dumps({'type': 'FeatureCollection', 'features': nations_features}, ensure_ascii=False, separators=(',', ':'))

    # Build PHOTOS dict — slug -> list of {f, d, thumb, large}
    photos_dict = {}
    for site in all_sites:
        slug = site['slug']
        thumb_dir = os.path.join('thumbs', slug)
        if not os.path.isdir(thumb_dir):
            continue
        images = get_all_images_for_site(site)
        if not images:
            continue
        entries = []
        for i, img in enumerate(images):
            cam = img['camera_filename']
            stem = os.path.splitext(cam)[0]
            thumb_path = f'thumbs/{slug}/{cam}'
            large_path = f'thumbs/{slug}/lg_{cam}'
            entries.append({
                'f': img['commons_name'] or img['camera_filename'],
                'd': img.get('date', '') or '',
                'thumb': thumb_path if os.path.exists(thumb_path) else '',
                'large': large_path if os.path.exists(large_path) else '',
                't': img['tif_url'] or '',
                'r': img['raw'] or '',
                'x': img['xmp'] or '',
                'c': img['commons_page'] or '',
            })
        if entries:
            photos_dict[slug] = entries
    photos_json = json.dumps(photos_dict, ensure_ascii=False, separators=(',', ':'))

    nation_colors_json = json.dumps(nation_colors, ensure_ascii=False, separators=(',', ':'))
    nation_list_json = json.dumps(all_nations, ensure_ascii=False, separators=(',', ':'))
    state_names_json = json.dumps(STATE_NAMES, ensure_ascii=False, separators=(',', ':'))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-TMR79M95R4"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-TMR79M95R4');</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Public Lands Institute</title>
<meta name="description" content="An ongoing photographic index and open-access archive of American public lands. CC0 Public Domain.">
<meta name="robots" content="index, follow">
<meta property="og:title" content="Public Lands Institute">
<meta property="og:description" content="An ongoing photographic index and open-access archive of American public lands, with geological, ecological, Indigenous land tenure, and shadow history documentation. CC0 Public Domain.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://publiclandsinstitute.net/">
<meta property="og:site_name" content="Public Lands Institute">
{og_image_tags}
<link rel="canonical" href="https://publiclandsinstitute.net/">
<link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">
<link rel="icon" href="/favicon-16.png" sizes="16x16" type="image/png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{ --sand: #e8e8e8; --ink: #161616; --moss: #444444; --stone: #8c8c8c; --panel-w: 440px; }}
html, body {{ height: 100%; font-family: 'Inter', sans-serif; background: var(--ink); }}
#map {{ position: fixed; inset: 0; }}
#wordmark {{ position: fixed; top: 28px; left: 32px; z-index: 10; pointer-events: none; }}
#wordmark h1 {{ font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 300; letter-spacing: 0.2em; text-transform: uppercase; color: var(--sand); opacity: 0.85; line-height: 1; }}
#topnav {{ position: fixed; top: 28px; right: 32px; z-index: 10; display: flex; gap: 18px; align-items: baseline; }}
#topnav a {{ color: rgba(255,255,255,0.55); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 300; text-decoration: none; transition: color 0.15s; }}
#topnav a:hover {{ color: var(--sand); }}
#site-count {{ color: rgba(255,255,255,0.3); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; font-weight: 300; }}
#layers {{ position: fixed; bottom: 32px; left: 32px; z-index: 10; display: flex; flex-direction: column; gap: 6px; }}
.layer-btn {{ background: rgba(18,18,18,0.72); border: 1px solid rgba(255,255,255,0.2); color: var(--sand); font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; padding: 6px 12px; cursor: pointer; backdrop-filter: blur(8px); transition: border-color 0.2s; text-align: left; }}
.layer-btn:hover {{ border-color: rgba(255,255,255,0.5); }}
.layer-btn.active {{ color: #ffffff; border-color: #ffffff; background: rgba(18,18,18,0.9); }}
#legend {{ position: fixed; bottom: 32px; right: 32px; z-index: 10; background: rgba(18,18,18,0.85); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.15); padding: 14px 16px; min-width: 200px; display: none; }}
#legend.visible {{ display: block; }}
#legend-title {{ font-size: 10px; font-weight: 500; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255,255,255,0.45); margin-bottom: 10px; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 11px; font-weight: 300; color: rgba(255,255,255,0.75); }}
.legend-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
#panel {{ position: fixed; top: 0; right: 0; width: var(--panel-w); height: 100%; background: var(--sand); z-index: 20; transform: translateX(100%); transition: transform 0.4s cubic-bezier(0.16,1,0.3,1); overflow-y: auto; overflow-x: hidden; }}
#panel.open {{ transform: translateX(0); }}
#panel-close {{ position: sticky; top: 0; z-index: 5; display: flex; justify-content: flex-end; padding: 16px 20px 0; background: var(--sand); }}
#panel-close button {{ background: none; border: none; cursor: pointer; color: var(--stone); font-size: 20px; line-height: 1; padding: 4px; }}
#panel-close button:hover {{ color: var(--ink); }}
#panel-body {{ padding: 8px 32px 48px; }}
.panel-site-name {{ font-family: 'Inter', sans-serif; font-size: 22px; font-weight: 300; letter-spacing: -0.01em; color: var(--ink); line-height: 1.2; margin-bottom: 4px; }}
.panel-site-name a {{ color: inherit; text-decoration: none; border-bottom: 1px solid rgba(18,18,18,0.25); }}
.panel-site-name a:hover {{ border-bottom-color: var(--ink); }}
.panel-page-link {{ font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; margin: 14px 0 0; text-align: right; }}
.panel-page-link a {{ color: var(--moss); text-decoration: none; border-bottom: 1px solid var(--moss); }}
.panel-state {{ font-size: 11px; font-weight: 400; letter-spacing: 0.12em; text-transform: uppercase; color: var(--stone); margin-bottom: 20px; }}
.photo-grid {{ display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 180px; gap: 3px; margin-bottom: 6px; }}
.photo-thumb {{ background: #c8c8c8; cursor: pointer; overflow: hidden; }}
.photo-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0; transition: opacity 0.25s; }}
.photo-thumb img.loaded {{ opacity: 1; }}
.photo-thumb:hover img {{ opacity: 0.75; }}
.photo-grid-more {{ font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--stone); margin-bottom: 20px; text-align: right; }}
.photo-grid-more a {{ color: var(--moss); text-decoration: none; border-bottom: 1px solid var(--moss); }}
.panel-section {{ margin-bottom: 20px; border-top: 1px solid rgba(18,18,18,0.12); padding-top: 16px; }}
.panel-section-label {{ font-size: 10px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--stone); margin-bottom: 8px; }}
.panel-section p {{ font-size: 13.5px; font-weight: 300; line-height: 1.7; color: #2a2a2a; }}
.geo-block {{ margin-bottom: 20px; border-top: 1px solid rgba(18,18,18,0.12); padding-top: 16px; }}
.geo-label {{ font-size: 10px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--stone); margin-bottom: 10px; }}
.geo-era-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
.geo-swatch {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
.geo-era-name {{ font-size: 14px; font-weight: 300; color: var(--ink); }}
.geo-mya {{ font-size: 11px; font-weight: 300; color: var(--stone); margin-left: auto; letter-spacing: 0.04em; }}
.geo-bar-wrap {{ position: relative; height: 3px; background: rgba(18,18,18,0.08); margin-bottom: 8px; border-radius: 2px; }}
.geo-bar-fill {{ position: absolute; right: 0; top: 0; height: 100%; border-radius: 2px; }}
.geo-prose {{ font-size: 12px; font-weight: 300; line-height: 1.6; color: var(--stone); }}
#lightbox {{ position: fixed; inset: 0; z-index: 100; background: rgba(12,12,12,0.97); display: none; flex-direction: column; }}
#lightbox.open {{ display: flex; }}
#lb-img-wrap {{ flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 56px 72px 0; position: relative; }}
#lb-img {{ max-width: 100%; max-height: 100%; object-fit: contain; display: block; opacity: 0; transition: opacity 0.2s; }}
#lb-img.loaded {{ opacity: 1; }}
#lb-spinner {{ position: absolute; color: rgba(255,255,255,0.3); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; }}
#lb-bar {{ display: flex; align-items: center; justify-content: space-between; padding: 14px 72px 20px; gap: 24px; flex-shrink: 0; border-top: 1px solid rgba(255,255,255,0.07); }}
#lb-meta {{ flex: 1; min-width: 0; }}
#lb-filename {{ font-size: 12px; font-weight: 300; color: rgba(255,255,255,0.55); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }}
#lb-date {{ font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.3); }}
#lb-actions {{ display: flex; gap: 8px; flex-shrink: 0; }}
.lb-action {{ font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; text-decoration: none; padding: 5px 12px; border: 1px solid rgba(255,255,255,0.3); color: rgba(255,255,255,0.65); transition: border-color 0.15s, color 0.15s; white-space: nowrap; }}
.lb-action:hover {{ border-color: rgba(255,255,255,0.75); color: var(--sand); }}
#lb-close {{ position: fixed; top: 18px; right: 24px; z-index: 101; background: none; border: none; cursor: pointer; color: rgba(255,255,255,0.4); font-size: 22px; line-height: 1; transition: color 0.15s; }}
#lb-close:hover {{ color: var(--sand); }}
#lb-prev, #lb-next {{ position: fixed; top: 50%; transform: translateY(-50%); z-index: 101; background: none; border: none; cursor: pointer; color: rgba(255,255,255,0.3); font-size: 36px; padding: 16px; transition: color 0.15s; line-height: 1; }}
#lb-prev {{ left: 8px; }} #lb-next {{ right: 8px; }}
#lb-prev:hover, #lb-next:hover {{ color: var(--sand); }}
#lb-counter {{ position: fixed; top: 22px; left: 50%; transform: translateX(-50%); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(255,255,255,0.25); }}
.maplibregl-popup-content {{ background: var(--ink); color: var(--sand); font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 300; padding: 8px 12px; border-radius: 0; box-shadow: none; }}
.maplibregl-popup-tip {{ border-top-color: var(--ink) !important; }}
.maplibregl-ctrl-attrib {{ font-size: 9px; opacity: 0.4; }}
@media (max-width: 640px) {{
  :root {{ --panel-w: 100%; }}
  #wordmark {{ top: 16px; left: 16px; }}
  #wordmark h1 {{ font-size: 11px; }}
  #topnav {{ top: 16px; right: 16px; gap: 12px; }}
  #topnav a, #site-count {{ font-size: 10px; }}
  #layers {{ bottom: 16px; left: 16px; right: 16px; }}
  .layer-btn {{ font-size: 11px; padding: 7px 10px; }}
  #legend {{ left: 16px; right: 16px; bottom: 84px; min-width: 0; }}
  #panel {{ width: 100%; }}
  #panel-body {{ padding: 8px 20px 48px; }}
  .panel-site-name {{ font-size: 19px; }}
  .photo-grid {{ grid-template-columns: 1fr 1fr; grid-auto-rows: 130px; }}
  .panel-section p, .geo-prose {{ word-break: break-word; overflow-wrap: break-word; }}
  #lb-img-wrap {{ padding: 56px 16px 0; }}
  #lb-bar {{ padding: 14px 16px 20px; flex-direction: column; align-items: flex-start; gap: 10px; }}
  #lb-actions {{ flex-wrap: wrap; }}
  #lb-prev, #lb-next {{ font-size: 28px; padding: 10px; }}
  #lb-prev {{ left: 0; }} #lb-next {{ right: 0; }}
}}
</style>
</head>
<body>
<div id="map"></div>
<div id="wordmark"><h1>Public Lands Institute</h1></div>
<nav id="topnav">
  <a href="archive.html">Archive</a>
  <a href="about.html">About</a>
  <span id="site-count"></span>
</nav>
<div id="layers">
  <button class="layer-btn" data-layer="geology">Geologic Age</button>
  <button class="layer-btn" data-layer="agency">Managing Agency</button>
  <button class="layer-btn" data-layer="native">Indigenous Territories</button>
  <button class="layer-btn" data-layer="shadow">Shadow History</button>
</div>
<div id="legend"><div id="legend-title"></div><div id="legend-items"></div></div>
<div id="panel">
  <div id="panel-close"><button>&#x2715;</button></div>
  <div id="panel-body"></div>
</div>
<div id="lightbox">
  <button id="lb-close">&#x2715;</button>
  <button id="lb-prev">&#x2039;</button>
  <button id="lb-next">&#x203a;</button>
  <div id="lb-counter"></div>
  <div id="lb-img-wrap">
    <div id="lb-spinner">Loading</div>
    <img id="lb-img" src="" alt="">
  </div>
  <div id="lb-bar">
    <div id="lb-meta">
      <div id="lb-filename"></div>
      <div id="lb-date"></div>
    </div>
    <div id="lb-actions">
      <a id="lb-tif" class="lb-action" href="#" download>Download TIFF</a>
      <a id="lb-raw" class="lb-action" href="#" download>RAW File</a>
      <a id="lb-xml" class="lb-action" href="#" download>XML</a>
      <a id="lb-commons" class="lb-action" href="#" target="_blank" rel="noopener">Commons</a>
    </div>
  </div>
</div>
<script>
const SITES={sites_gj};
const NATIONS_GJ={nations_gj};
const PHOTOS={photos_json};
const STATE_NAMES={state_names_json};
const NATION_COLORS={nation_colors_json};
const NATION_LIST={nation_list_json};

const GEOLOGY_ERAS = [
  ["Cambrian","#a0522d"],["Ordovician","#c8a86e"],["Silurian","#7ecfc0"],["Devonian","#4aaa78"],
  ["Mississippian","#3d7fbf"],["Pennsylvanian","#5d5abf"],["Permian","#9b59b6"],
  ["Triassic","#e07050"],["Jurassic","#c8a840"],["Cretaceous","#d4b840"],
  ["Paleogene","#d4704a"],["Neogene","#c85a8a"],["Quaternary","#8c8c8c"],["Pleistocene","#8c8c8c"],
];
const GEO_TIMESCALE = [
  ["Cambrian","#a0522d",541,485],["Ordovician","#c8a86e",485,444],["Silurian","#7ecfc0",444,419],
  ["Devonian","#4aaa78",419,359],["Mississippian","#3d7fbf",359,323],["Pennsylvanian","#5d5abf",323,299],
  ["Permian","#9b59b6",299,252],["Triassic","#e07050",252,201],["Jurassic","#c8a840",201,145],
  ["Cretaceous","#d4b840",145,66],["Paleogene","#d4704a",66,23],["Neogene","#c85a8a",23,2.6],
  ["Quaternary","#8c8c8c",2.6,0],["Pleistocene","#8c8c8c",2.6,0.01],
];
const EARTH_AGE = 541;
const GEOLOGY_LEGEND = [
  ["Ordovician \xb7 485–444 Mya","#c8a86e"],["Silurian \xb7 444–419 Mya","#7ecfc0"],["Devonian \xb7 419–359 Mya","#4aaa78"],
  ["Mississippian \xb7 359–323 Mya","#3d7fbf"],["Pennsylvanian \xb7 323–299 Mya","#5d5abf"],
  ["Permian \xb7 299–252 Mya","#9b59b6"],["Cretaceous \xb7 145–66 Mya","#d4b840"],
  ["Paleogene \xb7 66–23 Mya","#d4704a"],["Quaternary \xb7 <2.6 Mya","#8c8c8c"],
];
const AGENCY_ENTRIES = [
  ["National Park Service","#5c9e6a"],["U.S. Fish & Wildlife Service","#4a8a9e"],
  ["State Park / Preserve","#9e7a4a"],["Nature Conservancy / Private","#7a5a8a"],["Other","#5a5a52"],
];
const NATIVE_LEGEND = NATION_LIST.map(n => [n, NATION_COLORS[n]||'#8c8c8c']);
const LAYER_LEGENDS = {{
  geology:{{ title:"Geologic Age",          entries:GEOLOGY_LEGEND }},
  agency: {{ title:"Managing Agency",        entries:AGENCY_ENTRIES }},
  native: {{ title:"Indigenous Territories", entries:NATIVE_LEGEND }},
  shadow: {{ title:"Shadow History",         entries:[["Extensively documented","#c85a2a"],["Documented","#c8904a"],["Brief note","#8a6a3a"]] }},
}};
function geologyColor(geo) {{
  const g=(geo||'').toLowerCase();
  for (const [era,c] of GEOLOGY_ERAS) if (g.includes(era.toLowerCase())) return c;
  return '#5a5a52';
}}
function agencyColor(s) {{
  const sl=(s||'').toLowerCase();
  if (sl.includes('national park')||sl.includes('national seashore')||sl.includes('national river')||sl.includes('national monument')||sl.includes('national recreation')) return '#5c9e6a';
  if (sl.includes('wildlife refuge')||sl.includes('federal wilderness')) return '#4a8a9e';
  if (sl.includes('state park')||sl.includes('state nature preserve')||sl.includes('state memorial')||sl.includes('state forest')) return '#9e7a4a';
  if (sl.includes('nature conservancy')||sl.includes('private')||sl.includes('land trust')) return '#7a5a8a';
  return '#5a5a52';
}}
let activeLayer = null;
function dotColor(p) {{
  if (activeLayer==='geology') return geologyColor(p.geology);
  if (activeLayer==='agency')  return agencyColor(p.conservation_status);
  if (activeLayer==='native')  return p.primary_nation ? (NATION_COLORS[p.primary_nation]||'#8c8c8c') : '#3a3a38';
  if (activeLayer==='shadow')  {{ const l=(p.shadow_history||'').length; return l>800?'#c85a2a':l>400?'#c8904a':'#8a6a3a'; }}
  return '#e8e8e8';
}}
function buildDotFeatures() {{
  return {{ ...SITES, features: SITES.features.map(f => ({{...f, properties:{{...f.properties, _color:dotColor(f.properties)}}}}) ) }};
}}
const map = new maplibregl.Map({{
  container:'map',
  style:{{ version:8, sources:{{ base:{{ type:'raster', tiles:['https://basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}@2x.png'], tileSize:256, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>' }} }}, layers:[{{id:'bg',type:'raster',source:'base'}}] }},
  bounds:(() => {{
    const lngs = SITES.features.map(f => f.geometry.coordinates[0]);
    const lats = SITES.features.map(f => f.geometry.coordinates[1]);
    return [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]];
  }})(),
  fitBoundsOptions:{{ padding: window.innerWidth < 640 ? {{top:70,bottom:130,left:30,right:30}} : {{top:90,bottom:120,left:70,right:70}} }},
  minZoom:2, maxZoom:18,
}});
document.getElementById('site-count').textContent = SITES.features.length+' sites';
map.on('load', () => {{
  map.addSource('sites', {{ type:'geojson', data:buildDotFeatures() }});
  map.addSource('nations', {{ type:'geojson', data:NATIONS_GJ }});
  map.addLayer({{ id:'nations-dot', type:'circle', source:'nations',
    layout:{{ visibility:'none' }},
    paint:{{ 'circle-radius':['interpolate',['linear'],['zoom'],3,4.5,10,8],
            'circle-color':['get','color'], 'circle-opacity':0.85,
            'circle-stroke-color':'rgba(255,255,255,0.2)','circle-stroke-width':1 }} }});
  map.addLayer({{ id:'sites-hit', type:'circle', source:'sites', paint:{{ 'circle-radius':16,'circle-opacity':0,'circle-stroke-width':0 }} }});
  map.addLayer({{ id:'sites-dot', type:'circle', source:'sites',
    paint:{{ 'circle-radius':['interpolate',['linear'],['zoom'],3,4.5,10,8],
            'circle-color':['get','_color'],'circle-opacity':0.88,
            'circle-stroke-color':'rgba(255,255,255,0.2)','circle-stroke-width':1 }} }});
  const popup = new maplibregl.Popup({{closeButton:false,closeOnClick:false,offset:12}});
  let panelOpen = false;
  map.on('mouseenter','sites-hit', e => {{
    if (panelOpen) return;
    map.getCanvas().style.cursor='pointer';
    popup.setLngLat(e.lngLat).setHTML('<span style="letter-spacing:.07em">'+e.features[0].properties.name+'</span>').addTo(map);
  }});
  map.on('mouseleave','sites-hit', () => {{
    if (panelOpen) return;
    map.getCanvas().style.cursor=''; popup.remove();
  }});
  map.on('click','sites-hit', e => {{
    const props = e.features[0].properties;
    const coords = e.features[0].geometry.coordinates;
    map.flyTo({{ center:coords, zoom:Math.max(map.getZoom(),11), duration:900, essential:true }});
    popup.remove();
    panelOpen = true;
    openPanel(props);
  }});
  document.querySelectorAll('.layer-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const layer = btn.dataset.layer;
      if (activeLayer===layer) {{ activeLayer=null; btn.classList.remove('active'); hideLegend(); }}
      else {{ document.querySelectorAll('.layer-btn').forEach(b=>b.classList.remove('active')); activeLayer=layer; btn.classList.add('active'); showLegend(layer); }}
      const nativeOn = activeLayer === 'native';
      map.setLayoutProperty('nations-dot', 'visibility', nativeOn ? 'visible' : 'none');
      map.setLayoutProperty('sites-dot',   'visibility', nativeOn ? 'none'    : 'visible');
      if (!nativeOn) {{ map.setFilter('nations-dot', null); map.setFilter('sites-dot', null); }}
      map.getSource('sites').setData(buildDotFeatures());
    }});
  }});
}});
function showLegend(layer) {{
  const def = LAYER_LEGENDS[layer];
  document.getElementById('legend-title').textContent = def.title;
  document.getElementById('legend-items').innerHTML = def.entries.map(([l,c])=>
    '<div class="legend-item" data-color="'+c+'" style="cursor:pointer"><div class="legend-dot" style="background:'+c+'"></div><span>'+l+'</span></div>').join('');
  document.getElementById('legend-items').querySelectorAll('.legend-item').forEach((item, i) => {{
    item.addEventListener('mouseenter', () => {{
      if (activeLayer === 'native') map.setFilter('nations-dot', ['==', ['get','nation'], NATION_LIST[i]]);
      else map.setFilter('sites-dot', ['==', ['get','_color'], item.dataset.color]);
    }});
    item.addEventListener('click', () => {{
      let matching;
      if (activeLayer === 'native') matching = NATIONS_GJ.features.filter(f => f.properties.nation === NATION_LIST[i]);
      else matching = SITES.features.filter(f => dotColor(f.properties) === item.dataset.color);
      if (!matching.length) return;
      const lngs = matching.map(f => f.geometry.coordinates[0]);
      const lats = matching.map(f => f.geometry.coordinates[1]);
      map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
        {{ padding:{{ top:80, bottom:180, left:220, right:280 }}, maxZoom:9, duration:800 }});
    }});
  }});
  document.getElementById('legend').addEventListener('mouseleave', () => {{
    map.setFilter('nations-dot', null); map.setFilter('sites-dot', null);
  }});
  document.getElementById('legend').classList.add('visible');
}}
function hideLegend() {{
  map.setFilter('nations-dot', null); map.setFilter('sites-dot', null);
  document.getElementById('legend').classList.remove('visible');
}}
function buildGeoBlock(geoText) {{
  if (!geoText) return '';
  const g = geoText.toLowerCase();
  const matched = GEO_TIMESCALE.filter(([era]) => g.includes(era.toLowerCase()));
  if (!matched.length) return '';
  const [eraName, color, oldest] = matched.reduce((a, b) => a[2] > b[2] ? a : b);
  const myaMatch = geoText.match(/~?([\d,]+(?:-[\d,]+)?)\s*[Mm]ya/);
  const myaLabel = myaMatch ? myaMatch[1].replace(',','') + ' Mya' : '';
  const barPct = Math.min(100, Math.round((oldest / EARTH_AGE) * 100));
  const prose = geoText.split(';')[0].trim();
  return '<div class="geo-block">' +
    '<div class="geo-label">Geology</div>' +
    '<div class="geo-era-row">' +
      '<div class="geo-swatch" style="background:'+color+'"></div>' +
      '<span class="geo-era-name">'+eraName+'</span>' +
      (myaLabel ? '<span class="geo-mya">'+myaLabel+'</span>' : '') +
    '</div>' +
    '<div class="geo-bar-wrap"><div class="geo-bar-fill" style="width:'+barPct+'%;background:'+color+';opacity:0.5"></div></div>' +
    '<p class="geo-prose">'+prose+'</p>' +
  '</div>';
}}
const imgObserver = new IntersectionObserver((entries) => {{
  entries.forEach(entry => {{
    if (entry.isIntersecting) {{
      const img = entry.target;
      if (img.dataset.src) {{ img.src=img.dataset.src; img.onload=()=>img.classList.add('loaded'); imgObserver.unobserve(img); }}
    }}
  }});
}}, {{ rootMargin:'120px' }});
const panel = document.getElementById('panel');
const panelBody = document.getElementById('panel-body');
document.getElementById('panel-close').querySelector('button').addEventListener('click', () => {{
  panel.classList.remove('open'); panelOpen = false; map.getCanvas().style.cursor='';
}});
let currentPhotos = [];
function sec(label, text) {{
  return text ? '<div class="panel-section"><div class="panel-section-label">'+label+'</div><p>'+text+'</p></div>' : '';
}}
function openPanel(props) {{
  const state   = STATE_NAMES[props.state]||props.state;
  const acreage = props.acreage
    ? (/^\d[\d,]*$/.test(props.acreage.trim())
        ? parseInt(props.acreage.replace(/,/g,'')).toLocaleString()+' acres'
        : props.acreage)
    : '';
  const photos = (PHOTOS[props.slug]||[]).filter(p => p.thumb);
  currentPhotos = photos;
  const GRID_MAX = 6;
  const grid = photos.slice(0, GRID_MAX);
  let gridHTML = '';
  if (grid.length) {{
    gridHTML = '<div class="photo-grid">' +
      grid.map((p,i) => '<div class="photo-thumb" data-idx="'+i+'"><img data-src="'+p.thumb+'" alt=""></div>').join('') +
    '</div>';
    if (photos.length > GRID_MAX) {{
      gridHTML += '<p class="photo-grid-more"><a href="sites/'+props.slug+'.html">View all '+photos.length+' photos →</a></p>';
    }}
  }}
  let sections = '';
  sections += buildGeoBlock(props.geology);
  sections += sec('Epoch', props.epoch);
  sections += sec('Native Lands', props.native_lands);
  sections += sec('Displacement & Tenure', props.displacement_tenure);
  sections += sec('Shadow History', props.shadow_history);
  sections += sec('Ecology', props.ecology);
  sections += sec('Hydrology', props.hydrology);
  sections += sec('Conservation Status', props.conservation_status);
  sections += sec('Endangered Species', props.endangered_species);
  sections += sec('Acreage', acreage);
  sections += sec('GPS', props.gps);
  panelBody.innerHTML =
    '<p class="panel-site-name"><a href="sites/'+props.slug+'.html">'+props.name+'</a></p>'+
    '<p class="panel-state">'+state+'</p>'+
    gridHTML+
    sections+
    '<p class="panel-page-link"><a href="sites/'+props.slug+'.html">Site page · downloads →</a></p>';
  panelBody.querySelectorAll('.photo-thumb img').forEach(img => imgObserver.observe(img));
  panelBody.querySelectorAll('.photo-thumb').forEach(el => {{
    el.addEventListener('click', () => openLightbox(parseInt(el.dataset.idx)));
  }});
  panel.classList.add('open');
}}
const lightbox  = document.getElementById('lightbox');
const lbImg     = document.getElementById('lb-img');
const lbSpinner = document.getElementById('lb-spinner');
let lbIndex = 0;
function openLightbox(idx) {{ lbIndex=idx; lightbox.classList.add('open'); showLbPhoto(idx); }}
function showLbPhoto(idx) {{
  const p = currentPhotos[idx];
  if (!p) return;
  lbImg.classList.remove('loaded'); lbImg.src=''; lbSpinner.style.display='block'; lbSpinner.textContent='Loading';
  document.getElementById('lb-counter').textContent  = (idx+1)+' / '+currentPhotos.length;
  document.getElementById('lb-filename').textContent = p.f;
  document.getElementById('lb-date').textContent     = p.d||'';
  const lbCommons = document.getElementById('lb-commons');
  lbCommons.style.display = p.c ? '' : 'none';
  if (p.c) lbCommons.href = p.c;
  const lbTif = document.getElementById('lb-tif');
  const lbRaw = document.getElementById('lb-raw');
  const lbXml = document.getElementById('lb-xml');
  lbTif.style.display = p.t ? '' : 'none';
  if (p.t) lbTif.href = p.t;
  lbRaw.style.display = p.r ? '' : 'none';
  if (p.r) lbRaw.href = p.r;
  lbXml.style.display = p.x ? '' : 'none';
  if (p.x) lbXml.href = p.x;
  if (p.large) {{
    lbImg.src = p.large;
    lbImg.onload  = () => {{ lbSpinner.style.display='none'; lbImg.classList.add('loaded'); }};
    lbImg.onerror = () => {{ lbSpinner.textContent='Image unavailable'; }};
  }} else {{ lbSpinner.textContent='No local image'; }}
}}
document.getElementById('lb-close').addEventListener('click', () => {{ lightbox.classList.remove('open'); lbImg.src=''; }});
document.getElementById('lb-prev').addEventListener('click',  () => {{ lbIndex=(lbIndex-1+currentPhotos.length)%currentPhotos.length; showLbPhoto(lbIndex); }});
document.getElementById('lb-next').addEventListener('click',  () => {{ lbIndex=(lbIndex+1)%currentPhotos.length; showLbPhoto(lbIndex); }});
lightbox.addEventListener('click', e => {{ if(e.target===lightbox){{ lightbox.classList.remove('open'); lbImg.src=''; }} }});
document.addEventListener('keydown', e => {{
  if (!lightbox.classList.contains('open')) return;
  if (e.key==='Escape')     {{ lightbox.classList.remove('open'); lbImg.src=''; }}
  if (e.key==='ArrowLeft')  {{ lbIndex=(lbIndex-1+currentPhotos.length)%currentPhotos.length; showLbPhoto(lbIndex); }}
  if (e.key==='ArrowRight') {{ lbIndex=(lbIndex+1)%currentPhotos.length; showLbPhoto(lbIndex); }}
}});
</script>
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
    f.write(make_sites_index_page(sites, SITES_META))
print('  index.html')

print('\nGenerating about.html...')
with open('about.html', 'w') as f:
    f.write(make_about_page(sites))
print('  about.html')

print('\nGenerating sitemap.xml...')
BASE_URL = 'https://publiclandsinstitute.net'
_today = _dt.date.today().isoformat()
_urls = [f'{BASE_URL}/', f'{BASE_URL}/archive.html', f'{BASE_URL}/about.html']
_urls += [f'{BASE_URL}/sites/{s["slug"]}.html' for s in sites]
with open('sitemap.xml', 'w') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
    for u in _urls:
        f.write(f'  <url><loc>{u}</loc><lastmod>{_today}</lastmod></url>\n')
    f.write('</urlset>\n')
print(f'  sitemap.xml ({len(_urls)} URLs)')

print(f'\nDone \u2014 {len(sites)} site pages + archive + map index + about + sitemap.')

import subprocess as _sp
_backup = os.path.expanduser(
    '~/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli-commons/backup_to_gdrive.sh'
)
if os.path.exists(_backup):
    print('\nBacking up to Google Drive...')
    _result = _sp.run(['bash', _backup], capture_output=True, text=True)
    if _result.returncode == 0:
        print('Backup complete.')
    else:
        print(f'Backup warning: {(_result.stderr or _result.stdout).strip()}')
