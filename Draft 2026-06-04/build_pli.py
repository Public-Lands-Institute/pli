import json
from pathlib import Path
from collections import defaultdict

sites_raw = json.load(open('/Users/jordan/PLI/sites.json'))
log       = json.load(open('/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli-commons/upload_log.json'))
photo_map = json.load(open('/tmp/pli_photo_map.json'))

STATE_NAMES = {"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia"}

by_slug = defaultdict(list)
for e in log:
    fname = e['commons_filename']
    pm = photo_map.get(fname, {})
    PLI_THUMBS = '/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli/thumbs'
    def rel(path):
        return 'thumbs/' + '/'.join(path.replace(PLI_THUMBS + '/', '').split('/')) if path else ''
    by_slug[e['slug']].append({
        'f':     fname,
        'd':     e.get('uploaded_at','')[:10],
        'thumb': rel(pm['thumb']) if pm.get('thumb') else '',
        'large': rel(pm['large']) if pm.get('large') else '',
    })

features = []
for s in sites_raw:
    if not (s.get('lat') and s.get('lng')):
        continue
    slug = s['slug']
    photos = by_slug.get(slug, [])
    features.append({
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [s['lng'], s['lat']]},
        'properties': {
            'slug': slug, 'name': s['name'], 'state': s['state'],
            'acreage': s.get('acreage',''), 'ecology': s.get('ecology',''),
            'geology': s.get('geological_age',''), 'hydrology': s.get('hydrology',''),
            'native_lands': s.get('native_lands',''),
            'native_lands_api': json.dumps(s.get('native_lands_api',[])),
            'shadow_history': s.get('shadow_history',''),
            'conservation_status': s.get('conservation_status',''),
            'photo_count': len(photos),
        }
    })

geojson_str = json.dumps({'type':'FeatureCollection','features':features})
photos_str  = json.dumps(dict(by_slug))
state_str   = json.dumps(STATE_NAMES)

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root { --sand: #f2ede6; --ink: #1a1a18; --moss: #4a5e3a; --stone: #8a8478; --panel-w: 440px; }
html, body { height: 100%; font-family: 'Inter', sans-serif; background: var(--ink); }
#map { position: fixed; inset: 0; }
#wordmark { position: fixed; top: 28px; left: 32px; z-index: 10; pointer-events: none; }
#wordmark h1 { font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 300; letter-spacing: 0.2em; text-transform: uppercase; color: var(--sand); opacity: 0.85; line-height: 1; }
#site-count { position: fixed; top: 28px; right: 32px; z-index: 10; color: rgba(242,237,230,0.3); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; font-weight: 300; }
#layers { position: fixed; bottom: 32px; left: 32px; z-index: 10; display: flex; flex-direction: column; gap: 6px; }
.layer-btn { background: rgba(26,26,24,0.72); border: 1px solid rgba(242,237,230,0.2); color: var(--sand); font-family: 'Inter', sans-serif; font-size: 11px; font-weight: 200; letter-spacing: 0.1em; text-transform: uppercase; padding: 6px 12px; cursor: pointer; backdrop-filter: blur(8px); transition: border-color 0.2s; text-align: left; }
.layer-btn:hover { border-color: rgba(242,237,230,0.5); }
.layer-btn.active { color: #c8ddb8; border-color: #c8ddb8; background: rgba(26,26,24,0.9); }
#legend { position: fixed; bottom: 32px; right: 32px; z-index: 10; background: rgba(26,26,24,0.85); backdrop-filter: blur(8px); border: 1px solid rgba(242,237,230,0.15); padding: 14px 16px; min-width: 200px; display: none; }
#legend.visible { display: block; }
#legend-title { font-size: 10px; font-weight: 500; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(242,237,230,0.45); margin-bottom: 10px; }
.legend-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 11px; font-weight: 300; color: rgba(242,237,230,0.75); }
.legend-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
#panel { position: fixed; top: 0; right: 0; width: var(--panel-w); height: 100%; background: var(--sand); z-index: 20; transform: translateX(100%); transition: transform 0.4s cubic-bezier(0.16,1,0.3,1); overflow-y: auto; overflow-x: hidden; }
#panel.open { transform: translateX(0); }
#panel-close { position: sticky; top: 0; z-index: 5; display: flex; justify-content: flex-end; padding: 16px 20px 0; background: var(--sand); }
#panel-close button { background: none; border: none; cursor: pointer; color: var(--stone); font-size: 20px; line-height: 1; padding: 4px; }
#panel-close button:hover { color: var(--ink); }
#panel-body { padding: 8px 32px 48px; }
.panel-site-name { font-family: 'Inter', sans-serif; font-size: 22px; font-weight: 300; letter-spacing: -0.01em; color: var(--ink); line-height: 1.2; margin-bottom: 4px; }
.panel-state { font-size: 11px; font-weight: 400; letter-spacing: 0.12em; text-transform: uppercase; color: var(--stone); margin-bottom: 20px; }
.panel-acreage { font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; color: var(--stone); margin-bottom: 20px; }
.photo-grid { display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 180px; gap: 3px; margin-bottom: 6px; }
.photo-thumb { background: #ccc8c0; cursor: pointer; overflow: hidden; }
.photo-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0; transition: opacity 0.25s; }
.photo-thumb img.loaded { opacity: 1; }
.photo-thumb:hover img { opacity: 0.75; }
.photo-grid-more { font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--stone); margin-bottom: 20px; text-align: right; }
.photo-grid-more a { color: var(--moss); text-decoration: none; border-bottom: 1px solid var(--moss); }
.panel-section { margin-bottom: 20px; border-top: 1px solid rgba(26,26,24,0.12); padding-top: 16px; }
.panel-section-label { font-size: 10px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--stone); margin-bottom: 8px; }
.panel-section p { font-size: 13.5px; font-weight: 300; line-height: 1.7; color: #2e2e2a; }
.nation-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.nation-tag { font-size: 10px; font-weight: 400; letter-spacing: 0.06em; background: rgba(74,94,58,0.12); color: var(--moss); padding: 3px 8px; border: 1px solid rgba(74,94,58,0.3); }

/* Geologic age visual */
.geo-block { margin-bottom: 20px; border-top: 1px solid rgba(26,26,24,0.12); padding-top: 16px; }
.geo-label { font-size: 10px; font-weight: 500; letter-spacing: 0.16em; text-transform: uppercase; color: var(--stone); margin-bottom: 10px; }
.geo-era-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.geo-swatch { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.geo-era-name { font-size: 14px; font-weight: 300; color: var(--ink); }
.geo-mya { font-size: 11px; font-weight: 300; color: var(--stone); margin-left: auto; letter-spacing: 0.04em; }
.geo-bar-wrap { position: relative; height: 3px; background: rgba(26,26,24,0.08); margin-bottom: 8px; border-radius: 2px; }
.geo-bar-fill { position: absolute; right: 0; top: 0; height: 100%; border-radius: 2px; }
.geo-prose { font-size: 12px; font-weight: 300; line-height: 1.6; color: var(--stone); }
#lightbox { position: fixed; inset: 0; z-index: 100; background: rgba(14,14,12,0.97); display: none; flex-direction: column; }
#lightbox.open { display: flex; }
#lb-img-wrap { flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 56px 72px 0; position: relative; }
#lb-img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; opacity: 0; transition: opacity 0.2s; }
#lb-img.loaded { opacity: 1; }
#lb-spinner { position: absolute; color: rgba(242,237,230,0.3); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; }
#lb-bar { display: flex; align-items: center; justify-content: space-between; padding: 14px 72px 20px; gap: 24px; flex-shrink: 0; border-top: 1px solid rgba(242,237,230,0.07); }
#lb-meta { flex: 1; min-width: 0; }
#lb-filename { font-size: 12px; font-weight: 300; color: rgba(242,237,230,0.55); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }
#lb-date { font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(242,237,230,0.3); }
#lb-actions { display: flex; gap: 8px; flex-shrink: 0; }
.lb-action { font-size: 11px; font-weight: 300; letter-spacing: 0.1em; text-transform: uppercase; text-decoration: none; padding: 5px 12px; border: 1px solid rgba(242,237,230,0.3); color: rgba(242,237,230,0.65); transition: border-color 0.15s, color 0.15s; white-space: nowrap; }
.lb-action:hover { border-color: rgba(242,237,230,0.75); color: var(--sand); }
#lb-close { position: fixed; top: 18px; right: 24px; z-index: 101; background: none; border: none; cursor: pointer; color: rgba(242,237,230,0.4); font-size: 22px; line-height: 1; transition: color 0.15s; }
#lb-close:hover { color: var(--sand); }
#lb-prev, #lb-next { position: fixed; top: 50%; transform: translateY(-50%); z-index: 101; background: none; border: none; cursor: pointer; color: rgba(242,237,230,0.3); font-size: 36px; padding: 16px; transition: color 0.15s; line-height: 1; }
#lb-prev { left: 8px; } #lb-next { right: 8px; }
#lb-prev:hover, #lb-next:hover { color: var(--sand); }
#lb-counter { position: fixed; top: 22px; left: 50%; transform: translateX(-50%); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: rgba(242,237,230,0.25); }
.maplibregl-popup-content { background: var(--ink); color: var(--sand); font-family: 'Inter', sans-serif; font-size: 12px; font-weight: 300; padding: 8px 12px; border-radius: 0; box-shadow: none; }
.maplibregl-popup-tip { border-top-color: var(--ink) !important; }
.maplibregl-ctrl-attrib { font-size: 9px; opacity: 0.4; }
"""

JS = r"""
const GEOLOGY_ERAS = [
  ["Silurian","#7ecfc0"],["Devonian","#4aaa78"],["Mississippian","#3d7fbf"],
  ["Pennsylvanian","#5d5abf"],["Permian","#9b59b6"],["Cretaceous","#c8a840"],
  ["Paleogene","#d4704a"],["Neogene","#c85a8a"],["Quaternary","#8a8478"],["Pleistocene","#8a8478"],
];
const AGENCY_ENTRIES = [
  ["National Park Service","#5c9e6a"],["U.S. Fish & Wildlife Service","#4a8a9e"],
  ["State Park / Preserve","#9e7a4a"],["Nature Conservancy / Private","#7a5a8a"],["Other","#5a5a52"],
];
const LAYER_LEGENDS = {
  geology:{ title:"Geologic Age",          entries:GEOLOGY_ERAS },
  agency: { title:"Managing Agency",        entries:AGENCY_ENTRIES },
  native: { title:"Indigenous Territories", entries:[["Documented","#c8a840"],["No data","#3a3a38"]] },
  shadow: { title:"Shadow History",         entries:[["Extensively documented","#c85a2a"],["Documented","#c8904a"],["Brief note","#8a6a3a"]] },
};
function geologyColor(geo) {
  const g=(geo||'').toLowerCase();
  for (const [era,c] of GEOLOGY_ERAS) if (g.includes(era.toLowerCase())) return c;
  return '#5a5a52';
}
function agencyColor(s) {
  const sl=(s||'').toLowerCase();
  if (sl.includes('national park')||sl.includes('national seashore')||sl.includes('national river')||sl.includes('national monument')||sl.includes('national recreation')) return '#5c9e6a';
  if (sl.includes('wildlife refuge')||sl.includes('federal wilderness')) return '#4a8a9e';
  if (sl.includes('state park')||sl.includes('state nature preserve')||sl.includes('state memorial')||sl.includes('state forest')) return '#9e7a4a';
  if (sl.includes('nature conservancy')||sl.includes('private')||sl.includes('land trust')) return '#7a5a8a';
  return '#5a5a52';
}
let activeLayer = null;
function dotColor(p) {
  if (activeLayer==='geology') return geologyColor(p.geology);
  if (activeLayer==='agency')  return agencyColor(p.conservation_status);
  if (activeLayer==='native')  return (p.native_lands||'').trim() ? '#c8a840' : '#3a3a38';
  if (activeLayer==='shadow')  { const l=(p.shadow_history||'').length; return l>800?'#c85a2a':l>400?'#c8904a':'#8a6a3a'; }
  return '#f2ede6';
}
function buildDotFeatures() {
  return { ...SITES, features: SITES.features.map(f => ({...f, properties:{...f.properties, _color:dotColor(f.properties)}})) };
}
const map = new maplibregl.Map({
  container:'map',
  style:{ version:8, sources:{ base:{ type:'raster', tiles:['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'], tileSize:256, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>' } }, layers:[{id:'bg',type:'raster',source:'base'}] },
  center:[-89,38.5], zoom:4.4, minZoom:2, maxZoom:18,
});
document.getElementById('site-count').textContent = SITES.features.length+' sites';
map.on('load', () => {
  map.addSource('sites', { type:'geojson', data:buildDotFeatures() });
  map.addLayer({ id:'sites-hit', type:'circle', source:'sites', paint:{ 'circle-radius':16,'circle-opacity':0,'circle-stroke-width':0 } });
  map.addLayer({ id:'sites-dot', type:'circle', source:'sites',
    paint:{ 'circle-radius':['interpolate',['linear'],['zoom'],3,4.5,10,8],
            'circle-color':['get','_color'],'circle-opacity':0.88,
            'circle-stroke-color':'rgba(242,237,230,0.2)','circle-stroke-width':1 } });
  const popup = new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:12});
  map.on('mouseenter','sites-hit', e => {
    map.getCanvas().style.cursor='pointer';
    popup.setLngLat(e.lngLat).setHTML('<span style="letter-spacing:.07em">'+e.features[0].properties.name+'</span>').addTo(map);
  });
  map.on('mouseleave','sites-hit', () => { map.getCanvas().style.cursor=''; popup.remove(); });
  map.on('click','sites-hit', e => {
    const props = e.features[0].properties;
    const coords = e.features[0].geometry.coordinates;
    map.flyTo({ center:coords, zoom:Math.max(map.getZoom(),11), duration:900, essential:true });
    openPanel(props);
  });
  document.querySelectorAll('.layer-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const layer = btn.dataset.layer;
      if (activeLayer===layer) { activeLayer=null; btn.classList.remove('active'); hideLegend(); }
      else { document.querySelectorAll('.layer-btn').forEach(b=>b.classList.remove('active')); activeLayer=layer; btn.classList.add('active'); showLegend(layer); }
      map.getSource('sites').setData(buildDotFeatures());
    });
  });
});
function showLegend(layer) {
  const def = LAYER_LEGENDS[layer];
  document.getElementById('legend-title').textContent = def.title;
  document.getElementById('legend-items').innerHTML = def.entries.map(([l,c])=>
    '<div class="legend-item"><div class="legend-dot" style="background:'+c+'"></div><span>'+l+'</span></div>').join('');
  document.getElementById('legend').classList.add('visible');
}
function hideLegend() { document.getElementById('legend').classList.remove('visible'); }

// Geologic timescale: era name, color, age range [oldest, youngest] in Mya
const GEO_TIMESCALE = [
  ["Cambrian",      "#a0522d", 541,  485],
  ["Ordovician",    "#c8a86e", 485,  444],
  ["Silurian",      "#7ecfc0", 444,  419],
  ["Devonian",      "#4aaa78", 419,  359],
  ["Mississippian", "#3d7fbf", 359,  323],
  ["Pennsylvanian", "#5d5abf", 323,  299],
  ["Permian",       "#9b59b6", 299,  252],
  ["Triassic",      "#e07050", 252,  201],
  ["Jurassic",      "#c8a840", 201,  145],
  ["Cretaceous",    "#d4b840", 145,   66],
  ["Paleogene",     "#d4704a",  66,   23],
  ["Neogene",       "#c85a8a",  23,    2.6],
  ["Quaternary",    "#8a8478",   2.6,  0],
  ["Pleistocene",   "#8a8478",   2.6,  0.01],
];
const EARTH_AGE = 541; // Mya span shown on bar

function buildGeoBlock(geoText) {
  if (!geoText) return '';
  const g = geoText.toLowerCase();

  // Find all matching eras
  const matched = GEO_TIMESCALE.filter(([era]) => g.includes(era.toLowerCase()));
  if (!matched.length) return '';

  // Use oldest matched era as primary
  const [eraName, color, oldest, youngest] = matched.reduce((a, b) => a[2] > b[2] ? a : b);

  // Extract first Mya number from text
  const myaMatch = geoText.match(/~?([\d,]+(?:-[\d,]+)?)\s*[Mm]ya/);
  const myaLabel = myaMatch ? myaMatch[1].replace(',','') + ' Mya' : '';

  // Bar: position right-to-left, oldest era fills from right
  const barPct = Math.min(100, Math.round((oldest / EARTH_AGE) * 100));

  // Short prose: first clause only
  const prose = geoText.split(';')[0].trim();

  return '<div class="geo-block">' +
    '<div class="geo-label">Geology</div>' +
    '<div class="geo-era-row">' +
      '<div class="geo-swatch" style="background:'+color+'"></div>' +
      '<span class="geo-era-name">'+eraName+'</span>' +
      (myaLabel ? '<span class="geo-mya">'+myaLabel+'</span>' : '') +
    '</div>' +
    '<div class="geo-bar-wrap">' +
      '<div class="geo-bar-fill" style="width:'+barPct+'%;background:'+color+';opacity:0.5"></div>' +
    '</div>' +
    '<p class="geo-prose">'+prose+'</p>' +
  '</div>';
}

const imgObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const img = entry.target;
      if (img.dataset.src) { img.src=img.dataset.src; img.onload=()=>img.classList.add('loaded'); imgObserver.unobserve(img); }
    }
  });
}, { rootMargin:'120px' });

const panel = document.getElementById('panel');
const panelBody = document.getElementById('panel-body');
document.getElementById('panel-close').querySelector('button').addEventListener('click', () => panel.classList.remove('open'));
let currentPhotos = [];

function openPanel(props) {
  const state = STATE_NAMES[props.state]||props.state;
  const acreage = props.acreage ? parseInt(props.acreage).toLocaleString()+' acres' : '';
  const ecology = (props.ecology||'').split(';')[0].trim();
  const geo = (props.geology||'').split(';')[0].trim();
  const hydro = (props.hydrology||'').split(';')[0].trim();
  const nativeLands = props.native_lands||'';
  const nativeApi = JSON.parse(props.native_lands_api||'[]');
  const shadow = props.shadow_history||'';
  const shadowShort = shadow.split(/(?<=[.!?])\s+/).slice(0,2).join(' ');
  const nativeShort = nativeLands.length>280 ? nativeLands.slice(0,280)+'...' : nativeLands;
  const nationTags = nativeApi.length ? '<div class="nation-tags">'+nativeApi.map(n=>'<span class="nation-tag">'+n+'</span>').join('')+'</div>' : '';
  const photos = PHOTOS[props.slug]||[];
  currentPhotos = photos;
  const GRID_MAX = 6;
  const grid = photos.slice(0, GRID_MAX);
  let gridHTML = '';
  if (grid.length) {
    gridHTML = '<div class="photo-grid">' +
      grid.map((p,i) => p.thumb
        ? '<div class="photo-thumb" data-idx="'+i+'"><img data-src="'+p.thumb+'" alt=""></div>'
        : '<div class="photo-thumb" data-idx="'+i+'" style="background:#bbb8b0"></div>'
      ).join('') + '</div>';
    if (photos.length > GRID_MAX) {
      const q = encodeURIComponent('Public Lands Institute '+props.name);
      gridHTML += '<p class="photo-grid-more"><a href="https://commons.wikimedia.org/w/index.php?title=Special:MediaSearch&search='+q+'" target="_blank">View all '+photos.length+' photos →</a></p>';
    }
  }
  let sections = '';
  if (ecology) sections += '<div class="panel-section"><div class="panel-section-label">Ecology</div><p>'+ecology+'</p></div>';
  if (geo)     sections += buildGeoBlock(props.geology);
  if (hydro)   sections += '<div class="panel-section"><div class="panel-section-label">Hydrology</div><p>'+hydro+'</p></div>';
  if (nativeLands) sections += '<div class="panel-section"><div class="panel-section-label">Indigenous Territories</div><p>'+nativeShort+'</p></div>';
  if (shadow)  sections += '<div class="panel-section"><div class="panel-section-label">Shadow History</div><p>'+shadowShort+'</p></div>';
  if (props.conservation_status) sections += '<div class="panel-section"><div class="panel-section-label">Status</div><p>'+props.conservation_status+'</p></div>';
  panelBody.innerHTML =
    '<p class="panel-site-name">'+props.name+'</p>'+
    '<p class="panel-state">'+state+'</p>'+
    gridHTML+
    (acreage?'<p class="panel-acreage">'+acreage+'</p>':'')+
    sections;
  panelBody.querySelectorAll('.photo-thumb').forEach(thumb => {
    const img = thumb.querySelector('img');
    if (img) imgObserver.observe(img);
    thumb.addEventListener('click', () => openLightbox(+thumb.dataset.idx));
  });
  panel.classList.add('open');
}

const lightbox  = document.getElementById('lightbox');
const lbImg     = document.getElementById('lb-img');
const lbSpinner = document.getElementById('lb-spinner');
let lbIndex = 0;
function openLightbox(idx) { lbIndex=idx; lightbox.classList.add('open'); showLbPhoto(idx); }
function showLbPhoto(idx) {
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
  if (p.large) {
    lbImg.src = p.large;
    lbImg.onload  = () => { lbSpinner.style.display='none'; lbImg.classList.add('loaded'); };
    lbImg.onerror = () => { lbSpinner.textContent='Image unavailable'; };
  } else { lbSpinner.textContent='No local image'; }
}
document.getElementById('lb-close').addEventListener('click', () => { lightbox.classList.remove('open'); lbImg.src=''; });
document.getElementById('lb-prev').addEventListener('click',  () => { lbIndex=(lbIndex-1+currentPhotos.length)%currentPhotos.length; showLbPhoto(lbIndex); });
document.getElementById('lb-next').addEventListener('click',  () => { lbIndex=(lbIndex+1)%currentPhotos.length; showLbPhoto(lbIndex); });
lightbox.addEventListener('click', e => { if(e.target===lightbox){ lightbox.classList.remove('open'); lbImg.src=''; } });
document.addEventListener('keydown', e => {
  if (!lightbox.classList.contains('open')) return;
  if (e.key==='Escape')     { lightbox.classList.remove('open'); lbImg.src=''; }
  if (e.key==='ArrowLeft')  { lbIndex=(lbIndex-1+currentPhotos.length)%currentPhotos.length; showLbPhoto(lbIndex); }
  if (e.key==='ArrowRight') { lbIndex=(lbIndex+1)%currentPhotos.length; showLbPhoto(lbIndex); }
});
"""

HTML = f"""<!DOCTYPE html>
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
<style>{CSS}</style>
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
const SITES={geojson_str};
const PHOTOS={photos_str};
const STATE_NAMES={state_str};
{JS}
</script>
</body>
</html>"""

out = '/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli/index.html'
Path(out).write_text(HTML, encoding='utf-8')
print(f"Written {len(HTML):,} chars")
