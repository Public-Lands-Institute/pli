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
  sites_meta.json       agency / agency_type / territory data
  data/photos.json      per-site image entries, keyed by slug
                        entry shape: f, d, thumb, large, t, r, x, c
  data/nations.geojson  per-(site, nation) point features for the map's native layer

Outputs:
  sites/<slug>.html     one page per site (record column + photo pane)
  archive.html          plain-text download index (all rows, per-site sections)
  photographs.html      visual feed grouped by site
  about.html            stats sentence only — the rest of the page is hand-maintained
  sitemap.xml           lastmod = each source file's actual last-modified date
  data/sites-map.js     SITES / NATIONS_GJ / PHOTOS / NATION_COLORS / NATION_LIST,
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

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


def load_data():
    with open('sites.json') as f:
        sites = json.load(f)
    with open('sites_meta.json') as f:
        meta = json.load(f)
    with open('data/photos.json') as f:
        photos = json.load(f)
    with open('data/nations.geojson') as f:
        nations_gj = json.load(f)
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

    total = sum(len(g['imgs']) for g in groups)
    n_sites = len(groups)

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
    """Rewrite the stats sentence in about.html in place. Counts unique frames:
    one (slug, camera filename) pair per photograph."""
    frames = set()
    for slug, entries in photos.items():
        for e in entries:
            frames.add((slug, camera_filename(e)))
    n_sites = len(all_sites)
    n_states = len({s['state'] for s in all_sites})
    sentence = (f'The index currently holds {n_sites} sites across {n_states} states, '
                f'documented in {len(frames)} photographs')
    with open('about.html') as f:
        html = f.read()
    new_html, n = STATS_RE.subn(sentence, html)
    if n != 1:
        raise RuntimeError(f'about.html stats sentence: expected 1 match, found {n}')
    if new_html != html:
        with open('about.html', 'w') as f:
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
    # NATION_LIST / NATION_COLORS in first-encounter order across nations.geojson
    nation_list, nation_colors, seen = [], {}, set()
    for f in nations_gj['features']:
        n = f['properties']['nation']
        if n not in seen:
            seen.add(n)
            nation_list.append(n)
            nation_colors[n] = f['properties']['color']
    return (f'const SITES={dump(sites_gj)};\n'
            f'const NATIONS_GJ={dump(nations_gj)};\n'
            f'const PHOTOS={dump(photos)};\n'
            f'const NATION_COLORS={dump(nation_colors)};\n'
            f'const NATION_LIST={dump(nation_list)};\n')


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


# ── Main ───────────────────────────────────────────────────────────────────────

ALL_TARGETS = ['sites', 'archive', 'photographs', 'about', 'mapjs', 'sitemap']


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
    if 'mapjs' in targets:
        version = write_sites_map_js(sites, meta, photos, nations_gj)
        print(f'data/sites-map.js (v={version})')
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
