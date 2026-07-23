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
  archive.html          plain-text download index (all rows, per-site sections)
  photographs.html      visual feed grouped by site
  about.html            stats sentence only — the rest of the page is hand-maintained
  sitemap.xml           lastmod = each source file's actual last-modified date
  data/sites-map.js     SITES / NATIONS_GJ / PHOTOS / NATION_COLORS / NATION_LIST,
                        loaded by index.html with a ?v= content-hash query string

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
  .gps-link:hover { text-decoration: underline; }'''


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
        _search_key = f'{site["name"]} {site["state"]}'.lower()
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

ALL_TARGETS = ['archive', 'photographs', 'about', 'sitemap', 'mapjs']


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    validate = '--no-validate' not in argv
    targets = args or ALL_TARGETS

    sites, meta, photos, nations_gj = load_data()

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
