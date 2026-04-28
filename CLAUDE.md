# Public Lands Institute

Static photographic index of public lands. CC0 Public Domain.

## Important
Always work directly in the main repo. Never use git worktrees for this project — they drift from main and cause data loss on deploy. If you find yourself in a worktree, sync sites.json, sites_meta.json, and *_cache.json from the main repo before generating or deploying.
Never use preview_start, preview_screenshot, preview_snapshot, or any browser preview tools. They do not work in this environment. Do not attempt browser verification for any change — report what changed and move on.
At the start of every session, read sites.json (first 60 lines), sites_meta.json, shadow_history_bibliography.txt, generate_sites.py, and js/lightbox.js before performing any task.
Site: publiclandsinstitute.net
Host: DreamHost (SFTP port 22, credentials in .env)

## Key files
- generate_sites.py — master generator, run with: python3 generate_sites.py
- sites.json — location metadata (includes lat/lng/inat_radius_km)
- sites_meta.json — agency, agency_type, territory data used to generate sites.html
- inaturalist_cache.json — iNat API cache, safe to delete entries to force refresh
- img/jpg/<slug>/ — JPEG images (drive generation)
- img/full/<slug>/ — TIFF downloads
- .env — DreamHost credentials (never commit this file)

## Deploying
Install sshpass once: brew install sshpass
**Always run all 3 phases below — never construct a custom rsync command. Phase 3 (chmod) is mandatory after every deploy; rsync --chmod only applies to files transferred in that run, not existing files.**
Before deploying, archive the current generated files (timestamp includes H-M so multiple deploys per day are preserved):
  STAMP=$(date +%Y-%m-%d_%H-%M)
  mkdir -p Archive/$STAMP/sites
  cp *.html Archive/$STAMP/ 2>/dev/null || true
  cp sites/*.html Archive/$STAMP/sites/ 2>/dev/null || true
  cp sites.json sites_meta.json nativeland_cache.json shadow_history_bibliography.txt shadow_history_methodology.txt Archive/$STAMP/ 2>/dev/null || true
  # Prune archives older than 30 days, but always keep the two most recent
  python3 -c "
import os, shutil
from datetime import datetime, timedelta
arc = 'Archive'
entries = sorted([e for e in os.listdir(arc) if os.path.isdir(os.path.join(arc, e)) and e[0].isdigit()])
cutoff = datetime.now() - timedelta(days=30)
for e in entries[:-2]:
    try:
        dt = datetime.strptime(e[:10], '%Y-%m-%d')
        if dt < cutoff:
            shutil.rmtree(os.path.join(arc, e))
            print(f'Pruned {e}')
    except ValueError:
        pass
"
Then deploy (three-phase — images go first so they exist before HTML references them):
  source .env
  # Phase 1: Images — skip existing (images are immutable once uploaded, never re-checksum)
  # Images upload first so they are on the server before HTML is updated to reference them.
  # No -z: JPGs are already compressed; TIFs are large binaries — compression adds CPU overhead with no benefit
  sshpass -p "$DREAMHOST_PASS" rsync -av --ignore-existing \
    --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3" \
    img/ "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/img/"
  # Phase 2: HTML/JS/JSON/text files — checksum-accurate, deletes removed files, skips images
  sshpass -p "$DREAMHOST_PASS" rsync -avz --checksum --delete \
    --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    --exclude '.git/' --exclude '.env' --exclude '.claude/' \
    --exclude 'Archive/' --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude '*.py' --exclude 'img/' \
    -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3" \
    . "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/"
  # Phase 3: Fix permissions on existing files — rsync --chmod only applies to files transferred in that run
  # Use + (not \;) to batch chmod calls — much faster on large image libraries
  sshpass -p "$DREAMHOST_PASS" ssh \
    -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3 \
    "$DREAMHOST_USER@$DREAMHOST_HOST" \
    "find $DREAMHOST_REMOTE_PATH -type d -exec chmod 755 {} + && find $DREAMHOST_REMOTE_PATH -type f -exec chmod 644 {} +"

## Field order in sites.json
geological_age, epoch, native_lands, displacement_tenure, shadow_history, ecology, hydrology, acreage, gps
(plus conservation_status, endangered_species, lat, lng, inat_radius_km — kept in JSON, not displayed)

## shadow_history field
Documented but underreported history: industrial contamination, forced residential removal, segregated CCC labor, archaeological extraction, institutional labor. Displayed on individual site pages and on the sites index, positioned between displacement_tenure and ecology. Sources tracked in shadow_history_bibliography.txt (archived with each deploy).

## Observations schema (optional per-site field)
Add an `observations` array to group images by visit date:
```json
"observations": [
  { "date": "2026-03", "notes": "Early spring, dormant forest floor.", "image_list": ["_DSF1130.jpg"] }
]
```
- date: YYYY-MM
- notes: free text, displayed above that visit's images
- image_list: filenames only (files must exist in img/jpg/<slug>/)
If omitted, generator falls back to scanning the folder and grouping images by EXIF month.

## research_pli_metadata.py
Populates native_lands and displacement_tenure using native-land.ca territories + treaties APIs and Claude.
Run: python3 research_pli_metadata.py
Flags: --site <slug> to process one site, --dry-run to preview, --force-native / --force-tenure to re-research.
Safe to re-run; skips already-populated entries. Complex sites (Mammoth Cave, etc.) are guarded against overwrite.

## Writing rules
- Never use em dashes or en dashes anywhere in output or field values
- Never add an "images" count field to sites.json
- Roman numeral captions I through L
- Always run generator after any change and confirm output before finishing
- Always deploy after generating unless told otherwise

## inat_radius_km defaults
- 5km: standard preserves and state parks
- 8km: large state parks, wilderness areas, multi-tract preserves
- 10km: national parks, national wildlife refuges

---

## ADDING A NEW LOCATION

When the user says "add [location name]", follow this protocol exactly:

### Step 1: Research

Use web search to find the following for the named location. Search specifically for each field — do not guess or approximate.

- **geological_age**: Age in millions of years and rock type. Format: "~450 Mya Ordovician limestone"
- **epoch**: Geologic epoch or period name. Format: "Late Ordovician" or "Mississippian"
- **native_lands**: Indigenous nations with historical presence. Use the native-land.ca API (nativeland_cache.json) for territory names as a starting point, then web search for historical context. See native lands style guide below.
- **ecology**: Dominant plant communities, notable species, habitat type. 1-2 sentences max.
- **hydrology**: Watershed, named rivers or streams, any notable hydrological features (springs, karst, etc.)
- **acreage**: Total acreage of the protected area. Use the official figure from NPS, state DNR, or managing agency.
- **displacement_tenure**: Land cession and tenure history. Run research_pli_metadata.py after adding to sites.json, or manually research treaties. Format: "Cession N: Full Treaty Name (YYYY); [qualitative context]." For Kentucky, Tennessee, and other non-federal-domain states, document the colonial-era dispossession chain instead (no Royce cession applies). Complex cases (enslaved labor, litigation) require manual narrative.
- **shadow_history**: Documented but underreported history. Research via EPA records, NPS administrative histories, CCC camp rosters, archaeological site files, court records. Add to shadow_history_bibliography.txt. Leave empty if nothing significant found.
- **conservation_status**: Official federal or state designations. Kept in JSON, not displayed.
- **endangered_species**: Federally listed T&E species. Kept in JSON, not displayed.
- **gps**: Decimal degrees of the park/preserve center or main entrance. Format: "XX.XXXX° N, XX.XXXX° W"
- **lat** / **lng**: Numeric values parsed from GPS above (e.g. 39.7993 and -83.8328)
- **inat_radius_km**: Choose based on size using the defaults above.
- **slug**: lowercase, hyphenated version of the full official name (e.g. "shawnee-national-forest")
- **state**: Two-letter state abbreviation (e.g. "IL")

### Step 2: Confirm before writing

Present all researched fields to the user in a readable summary and ask: "Does this look right? I'll add it to sites.json."

Wait for confirmation before proceeding.

### Step 3: Add to sites.json

Insert the new entry at the **top** of sites.json (position 0 in the array). New sites always go at the top. Use this exact JSON structure:

```json
{
  "slug": "example-site-name",
  "name": "Example Site Name",
  "state": "OH",
  "geological_age": "~445 Mya Silurian dolomite",
  "epoch": "Late Silurian",
  "native_lands": "Shawnee, Miami, Adena",
  "displacement_tenure": "",
  "ecology": "Description of plant communities and notable species.",
  "hydrology": "Watershed and water features.",
  "acreage": "1,234",
  "conservation_status": "Ohio State Nature Preserve; National Natural Landmark",
  "endangered_species": "none documented",
  "gps": "39.7993° N, 83.8328° W",
  "lat": 39.7993,
  "lng": -83.8328,
  "inat_radius_km": 5
}
```

### Step 3b: Add to sites_meta.json

Add an entry to sites_meta.json with the new slug as key:
```json
"slug": {
  "agency": "Managing agency name",
  "agency_type": "State park | NPS | USFWS | Municipal park | Private preserve | etc.",
  "territory": ["Nation1", "Nation2"]
}
```

### Step 3c: Update shadow_history_bibliography.txt

If shadow_history is non-empty, add a new section at the top of shadow_history_bibliography.txt (after the header lines) listing each source consulted. Use the same format as existing sections. Update the "Generated" date to today.

### Step 4: Generate and deploy

Run python3 generate_sites.py and confirm the new .html file appears in the output list. Then deploy (archive first per deploy protocol above).

### Step 5: Generate metrics and archive metadata

After deploy completes, run both:

  python3 generate_metrics.py
  python3 generate_metadata.py

generate_metrics.py overwrites PLI-Project-Metrics.txt with current counts: total sites, total images, states represented, total acreage, and managing agencies.
generate_metadata.py overwrites archive-metadata/archive.csv with a full metadata export for archival use.

---

## NATIVE LANDS FIELD STYLE GUIDE

Write as a flowing series of facts separated by semicolons. Include: nation names with indigenous-language names in parentheses where known, territorial context, specific historical events (battles, treaties) with dates, and forced removal or reservation outcome. The native-land.ca API results (nativeland_cache.json) give territory names as a starting point — use web search to fill in the historical narrative.

**Model entry:**
> Shawnee (Shawanwaki) · Miami · Adena and Hopewell cultures; Little Miami River a major Shawnee territory; Shawnee ceded Ohio lands via Treaty of Greene Ville 1795

Do not write generic statements. Be specific about which nations, which events, which dates.

---

## Lightbox and mobile layout
Site pages load js/lightbox.js at the bottom of <body>. It intercepts clicks on
figure download links and opens a fullscreen lightbox viewer instead of triggering
a download. The download TIFF button lives inside the lightbox. Do not add onclick
handlers or image interaction logic anywhere in the page template -- lightbox.js
reads the existing figure structure automatically via .caption-title and
.caption-filename. No changes to sites.json are needed.

On mobile (max-width: 480px), CSS order properties cause .site-images to render
above .site-data, so photographs appear before the metadata fields. The desktop
two-column layout (min-width: 720px) is unaffected.

On mobile, lightbox.js also caps visible images at 4. Sites with more than 4
images show a "Show N more" button after the fourth figure; tapping it reveals
the rest. This is handled entirely in JS — no changes to the page template or
sites.json are needed. Sites with 4 or fewer images are unaffected.
