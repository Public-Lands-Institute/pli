#!/usr/bin/env python3
"""
research_pli_metadata.py
Populate native_lands and displacement_tenure using native-land.ca API + Claude research.

Phases:
  1. Query native-land.ca territories API → base for native_lands
  2. Query native-land.ca treaties API → base for displacement_tenure
  3. Claude API (claude-haiku) → resolve cession numbers, add qualitative tenure history

Run:
    python3 research_pli_metadata.py                # process all sites needing work
    python3 research_pli_metadata.py --site clifty-falls-state-park
    python3 research_pli_metadata.py --dry-run      # preview without writing
    python3 research_pli_metadata.py --force-tenure # re-research tenure for all sites
    python3 research_pli_metadata.py --force-native # regenerate native_lands for all sites

Requires:
    NATIVELAND_API_KEY in .env (or environment)
    ANTHROPIC_API_KEY in .env (or environment) — optional; skips Claude phase if absent
    pip install anthropic  (for Claude phase)

Safe to re-run. Already-populated fields are skipped unless a force flag is passed.
"""

import json, os, sys, time, urllib.request
from dotenv import load_dotenv
load_dotenv()

# ── CLI flags ──────────────────────────────────────────────────────────────────

FORCE_NATIVE = '--force-native' in sys.argv
FORCE_TENURE = '--force-tenure' in sys.argv
DRY_RUN      = '--dry-run'      in sys.argv
ONLY_SLUG    = sys.argv[sys.argv.index('--site') + 1] if '--site' in sys.argv else None

# ── Dependencies ───────────────────────────────────────────────────────────────

try:
    import anthropic as _anthropic
    _ANTHROPIC_INSTALLED = True
except ImportError:
    _ANTHROPIC_INSTALLED = False
    print('NOTE: anthropic package not installed — skipping Claude research phase.')
    print('      pip install anthropic')

SITES_FILE = 'sites.json'
CACHE_FILE = 'nativeland_cache.json'

# Sites whose tenure history requires manual narrative — complex enough that
# automated API + Claude results would be misleading or incomplete. These are
# skipped for displacement_tenure even with --force-tenure.
COMPLEX_TENURE = {
    'mammoth-cave-national-park':
        'TODO: enslaved labor documented in cave saltpeter mining and tourist operations '
        '1810s-1840s; NPS acquired land from private owners beginning 1926; full land '
        'tenure narrative requires archival research',
    'johnsons-shut-ins-state-park':
        'TODO: 2005 AmerenUE Taum Sauk reservoir breach destroyed lower park; '
        'litigation settlement 2009 funded restoration; land tenure predates breach -- '
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

nativeland_key = os.environ.get('NATIVELAND_API_KEY', '')
anthropic_key  = os.environ.get('ANTHROPIC_API_KEY', '')

if _ANTHROPIC_INSTALLED and not anthropic_key:
    print('NOTE: ANTHROPIC_API_KEY not set in .env — skipping Claude research phase.')

client = (
    _anthropic.Anthropic(api_key=anthropic_key)
    if (_ANTHROPIC_INSTALLED and anthropic_key)
    else None
)

# ── native-land.ca API ─────────────────────────────────────────────────────────

def _save_cache():
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def fetch_nativeland(slug, lat, lng, maps):
    """
    Fetch features from native-land.ca for maps='territories' or 'treaties'.
    Checks cache first; falls back to un-prefixed key for legacy territory entries.
    """
    primary_key = f'{maps}:{slug}'
    legacy_key  = slug  # territories were originally cached without prefix

    if primary_key in cache:
        return cache[primary_key]
    if maps == 'territories' and legacy_key in cache:
        # Migrate legacy key
        cache[primary_key] = cache[legacy_key]
        _save_cache()
        return cache[primary_key]

    url = (
        f'https://native-land.ca/api/index.php?maps={maps}&position={lat},{lng}'
        + (f'&key={nativeland_key}' if nativeland_key else '')
    )
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'PublicLandsInstitute/1.0 (publiclandsinstitute.net)'}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        time.sleep(0.6)
        cache[primary_key] = data
        _save_cache()
        print(f'    [{maps}] {len(data)} feature(s) fetched')
        return data
    except Exception as e:
        print(f'    [{maps}] API error: {e}')
        return []


def extract_names(features):
    names = []
    seen  = set()
    for f in features:
        if isinstance(f, str):
            name = f.strip()
        else:
            name = f.get('properties', {}).get('Name', '').strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names

# ── PLI style guide ────────────────────────────────────────────────────────────
#
# native_lands format:
#   "Nation A (indigenous name) · Nation B; territorial context sentence; event with date"
#
# displacement_tenure format:
#   "Cession N: Full Treaty Name (YYYY); qualitative sentence(s) in deadpan tone."

NATIVE_LANDS_STYLE = """
Write as a flowing series of facts separated by semicolons.
Lead with nation names separated by middle dots (·), with indigenous-language
names in parentheses where known.
Then add: territorial context, specific historical events (battles, treaties)
with dates, and forced removal or reservation outcome.
Be specific: which nations, which events, which dates.
Do not write generic statements.
Example: Shawnee (Shawanwaki) · Miami · Adena and Hopewell cultures; Little Miami
River a major Shawnee territory; Shawnee ceded Ohio lands via Treaty of Greene
Ville 1795
""".strip()

TENURE_STYLE = """
Resolve each cession number to its full treaty name and year where you are
confident. Format: "Cession N: Full Treaty Name (YYYY)".
Then append 1-2 sentences of qualitative tenure history specific to this exact
site — not the region generally. Focus on:
  - Enslaved or coerced labor in site development/operations
  - Eminent domain, condemnation, forced community displacement
  - Litigation, contested ownership, legal settlements
  - Indigenous sacred site conflicts, access restrictions, naming disputes
  - Notable acquisition controversies
Deadpan tone. Specific names, dates, legal citations only.
If nothing specific is documented for this exact site, end with:
TODO: RESEARCH TENURE
""".strip()

# ── Claude research ────────────────────────────────────────────────────────────

def claude_research_native_lands(site_name, state, territory_names):
    """
    Format raw territory names from the API into PLI-style native_lands narrative.
    """
    if not client or not territory_names:
        return None

    prompt = f"""You are writing a field for a public lands database following a strict style guide.

Site: {site_name} ({state})
Territory names from native-land.ca API: {'; '.join(territory_names)}

Style guide:
{NATIVE_LANDS_STYLE}

Write the native_lands field value. Do not add any preamble or explanation.
Output only the field value as plain text."""

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=400,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f'    Claude native_lands error: {e}')
        return None


def claude_research_tenure(site_name, state, treaty_names, existing_tenure=''):
    """
    Resolve cession numbers and research qualitative tenure history for a site.
    Returns (treaties_resolved: list[str], qualitative: str).
    """
    if not client:
        return treaty_names, ''

    context = ''
    if existing_tenure and existing_tenure.startswith('TODO:'):
        context = f'\nKnown research directions: {existing_tenure}'

    prompt = f"""You are writing a field for a public lands database.

Site: {site_name} ({state})
Treaty/cession names from native-land.ca API: {'; '.join(treaty_names) if treaty_names else 'none'}{context}

Style guide:
{TENURE_STYLE}

Respond ONLY with a JSON object, no other text:
{{
  "treaties_resolved": ["Cession N: Full Treaty Name (YYYY)", ...],
  "qualitative": "1-2 sentences or empty string if nothing documented"
}}

If no qualitative history is documented for this specific site, set "qualitative" to "TODO: RESEARCH TENURE"."""

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=600,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = msg.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith('```'):
            text = '\n'.join(text.split('\n')[1:]).rsplit('```', 1)[0].strip()
        result = json.loads(text)
        return (
            result.get('treaties_resolved', treaty_names),
            result.get('qualitative', '').strip()
        )
    except Exception as e:
        print(f'    Claude tenure error: {e}')
        return treaty_names, ''

# ── Field need detection ───────────────────────────────────────────────────────

def needs_native_update(val):
    if FORCE_NATIVE:
        return True
    return not val

def needs_tenure_update(val):
    if FORCE_TENURE:
        return True
    if not val:
        return True
    # Upgrade bare cession strings from research_metadata.py
    if val.startswith('Ceded via Cession') or val == 'Ceded via ':
        return True
    # Try again on generic TODO (but not the detailed manual-research TODOs)
    if val == 'TODO: RESEARCH TENURE':
        return True
    if val.startswith('TODO: API unavailable') or val.startswith('TODO: no treaty'):
        return True
    return False

# ── Main loop ──────────────────────────────────────────────────────────────────

updated = 0

for site in sites:
    slug  = site['slug']
    name  = site['name']
    state = site['state']

    if ONLY_SLUG and slug != ONLY_SLUG:
        continue

    lat = site.get('lat')
    lng = site.get('lng')
    if not lat or not lng:
        print(f'  {slug}: no GPS coordinates, skipping')
        continue

    existing_native = site.get('native_lands', '')
    existing_tenure = site.get('displacement_tenure', '')

    do_native = needs_native_update(existing_native)
    do_tenure = needs_tenure_update(existing_tenure)

    if not do_native and not do_tenure:
        print(f'  {slug}: fields current, skipping')
        continue

    print(f'\n  {slug}:')
    site_updated = False

    # Fetch API data
    territory_features = fetch_nativeland(slug, lat, lng, 'territories')
    territory_names    = extract_names(territory_features)

    treaty_features = fetch_nativeland(slug, lat, lng, 'treaties')
    treaty_names    = extract_names(treaty_features)

    # ── native_lands ──────────────────────────────────────────────────────────
    if do_native:
        if client and territory_names:
            new_native = claude_research_native_lands(name, state, territory_names)
        elif territory_names:
            new_native = ' · '.join(territory_names)
        else:
            new_native = 'TODO: RESEARCH NATIVE LANDS'

        print(f'    native_lands: {new_native[:100]}{"..." if len(new_native) > 100 else ""}')
        if not DRY_RUN:
            site['native_lands'] = new_native
        site_updated = True

    # ── displacement_tenure ───────────────────────────────────────────────────
    if do_tenure and slug in COMPLEX_TENURE:
        print(f'    displacement_tenure: complex site -- setting TODO (manual research required)')
        if not DRY_RUN:
            site['displacement_tenure'] = COMPLEX_TENURE[slug]
        updated += 1
        continue

    if do_tenure:
        if client:
            resolved, qualitative = claude_research_tenure(
                name, state, treaty_names, existing_tenure
            )
        else:
            resolved    = treaty_names
            qualitative = ''

        # Assemble field value
        if resolved:
            tenure = '; '.join(resolved)
        else:
            tenure = ''

        if qualitative and qualitative != 'TODO: RESEARCH TENURE':
            tenure = f'{tenure} {qualitative}'.strip() if tenure else qualitative
        elif not tenure:
            tenure = 'TODO: RESEARCH TENURE'
        elif qualitative == 'TODO: RESEARCH TENURE':
            tenure = f'{tenure} TODO: RESEARCH TENURE'

        print(f'    displacement_tenure: {tenure[:120]}{"..." if len(tenure) > 120 else ""}')
        if not DRY_RUN:
            site['displacement_tenure'] = tenure
        site_updated = True

    if site_updated:
        updated += 1

# ── Write back ─────────────────────────────────────────────────────────────────

if not DRY_RUN:
    with open(SITES_FILE, 'w') as f:
        json.dump(sites, f, indent=2, ensure_ascii=False)
    print(f'\nDone — {updated} site(s) updated. Run python3 generate_sites.py to rebuild.')
else:
    print(f'\nDry run complete — {updated} site(s) would be updated.')
    print('Remove --dry-run to apply changes.')
