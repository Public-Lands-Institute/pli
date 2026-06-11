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
    return {
        'jpg': jpg_path,
        'tif': tif_path,
        'raw': raw_path,
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

    # Build fields
    GEO_KEYS = {'geological_age', 'epoch'}
    REMAINING_KEYS = {'native_lands', 'displacement_tenure', 'ecology', 'hydrology', 'acreage', 'gps', 'shadow_history'}

    fields_html = ''
    for key, label in FIELDS:
        if key in GEO_KEYS:
            val = site.get(key, '')
            if val:
                fields_html += f'      <dt>{label}</dt><dd>{val}</dd>\n'

    for key, label in FIELDS:
        if key in REMAINING_KEYS:
            val = site.get(key, '')
            if val:
                if key == 'gps':
                    lat = site.get('lat', '')
                    lng = site.get('lng', '')
                    val = f'<a class="gps-link" href="https://maps.google.com/?q={lat},{lng}" target="_blank" rel="noopener">{val}</a>'
                fields_html += f'      <dt>{label}</dt><dd>{val}</dd>\n'

    show_obs_headers = len(observations) > 1 or any(obs.get('notes') for obs in observations)
    total_images = sum(len(obs['images']) for obs in observations)
    images_html = ''
    first_image_done = False
    for obs in observations:
        if show_obs_headers:
            label = format_obs_date(obs['date']) if obs['date'] else 'Undated'
            notes_html = f'\n      <p class="obs-notes">{obs["notes"]}</p>' if obs.get('notes') else ''
            extra_cls = ' pli-img-extra' if first_image_done else ''
            images_html += f'    <div class="obs-header{extra_cls}">\n      <span class="obs-date">{label}</span>{notes_html}\n    </div>\n'
        for img in obs['images']:
            caption = f'{name} {img["caption_index"]}'
            date_str = f' &middot; {img["date"]}' if img['date'] else ''
            extra_cls = ' pli-img-extra' if first_image_done else ''
            images_html += f'''    <figure class="site-figure{extra_cls}">
      <a href="../{img["tif"]}" download title="Download {img["camera_filename"]}">
        <img src="../{img["jpg"]}" alt="{caption}" loading="lazy"/>
      </a>
      <figcaption>
        <span class="caption-title">{caption}{date_str}</span>
        <span class="caption-filename">{img["camera_filename"]}</span>
      </figcaption>
    </figure>\n'''
            first_image_done = True
    if total_images > 1:
        images_html += f'    <button class="pli-view-all" data-index="0">View all {total_images} images</button>\n'

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
<title>{name} \u2014 Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="index, follow" name="robots"/>
<meta content="{name}. Public Lands Institute photographic index. CC0 Public Domain." name="description"/>
<meta property="og:title" content="{name} \u2014 Public Lands Institute"/>
<meta property="og:description" content="{name}. An ongoing photographic index and open-access archive of American public lands. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/sites/{slug}.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
<link href="https://publiclandsinstitute.net/sites/{slug}.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
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
  .pli-img-extra {{ display: none; }}
  .pli-view-all {{
    display: block; width: 100%; padding: 10px 0;
    font-family: system-ui, sans-serif; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.16em;
    color: var(--muted); background: transparent;
    border: 1px solid var(--border); cursor: pointer;
    margin-top: 4px;
  }}
  .pli-view-all:hover {{ color: var(--fg); }}
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
    .site-layout {{ grid-template-columns: 350px 1fr; gap: 48px; align-items: start; }}
    .site-data {{ position: sticky; top: 24px; }}
  }}
  @media (min-width: 1148px) {{
    .site-layout {{ grid-template-columns: 7fr 15fr; }}
  }}
  @media (max-width: 480px) {{
    .site-data {{ grid-template-columns: 110px 1fr; }}
    .site-images {{ order: -1; position: relative; }}
    .site-data {{ order: 0; }}
    .site-figure {{ display: none; }}
    .site-figure.carousel-active {{ display: block; }}
    .obs-header {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="../index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="../sites.html">Sites</a>
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
<script>
(function () {{
  if (!window.matchMedia('(max-width: 480px)').matches) return;
  var figures = Array.from(document.querySelectorAll('.site-figure'));
  if (!figures.length) return;
  var cur = 0;
  figures[0].classList.add('carousel-active');
  if (figures.length < 2) return;
  var container = document.querySelector('.site-images');
  var counter = document.createElement('div');
  counter.className = 'carousel-counter';
  counter.style.cssText = 'position:absolute;bottom:8px;right:8px;font-size:10px;font-family:monospace;color:var(--muted);letter-spacing:0.1em;pointer-events:none;z-index:3;';
  counter.textContent = '1 / ' + figures.length;
  container.appendChild(counter);
  var btnPrev = document.createElement('button');
  btnPrev.style.cssText = 'position:absolute;top:0;left:0;width:35%;height:100%;background:transparent;border:none;cursor:pointer;z-index:2;opacity:0;';
  btnPrev.setAttribute('aria-label', 'Previous image');
  container.appendChild(btnPrev);
  var btnNext = document.createElement('button');
  btnNext.style.cssText = 'position:absolute;top:0;right:0;width:35%;height:100%;background:transparent;border:none;cursor:pointer;z-index:2;opacity:0;';
  btnNext.setAttribute('aria-label', 'Next image');
  container.appendChild(btnNext);
  function show(i) {{
    figures[cur].classList.remove('carousel-active');
    cur = (i + figures.length) % figures.length;
    figures[cur].classList.add('carousel-active');
    counter.textContent = (cur + 1) + ' / ' + figures.length;
  }}
  btnPrev.addEventListener('click', function () {{ show(cur - 1); }});
  btnNext.addEventListener('click', function () {{ show(cur + 1); }});
  var sx, sy;
  container.addEventListener('touchstart', function (e) {{
    sx = e.touches[0].clientX;
    sy = e.touches[0].clientY;
  }}, {{ passive: true }});
  container.addEventListener('touchend', function (e) {{
    var dx = e.changedTouches[0].clientX - sx;
    var dy = e.changedTouches[0].clientY - sy;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) show(dx < 0 ? cur + 1 : cur - 1);
  }}, {{ passive: true }});
}})();
</script>
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
    <a href="sites.html">Sites</a>
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
<style>
{SHARED_CSS}
  .about-body {{
    max-width: 620px;
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
    <a href="sites.html">Sites</a>
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

SITES_INDEX_CSS = '''  *, *::before, *::after {
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
    --font-serif: system-ui, -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", sans-serif;
    --font-mono: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Mono', monospace;
  }

  html {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    font-family: var(--font-serif);
    font-size: 13px;
    color: var(--black);
    background: var(--gray-100);
    line-height: 1.5;
    letter-spacing: 0.01em;
  }

  a { color: var(--black); text-decoration: none; }
  a:hover { text-decoration: underline; }

  .header {
    padding: 40px 24px 28px;
    max-width: 1500px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }

  .logotype {
    font-family: var(--font-serif);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.24em;
    text-transform: uppercase;
  }

  .logotype a { text-decoration: none; }

  .header-nav {
    font-family: var(--font-serif);
    font-size: 11px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--gray-500);
    display: flex;
    gap: 16px;
  }

  .header-nav a { color: var(--gray-500); }

  .header-nav a:hover { color: var(--black); }
  .header-nav a.active { color: var(--black); }

  .filters {
    padding: 20px 24px;
    max-width: 1500px;
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
    font-size: 10px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--gray-500);
    margin-bottom: 0.5rem;
    display: block;
  }

  .filter-select {
    width: 100%;
    font-family: var(--font-serif);
    font-size: 13px;
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
    padding: 12px 24px;
    max-width: 1500px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .results-count {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--gray-500);
    letter-spacing: 0.04em;
  }

  .clear-filters {
    font-family: var(--font-mono);
    font-size: 10px;
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
    max-width: 1500px;
    margin: 0 auto;
    padding: 0 24px 56px;
  }

  table { width: 100%; border-collapse: collapse; }

  thead th {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 0.14em;
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
    font-size: 13px;
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
    font-size: 11px;
    letter-spacing: 0.02em;
    color: var(--gray-600);
    white-space: nowrap;
  }

  td.agency { font-size: 11px; color: var(--gray-600); }
  td.geology { font-size: 11px; color: var(--gray-600); }

  td.acreage {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--gray-600);
    text-align: right;
    white-space: nowrap;
  }

  td.native-lands {
    font-size: 11px;
    color: var(--gray-600);
    max-width: 200px;
  }

  .empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: var(--gray-400);
    font-style: italic;
    font-size: 13px;
    display: none;
  }

  footer {
    max-width: 1500px;
    margin: 0 auto;
    padding: 12px 24px 40px;
    border-top: 1px solid var(--gray-200);
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--gray-400);
    letter-spacing: 0.04em;
  }

  @media (max-width: 900px) {
    .filter-group { min-width: 150px; }
    td.native-lands, th.native-lands-col { display: none; }
  }

  @media (max-width: 600px) {
    .header { padding: 24px 18px 20px; }
    .filters { padding: 16px 18px; }
    .filter-row { gap: 1rem; }
    .filter-group { min-width: 100%; }
    .results-bar { padding: 10px 18px; }
    .map-wrap { padding: 0 18px 16px; }
    .index-table { padding: 0 18px 40px; overflow-x: auto; }
    table { min-width: 600px; }
    footer { padding: 12px 18px 32px; }
  }

  /* map */
  .map-wrap {
    max-width: 1500px;
    margin: 0 auto;
    padding: 0 24px 20px;
  }
  #pli-map {
    width: 100%;
    height: 300px;
    border: 1px solid var(--gray-200);
  }
  @media (min-width: 720px) { #pli-map { height: 380px; } }
  .pli-marker { background: none; border: none; }
  .pli-dot {
    width: 9px;
    height: 9px;
    background: var(--black);
    border-radius: 50%;
    border: 2px solid var(--white);
    box-shadow: 0 0 0 1px rgba(0,0,0,0.2);
    cursor: pointer;
    transition: transform 0.1s;
  }
  .pli-marker:hover .pli-dot,
  .pli-marker.active .pli-dot { transform: scale(1.8); }
  .leaflet-popup-content-wrapper {
    border-radius: 2px;
    box-shadow: 0 1px 8px rgba(0,0,0,0.1);
    font-family: var(--font-serif);
  }
  .leaflet-popup-content {
    margin: 8px 12px;
    font-size: 12px;
    line-height: 1.4;
  }
  .leaflet-popup-content a { color: var(--black); font-weight: 500; text-decoration: none; }
  .leaflet-popup-content a:hover { text-decoration: underline; }
  @keyframes pli-row-flash {
    0%   { background: var(--gray-200); }
    100% { background: transparent; }
  }
  tr.map-highlight { animation: pli-row-flash 1.2s ease-out forwards; }

  .intro-wrap {
    max-width: 1500px;
    margin: 0 auto;
    padding: 12px 24px 16px;
    border-top: 1px solid var(--gray-200);
  }
  .intro-text {
    font-size: 13px;
    color: var(--gray-500);
  }
  @media (max-width: 600px) {
    .intro-wrap { padding: 10px 18px 12px; }
  }'''


def make_sites_index_page(all_sites, meta):
    import re as _re
    import hashlib

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
                'properties': {'slug': slug, 'nation': n, 'color': nation_colors.get(n, '#8a8478')},
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
            # Use archive tif filename for f field (matches Commons naming, which uses zero-padded sequence numbers)
            archive_name = f'Public Lands Institute - {site["name"]} - {i + 1:03d}.tif'
            entries.append({
                'f': archive_name,
                'd': img.get('date', '') or '',
                'thumb': thumb_path if os.path.exists(thumb_path) else '',
                'large': large_path if os.path.exists(large_path) else '',
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
:root {{ --sand: #f2ede6; --ink: #1a1a18; --moss: #4a5e3a; --stone: #8a8478; --panel-w: 440px; }}
html, body {{ height: 100%; font-family: 'Inter', sans-serif; background: var(--ink); }}
#map {{ position: fixed; inset: 0; }}
#wordmark {{ position: fixed; top: 28px; left: 32px; z-index: 10; pointer-events: none; }}
#wordmark h1 {{ font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 300; letter-spacing: 0.2em; text-transform: uppercase; color: var(--sand); opacity: 0.85; line-height: 1; }}
#site-count {{ position: fixed; top: 28px; right: 32px; z-index: 10; color: rgba(242,237,230,0.3); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; font-weight: 300; }}
#layers {{ position: fixed; bottom: 32px; left: 32px; z-index: 10; display: flex; flex-direction: column; gap: 6px; }}
.layer-btn {{ background: rgba(26,26,24,0.72); border: 1px solid rgba(242,237,230,0.2); color: var(--sand); font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; padding: 6px 12px; cursor: pointer; backdrop-filter: blur(8px); transition: border-color 0.2s; text-align: left; }}
.layer-btn:hover {{ border-color: rgba(242,237,230,0.5); }}
.layer-btn.active {{ color: #c8ddb8; border-color: #c8ddb8; background: rgba(26,26,24,0.9); }}
#legend {{ position: fixed; bottom: 32px; right: 32px; z-index: 10; background: rgba(26,26,24,0.85); backdrop-filter: blur(8px); border: 1px solid rgba(242,237,230,0.15); padding: 14px 16px; min-width: 200px; display: none; }}
#legend.visible {{ display: block; }}
#legend-title {{ font-size: 10px; font-weight: 500; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(242,237,230,0.45); margin-bottom: 10px; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 11px; font-weight: 300; color: rgba(242,237,230,0.75); }}
.legend-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
#panel {{ position: fixed; top: 0; right: 0; width: var(--panel-w); height: 100%; background: var(--sand); z-index: 20; transform: translateX(100%); transition: transform 0.4s cubic-bezier(0.16,1,0.3,1); overflow-y: auto; overflow-x: hidden; }}
#panel.open {{ transform: translateX(0); }}
#panel-close {{ position: sticky; top: 0; z-index: 5; display: flex; justify-content: flex-end; padding: 16px 20px 0; background: var(--sand); }}
#panel-close button {{ background: none; border: none; cursor: pointer; color: var(--stone); font-size: 20px; line-height: 1; padding: 4px; }}
#panel-close button:hover {{ color: var(--ink); }}
#panel-body {{ padding: 8px 32px 48px; }}
.panel-site-name {{ font-family: 'Inter', sans-serif; font-size: 22px; font-weight: 300; letter-spacing: -0.01em; color: var(--ink); line-height: 1.2; margin-bottom: 4px; }}
.panel-state {{ font-size: 11px; font-weight: 400; letter-spacing: 0.12em; text-transform: uppercase; color: var(--stone); margin-bottom: 20px; }}
.photo-grid {{ display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 180px; gap: 3px; margin-bottom: 6px; }}
.photo-thumb {{ background: #ccc8c0; cursor: pointer; overflow: hidden; }}
.photo-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0; transition: opacity 0.25s; }}
.photo-thumb img.loaded {{ opacity: 1; }}
.photo-thumb:hover img {{ opacity: 0.75; }}
.photo-grid-more {{ font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--stone); margin-bottom: 20px; text-align: right; }}
.photo-grid-more a {{ color: var(--moss); text-decoration: none; border-bottom: 1px solid var(--moss); }}
.panel-section {{ margin-bottom: 20px; border-top: 1px solid rgba(26,26,24,0.12); padding-top: 16px; }}
.panel-section-label {{ font-size: 10px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--stone); margin-bottom: 8px; }}
.panel-section p {{ font-size: 13.5px; font-weight: 300; line-height: 1.7; color: #2e2e2a; }}
.geo-block {{ margin-bottom: 20px; border-top: 1px solid rgba(26,26,24,0.12); padding-top: 16px; }}
.geo-label {{ font-size: 10px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--stone); margin-bottom: 10px; }}
.geo-era-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
.geo-swatch {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
.geo-era-name {{ font-size: 14px; font-weight: 300; color: var(--ink); }}
.geo-mya {{ font-size: 11px; font-weight: 300; color: var(--stone); margin-left: auto; letter-spacing: 0.04em; }}
.geo-bar-wrap {{ position: relative; height: 3px; background: rgba(26,26,24,0.08); margin-bottom: 8px; border-radius: 2px; }}
.geo-bar-fill {{ position: absolute; right: 0; top: 0; height: 100%; border-radius: 2px; }}
.geo-prose {{ font-size: 12px; font-weight: 300; line-height: 1.6; color: var(--stone); }}
#lightbox {{ position: fixed; inset: 0; z-index: 100; background: rgba(14,14,12,0.97); display: none; flex-direction: column; }}
#lightbox.open {{ display: flex; }}
#lb-img-wrap {{ flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 56px 72px 0; position: relative; }}
#lb-img {{ max-width: 100%; max-height: 100%; object-fit: contain; display: block; opacity: 0; transition: opacity 0.2s; }}
#lb-img.loaded {{ opacity: 1; }}
#lb-spinner {{ position: absolute; color: rgba(242,237,230,0.3); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; }}
#lb-bar {{ display: flex; align-items: center; justify-content: space-between; padding: 14px 72px 20px; gap: 24px; flex-shrink: 0; border-top: 1px solid rgba(242,237,230,0.07); }}
#lb-meta {{ flex: 1; min-width: 0; }}
#lb-filename {{ font-size: 12px; font-weight: 300; color: rgba(242,237,230,0.55); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }}
#lb-date {{ font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(242,237,230,0.3); }}
#lb-actions {{ display: flex; gap: 8px; flex-shrink: 0; }}
.lb-action {{ font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; text-decoration: none; padding: 5px 12px; border: 1px solid rgba(242,237,230,0.3); color: rgba(242,237,230,0.65); transition: border-color 0.15s, color 0.15s; white-space: nowrap; }}
.lb-action:hover {{ border-color: rgba(242,237,230,0.75); color: var(--sand); }}
#lb-close {{ position: fixed; top: 18px; right: 24px; z-index: 101; background: none; border: none; cursor: pointer; color: rgba(242,237,230,0.4); font-size: 22px; line-height: 1; transition: color 0.15s; }}
#lb-close:hover {{ color: var(--sand); }}
#lb-prev, #lb-next {{ position: fixed; top: 50%; transform: translateY(-50%); z-index: 101; background: none; border: none; cursor: pointer; color: rgba(242,237,230,0.3); font-size: 36px; padding: 16px; transition: color 0.15s; line-height: 1; }}
#lb-prev {{ left: 8px; }} #lb-next {{ right: 8px; }}
#lb-prev:hover, #lb-next:hover {{ color: var(--sand); }}
#lb-counter {{ position: fixed; top: 22px; left: 50%; transform: translateX(-50%); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(242,237,230,0.25); }}
.maplibregl-popup-content {{ background: var(--ink); color: var(--sand); font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 300; padding: 8px 12px; border-radius: 0; box-shadow: none; }}
.maplibregl-popup-tip {{ border-top-color: var(--ink) !important; }}
.maplibregl-ctrl-attrib {{ font-size: 9px; opacity: 0.4; }}
@media (max-width: 640px) {{
  :root {{ --panel-w: 100%; }}
  #wordmark {{ top: 16px; left: 16px; }}
  #wordmark h1 {{ font-size: 11px; }}
  #site-count {{ top: 16px; right: 16px; font-size: 10px; }}
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
<div id="site-count"></div>
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
      <a id="lb-raw" class="lb-action" href="#" target="_blank" rel="noopener">RAW File</a>
      <a id="lb-xml" class="lb-action" href="#" target="_blank" rel="noopener">XML</a>
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
  ["Paleogene","#d4704a"],["Neogene","#c85a8a"],["Quaternary","#8a8478"],["Pleistocene","#8a8478"],
];
const GEO_TIMESCALE = [
  ["Cambrian","#a0522d",541,485],["Ordovician","#c8a86e",485,444],["Silurian","#7ecfc0",444,419],
  ["Devonian","#4aaa78",419,359],["Mississippian","#3d7fbf",359,323],["Pennsylvanian","#5d5abf",323,299],
  ["Permian","#9b59b6",299,252],["Triassic","#e07050",252,201],["Jurassic","#c8a840",201,145],
  ["Cretaceous","#d4b840",145,66],["Paleogene","#d4704a",66,23],["Neogene","#c85a8a",23,2.6],
  ["Quaternary","#8a8478",2.6,0],["Pleistocene","#8a8478",2.6,0.01],
];
const EARTH_AGE = 541;
const GEOLOGY_LEGEND = [
  ["Ordovician \xb7 485–444 Mya","#c8a86e"],["Silurian \xb7 444–419 Mya","#7ecfc0"],["Devonian \xb7 419–359 Mya","#4aaa78"],
  ["Mississippian \xb7 359–323 Mya","#3d7fbf"],["Pennsylvanian \xb7 323–299 Mya","#5d5abf"],
  ["Permian \xb7 299–252 Mya","#9b59b6"],["Cretaceous \xb7 145–66 Mya","#d4b840"],
  ["Paleogene \xb7 66–23 Mya","#d4704a"],["Quaternary \xb7 <2.6 Mya","#8a8478"],
];
const AGENCY_ENTRIES = [
  ["National Park Service","#5c9e6a"],["U.S. Fish & Wildlife Service","#4a8a9e"],
  ["State Park / Preserve","#9e7a4a"],["Nature Conservancy / Private","#7a5a8a"],["Other","#5a5a52"],
];
const NATIVE_LEGEND = NATION_LIST.map(n => [n, NATION_COLORS[n]||'#8a8478']);
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
  if (activeLayer==='native')  return p.primary_nation ? (NATION_COLORS[p.primary_nation]||'#8a8478') : '#3a3a38';
  if (activeLayer==='shadow')  {{ const l=(p.shadow_history||'').length; return l>800?'#c85a2a':l>400?'#c8904a':'#8a6a3a'; }}
  return '#f2ede6';
}}
function buildDotFeatures() {{
  return {{ ...SITES, features: SITES.features.map(f => ({{...f, properties:{{...f.properties, _color:dotColor(f.properties)}}}}) ) }};
}}
const map = new maplibregl.Map({{
  container:'map',
  style:{{ version:8, sources:{{ base:{{ type:'raster', tiles:['https://basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}@2x.png'], tileSize:256, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>' }} }}, layers:[{{id:'bg',type:'raster',source:'base'}}] }},
  center:[-89,38.5], zoom:4.4, minZoom:2, maxZoom:18,
}});
document.getElementById('site-count').textContent = SITES.features.length+' sites';
map.on('load', () => {{
  map.addSource('sites', {{ type:'geojson', data:buildDotFeatures() }});
  map.addSource('nations', {{ type:'geojson', data:NATIONS_GJ }});
  map.addLayer({{ id:'nations-dot', type:'circle', source:'nations',
    layout:{{ visibility:'none' }},
    paint:{{ 'circle-radius':['interpolate',['linear'],['zoom'],3,4.5,10,8],
            'circle-color':['get','color'], 'circle-opacity':0.85,
            'circle-stroke-color':'rgba(242,237,230,0.2)','circle-stroke-width':1 }} }});
  map.addLayer({{ id:'sites-hit', type:'circle', source:'sites', paint:{{ 'circle-radius':16,'circle-opacity':0,'circle-stroke-width':0 }} }});
  map.addLayer({{ id:'sites-dot', type:'circle', source:'sites',
    paint:{{ 'circle-radius':['interpolate',['linear'],['zoom'],3,4.5,10,8],
            'circle-color':['get','_color'],'circle-opacity':0.88,
            'circle-stroke-color':'rgba(242,237,230,0.2)','circle-stroke-width':1 }} }});
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
      const q = encodeURIComponent('Public Lands Institute '+props.name);
      gridHTML += '<p class="photo-grid-more"><a href="https://commons.wikimedia.org/w/index.php?title=Special:MediaSearch&search='+q+'" target="_blank">View all '+photos.length+' photos →</a></p>';
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
    '<p class="panel-site-name">'+props.name+'</p>'+
    '<p class="panel-state">'+state+'</p>'+
    gridHTML+
    sections;
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
  const fe = p.f.replace(/ /g,'_');
  document.getElementById('lb-commons').href = 'https://commons.wikimedia.org/wiki/File:'+fe;
  document.getElementById('lb-raw').href     = 'https://commons.wikimedia.org/wiki/Special:FilePath/'+fe;
  document.getElementById('lb-xml').href     = 'https://commons.wikimedia.org/wiki/Special:Export/File:'+fe;
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


# ── Index page builder ─────────────────────────────────────────────────────────

def make_index_page(all_sites, meta):
    import re as _re

    def acreage_int(s):
        m = _re.search(r'[\d,]+', str(s))
        return int(m.group().replace(',', '')) if m else 0

    rows = ''
    states = set()
    agency_types = set()
    for site in all_sites:
        images = get_all_images_for_site(site)
        if not images:
            continue
        first_img = images[0]['jpg'] if images else None
        m_data = meta.get(site['slug'], {})
        agency_type = m_data.get('agency_type', '')
        acr = acreage_int(site.get('acreage', '0'))
        states.add(site['state'])
        if agency_type:
            agency_types.add(agency_type)

        thumb_html = ''
        if first_img:
            all_jpgs = json.dumps([img['jpg'] for img in images])
            thumb_html = f'''    <a class="loc-thumb" href="sites/{site["slug"]}.html" data-images='{all_jpgs}'>
      <img src="{first_img}" alt="{site["name"]} I" loading="lazy"/>
    </a>\n'''

        PRIMARY_INDEX = {'geological_age', 'acreage', 'shadow_history', 'gps'}
        EXTRA_INDEX   = {'epoch', 'native_lands', 'displacement_tenure'}
        field_rows = ''
        has_extra  = False
        for key, label in FIELDS:
            if key not in PRIMARY_INDEX and key not in EXTRA_INDEX:
                continue
            val = site.get(key, '')
            if not val:
                continue
            if key == 'gps':
                lat = site.get('lat', '')
                lng = site.get('lng', '')
                val = f'<a class="gps-link" href="https://maps.google.com/?q={lat},{lng}" target="_blank" rel="noopener">{val}</a>'
            if key in EXTRA_INDEX:
                field_rows += f'<dt class="extra">{label}</dt><dd class="extra">{val}</dd>'
                has_extra = True
            else:
                field_rows += f'<dt>{label}</dt><dd>{val}</dd>'

        toggle_html = '    <button class="site-data-toggle">More</button>\n' if has_extra else ''

        inat_key = f'{site["slug"]}:{site.get("inat_radius_km", 5)}'
        inat_species = INAT_CACHE.get(inat_key, {}).get('total_species', 0)
        if inat_species:
            field_rows += f'<dt>Species observed</dt><dd>{inat_species:,} (iNaturalist)</dd>'

        rows += f'''  <div class="location-row" data-state="{site["state"]}" data-agency-type="{agency_type}" data-acreage="{acr}">
    <div class="location-row-header">
      <span class="loc-name">{site["name"]}<span class="loc-state">{site["state"]}</span></span>
      <a class="loc-link" href="sites/{site["slug"]}.html">{len(images)} images</a>
    </div>
{thumb_html}    <dl class="site-data">{field_rows}</dl>
{toggle_html}  </div>\n'''

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
<title>Sites — Public Lands Institute</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="An ongoing photographic index and open-access archive of American public lands. CC0 Public Domain." name="description"/>
<meta content="index, follow" name="robots"/>
<meta property="og:title" content="Sites — Public Lands Institute"/>
<meta property="og:description" content="An ongoing photographic index and open-access archive of American public lands, with geological, ecological, Indigenous land tenure, and shadow history documentation. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/sites.html"/>
<meta property="og:site_name" content="Public Lands Institute"/>
<link href="https://publiclandsinstitute.net/sites.html" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
<style>
{SHARED_CSS}
  .intro-text {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 20px;
  }}
  .filter-bar {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 8px 0 12px;
    margin-bottom: 4px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--bg);
    z-index: 10;
  }}
  .sort-btn {{
    font-family: inherit;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--muted);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
  }}
  .sort-btn:hover {{ color: var(--fg); }}
  .filter-count {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
  }}
  .filter-controls {{ display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }}
  .filter-select-sm {{
    font-family: inherit;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
    background: none;
    border: none;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    padding: 0 1.25rem 0 0;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%23777777'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0 center;
  }}
  .filter-select-sm:focus {{ outline: none; }}
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
    display: inline-flex;
    align-items: center;
    min-height: 44px;
  }}
  .gps-link {{
    color: inherit;
    text-decoration: none;
    display: inline-block;
    padding: 11px 0;
    margin: -11px 0;
  }}
  .gps-link:hover {{ text-decoration: underline; }}
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
    .site-data {{ grid-template-columns: 1fr; }}
    .site-data dt {{ padding-bottom: 0; }}
    .site-data dd {{ padding-left: 0; padding-top: 1px; margin-bottom: 6px; }}
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
  .site-data-toggle {{ display: none; }}
  @media (max-width: 480px) {{
    .site-data .extra {{ display: none; }}
    .site-data.expanded .extra {{ display: block; }}
    .site-data-toggle {{
      display: block;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
      background: none;
      border: none;
      padding: 4px 0 8px 0;
      cursor: pointer;
      font-family: inherit;
    }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="index.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="#" class="active">Sites</a>
    <a href="archive.html">Archive</a>
    <a href="about.html">About</a>
  </nav>
</header>
<div class="divider"></div>
<div class="filter-bar">
  <div class="filter-controls">
    <button class="sort-btn" id="sort-toggle">Alphabetical</button>
    <select id="filter-state-sites" class="filter-select-sm"><option value="">All states</option></select>
    <select id="filter-type-sites" class="filter-select-sm"><option value="">All types</option></select>
  </div>
  <span class="filter-count" id="filter-count"></span>
</div>
<div id="locations-container">
{rows}</div>
<footer>
  <span>Public Lands Institute \u2014 ongoing project</span>
  <span>US \u00b7 established MMXXV</span>
</footer>
</div>
<script>
(function () {{
  document.querySelectorAll('.loc-thumb[data-images]').forEach(function (thumb) {{
    var imgs = JSON.parse(thumb.dataset.images);
    if (imgs.length < 2) return;
    var idx = 0;
    var img = thumb.querySelector('img');
    var x0 = 0, y0 = 0, didSwipe = false;
    thumb.addEventListener('touchstart', function (e) {{
      if (e.touches.length !== 1) return;
      x0 = e.touches[0].clientX;
      y0 = e.touches[0].clientY;
      didSwipe = false;
    }}, {{ passive: true }});
    thumb.addEventListener('touchend', function (e) {{
      if (!e.changedTouches.length) return;
      var dx = e.changedTouches[0].clientX - x0;
      var dy = e.changedTouches[0].clientY - y0;
      if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) {{
        didSwipe = true;
        idx = (idx + (dx < 0 ? 1 : -1) + imgs.length) % imgs.length;
        img.src = imgs[idx];
      }}
    }}, {{ passive: true }});
    thumb.addEventListener('click', function (e) {{
      if (didSwipe) {{ e.preventDefault(); didSwipe = false; }}
    }});
  }});
  document.querySelectorAll('.site-data-toggle').forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      var dl = btn.previousElementSibling;
      var expanded = dl.classList.toggle('expanded');
      btn.textContent = expanded ? 'Less' : 'More';
    }});
  }});
}})();

(function () {{
  var rows = Array.from(document.querySelectorAll('.location-row'));
  var originalOrder = rows.slice();
  var sortMode = 'recent';
  var btn = document.getElementById('sort-toggle');
  var countEl = document.getElementById('filter-count');
  var stateSelect = document.getElementById('filter-state-sites');
  var typeSelect = document.getElementById('filter-type-sites');

  var states = [], types = [];
  rows.forEach(function (row) {{
    var s = row.dataset.state;
    var t = row.dataset.agencyType;
    if (s && states.indexOf(s) === -1) states.push(s);
    if (t && types.indexOf(t) === -1) types.push(t);
  }});
  states.sort().forEach(function (s) {{
    var opt = document.createElement('option');
    opt.value = s; opt.textContent = s;
    stateSelect.appendChild(opt);
  }});
  types.sort().forEach(function (t) {{
    var opt = document.createElement('option');
    opt.value = t; opt.textContent = t;
    typeSelect.appendChild(opt);
  }});

  function applyFilters() {{
    var sv = stateSelect.value;
    var tv = typeSelect.value;
    rows.forEach(function (row) {{
      var match = (!sv || row.dataset.state === sv) && (!tv || row.dataset.agencyType === tv);
      row.style.display = match ? '' : 'none';
    }});
    renderSort();
  }}

  function renderSort() {{
    var container = document.getElementById('locations-container');
    if (!container) return;
    var visible = rows.filter(function (r) {{ return r.style.display !== 'none'; }});
    if (sortMode === 'alpha') {{
      visible.sort(function (a, b) {{
        var na = a.querySelector('.loc-name').childNodes[0].nodeValue.trim().toLowerCase();
        var nb = b.querySelector('.loc-name').childNodes[0].nodeValue.trim().toLowerCase();
        return na < nb ? -1 : na > nb ? 1 : 0;
      }});
    }} else {{
      visible = originalOrder.filter(function (r) {{ return r.style.display !== 'none'; }});
    }}
    visible.forEach(function (row) {{ container.appendChild(row); }});
    countEl.textContent = visible.length + ' sites';
  }}

  btn.addEventListener('click', function () {{
    sortMode = sortMode === 'recent' ? 'alpha' : 'recent';
    btn.textContent = sortMode === 'recent' ? 'Alphabetical' : 'Recent';
    renderSort();
  }});

  stateSelect.addEventListener('change', applyFilters);
  typeSelect.addEventListener('change', applyFilters);

  countEl.textContent = rows.length + ' sites';
  renderSort();
}})();
</script>
</body>
</html>'''


# ── Combined prototype (index2.html) ───────────────────────────────────────────

def make_combined_page(all_sites, meta):
    import re as _re

    def acreage_int(s):
        m = _re.search(r'[\d,]+', str(s))
        return int(m.group().replace(',', '')) if m else 0

    # JS array for Leaflet map
    js_sites = []
    for site in all_sites:
        slug = site['slug']
        m = meta.get(slug, {})
        js_sites.append({
            'slug': slug,
            'name': site['name'],
            'stateAbbr': site['state'],
            'agencyType': m.get('agency_type', ''),
            'lat': site.get('lat', None),
            'lng': site.get('lng', None),
            'url': f'https://publiclandsinstitute.net/sites/{slug}.html',
        })
    js_array = json.dumps(js_sites, indent=2, ensure_ascii=False)

    # Card rows
    rows = ''
    for site in all_sites:
        images = get_all_images_for_site(site)
        if not images:
            continue
        m_data = meta.get(site['slug'], {})
        agency_type = m_data.get('agency_type', '')
        acr = acreage_int(site.get('acreage', '0'))

        PRIMARY_KEYS   = {'geological_age', 'acreage'}
        EXPANDABLE_KEYS = {'epoch', 'ecology', 'native_lands', 'displacement_tenure', 'shadow_history', 'gps'}
        field_rows = ''
        for key, label in FIELDS:
            val = site.get(key, '')
            if not val:
                continue
            if key == 'gps':
                lat = site.get('lat', '')
                lng = site.get('lng', '')
                val = f'<a class="gps-link" href="https://maps.google.com/?q={lat},{lng}" target="_blank" rel="noopener">{val}</a>'
            if key in PRIMARY_KEYS:
                field_rows += f'<dt>{label}</dt><dd>{val}</dd>'
            elif key in EXPANDABLE_KEYS:
                field_rows += f'<dt class="expandable">{label}</dt><dd class="expandable">{val}</dd>'

        inat_key = f'{site["slug"]}:{site.get("inat_radius_km", 5)}'
        inat_species = INAT_CACHE.get(inat_key, {}).get('total_species', 0)
        if inat_species:
            field_rows += f'<dt class="expandable">Species observed</dt><dd class="expandable">{inat_species:,} (iNaturalist)</dd>'

        rows += f'''  <div class="location-row" data-slug="{site["slug"]}" data-state="{site["state"]}" data-agency-type="{agency_type}" data-acreage="{acr}">
    <div class="location-row-header">
      <span class="loc-name">{site["name"]}<span class="loc-state">{site["state"]}</span><span class="expand-ind">+</span></span>
      <a class="loc-link" href="sites/{site["slug"]}.html">{len(images)} images</a>
    </div>
    <dl class="site-data">{field_rows}</dl>
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
<meta content="An ongoing photographic index and open-access archive of American public lands. CC0 Public Domain." name="description"/>
<meta content="index, follow" name="robots"/>
<meta property="og:title" content="Public Lands Institute"/>
<meta property="og:description" content="An ongoing photographic index and open-access archive of American public lands. CC0 Public Domain."/>
<meta property="og:type" content="website"/>
<meta property="og:url" content="https://publiclandsinstitute.net/"/>
<meta property="og:site_name" content="Public Lands Institute"/>
<link href="https://publiclandsinstitute.net/" rel="canonical"/>
<link href="/favicon-32.png" rel="icon" sizes="32x32" type="image/png"/>
<link href="/favicon-16.png" rel="icon" sizes="16x16" type="image/png"/>
<link href="/apple-touch-icon.png" rel="apple-touch-icon"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
{SHARED_CSS}
  /* ── intro ──────────────────────────────────────────────────── */
  .intro-text {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 20px;
  }}

  /* ── map ────────────────────────────────────────────────────── */
  #pli-map {{
    width: 100%;
    height: 240px;
    border: 1px solid var(--border);
    margin-bottom: 0;
  }}
  @media (min-width: 720px) {{ #pli-map {{ height: 340px; }} }}
  .pli-marker {{ background: none; border: none; }}
  .pli-dot {{
    width: 9px; height: 9px;
    background: var(--fg);
    border-radius: 50%;
    border: 2px solid #fff;
    box-shadow: 0 0 0 1px rgba(0,0,0,0.2);
    cursor: pointer;
    transition: transform 0.1s;
  }}
  .pli-marker:hover .pli-dot,
  .pli-marker.active .pli-dot {{ transform: scale(1.8); }}
  .leaflet-popup-content-wrapper {{
    border-radius: 2px;
    box-shadow: 0 1px 8px rgba(0,0,0,0.1);
    font-family: system-ui, sans-serif;
  }}
  .leaflet-popup-content {{
    margin: 8px 12px;
    font-size: 12px;
    line-height: 1.4;
  }}
  .leaflet-popup-content a {{ color: var(--fg); font-weight: 500; text-decoration: none; }}
  .leaflet-popup-content a:hover {{ text-decoration: underline; }}

  /* ── filter bar ─────────────────────────────────────────────── */
  .filter-bar {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 8px 0 12px;
    margin-top: 12px;
    margin-bottom: 4px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--bg);
    z-index: 10;
  }}
  .sort-btn {{
    font-family: inherit;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--muted);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
  }}
  .sort-btn:hover {{ color: var(--fg); }}
  .filter-count {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
  }}

  /* ── cards ──────────────────────────────────────────────────── */
  @keyframes card-flash {{
    0%   {{ background: var(--border); }}
    100% {{ background: transparent; }}
  }}
  .location-row {{
    border-top: 1px solid var(--border);
    padding: 10px 0 14px 0;
  }}
  .location-row.map-highlight {{ animation: card-flash 1.2s ease-out forwards; }}
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
    display: inline-flex;
    align-items: center;
    min-height: 44px;
  }}
  .gps-link {{
    color: inherit;
    text-decoration: none;
    display: inline-block;
    padding: 11px 0;
    margin: -11px 0;
  }}
  .gps-link:hover {{ text-decoration: underline; }}
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
  /* expand behaviour */
  .site-data .expandable {{ display: none; }}
  .location-row.open .site-data .expandable {{ display: block; }}
  .loc-name {{ cursor: pointer; }}
  .expand-ind {{
    font-size: 10px;
    color: var(--muted);
    margin-left: 6px;
    font-weight: 400;
    font-style: normal;
  }}
  @media (max-width: 480px) {{
    .site-data {{ grid-template-columns: 1fr; }}
    .site-data dt {{ padding-bottom: 0; }}
    .site-data dd {{ padding-left: 0; padding-top: 1px; margin-bottom: 6px; }}
  }}
</style>
</head>
<body>
<div class="page">
<header>
  <div class="logotype"><a href="index2.html">Public Lands Institute</a></div>
  <nav class="header-nav">
    <a href="archive2.html">Archive</a>
  </nav>
</header>
<div class="divider"></div>
<div id="pli-map"></div>
<div class="filter-bar">
  <button class="sort-btn" id="sort-toggle">Alphabetical</button>
  <span class="filter-count" id="filter-count"></span>
</div>
<div id="locations-container">
{rows}</div>
<footer>
  <span>Public Lands Institute — ongoing project</span>
  <span>CC0 Public Domain</span>
</footer>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// ── map ───────────────────────────────────────────────────────────────────────
const sites = {js_array};
const map = L.map('pli-map', {{ zoomControl: true, scrollWheelZoom: false, tap: false }});
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: 'abcd',
  maxZoom: 19
}}).addTo(map);

const allBounds = [];
sites.forEach(s => {{
  if (!s.lat || !s.lng) return;
  const icon = L.divIcon({{ className: 'pli-marker', html: '<div class="pli-dot"></div>', iconSize: [9, 9], iconAnchor: [4, 4] }});
  const marker = L.marker([s.lat, s.lng], {{ icon, title: s.name }}).addTo(map);
  marker.on('click', () => {{
    const card = document.querySelector(`.location-row[data-slug="${{s.slug}}"]`);
    if (card) {{
      card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      card.classList.remove('map-highlight');
      void card.offsetWidth;
      card.classList.add('map-highlight');
    }}
  }});
  allBounds.push([s.lat, s.lng]);
}});
if (allBounds.length) map.fitBounds(allBounds, {{ padding: [20, 20] }});
</script>
<script>
// ── expand ────────────────────────────────────────────────────────────────────
(function () {{
  document.querySelectorAll('.location-row').forEach(function (row) {{
    var nameEl = row.querySelector('.loc-name');
    var ind = row.querySelector('.expand-ind');
    nameEl.addEventListener('click', function (e) {{
      var open = row.classList.toggle('open');
      if (ind) ind.textContent = open ? '−' : '+';
    }});
  }});
}})();

// ── sort ──────────────────────────────────────────────────────────────────────
(function () {{
  var rows = Array.from(document.querySelectorAll('.location-row'));
  var originalOrder = rows.slice();
  var sortMode = 'recent';
  var btn = document.getElementById('sort-toggle');
  var countEl = document.getElementById('filter-count');

  function sortRows() {{
    var container = document.getElementById('locations-container');
    if (!container) return;
    if (sortMode === 'alpha') {{
      rows.slice().sort(function (a, b) {{
        var na = a.querySelector('.loc-name').childNodes[0].nodeValue.trim().toLowerCase();
        var nb = b.querySelector('.loc-name').childNodes[0].nodeValue.trim().toLowerCase();
        return na < nb ? -1 : na > nb ? 1 : 0;
      }}).forEach(function (row) {{ container.appendChild(row); }});
    }} else {{
      originalOrder.forEach(function (row) {{ container.appendChild(row); }});
    }}
  }}

  btn.addEventListener('click', function () {{
    sortMode = sortMode === 'recent' ? 'alpha' : 'recent';
    btn.textContent = sortMode === 'recent' ? 'Alphabetical' : 'Recent';
    sortRows();
  }});

  countEl.textContent = rows.length + ' sites';
  sortRows();
}})();
</script>
</body>
</html>'''


def make_archive2_page(all_sites):
    html = make_archive_page(all_sites)
    return html.replace(
        '<a href="index.html">Public Lands Institute</a>',
        '<a href="index2.html">Public Lands Institute</a>'
    ).replace(
        '<a href="archive.html" class="active">Archive</a>',
        '<a href="archive2.html" class="active">Archive</a>'
    )


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

print('\nGenerating sites.html...')
with open('sites.html', 'w') as f:
    f.write(make_index_page(sites, SITES_META))
print('  sites.html')

print('\nGenerating about.html...')
with open('about.html', 'w') as f:
    f.write(make_about_page(sites))
print('  about.html')

print(f'\nDone \u2014 {len(sites)} site pages + archive + index + sites index.')

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
