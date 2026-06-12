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
- sites_meta.json — agency, agency_type, territory data used by the map index (index.html)
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
Then deploy (two-phase — image uploads are handled separately by the "update" workflow):
  source .env
  # Phase 2: HTML/JS/JSON/text files — checksum-accurate, deletes removed files, skips images
  sshpass -p "$DREAMHOST_PASS" rsync -avz --checksum --delete \
    --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    --exclude '.git/' --exclude '.env' --exclude '.claude/' \
    --exclude 'Archive/' --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude '*.py' --exclude 'img/' \
    --exclude 'CLAUDE.md' --exclude 'PLI-*' --exclude '*.bak*' \
    --exclude '*.docx' --exclude 'banner.html' --exclude 'index2.html' \
    --exclude 'archive2.html' --exclude 'Draft*' --exclude 'Database Style/' \
    --exclude 'no image/' --exclude 'single image/' --exclude 'deploy.sh' \
    --exclude '.gitignore' --exclude '.DS_Store' \
    -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3" \
    . "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/"
  # Phase 3: Fix permissions on existing files — rsync --chmod only applies to files transferred in that run
  # Use + (not \;) to batch chmod calls — much faster on large image libraries
  sshpass -p "$DREAMHOST_PASS" ssh \
    -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3 \
    "$DREAMHOST_USER@$DREAMHOST_HOST" \
    "find $DREAMHOST_REMOTE_PATH -type d -exec chmod 755 {} + && find $DREAMHOST_REMOTE_PATH -type f -exec chmod 644 {} +"

## Field order in sites.json
geological_age, epoch, native_lands, displacement_tenure, shadow_history, ecology, hydrology, acreage, gps
(plus conservation_status, endangered_species, lat, lng, inat_radius_km — kept in JSON, not displayed)

## shadow_history field
Documented but underreported history: industrial contamination, forced residential removal, segregated CCC labor, archaeological extraction, institutional labor. Displayed on individual site pages and in the map index panel, positioned between displacement_tenure and ecology. Sources tracked in shadow_history_bibliography.txt (archived with each deploy).

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
- Plain numeric captions (1, 2, 3...), not roman numerals
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

Output the following terminal block for the user to paste and run themselves. Do not run it:

```bash
cd "/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli"
python3 generate_sites.py
STAMP=$(date +%Y-%m-%d_%H-%M)
mkdir -p Archive/$STAMP/sites
cp *.html Archive/$STAMP/ 2>/dev/null || true
cp sites/*.html Archive/$STAMP/sites/ 2>/dev/null || true
cp sites.json sites_meta.json nativeland_cache.json shadow_history_bibliography.txt shadow_history_methodology.txt Archive/$STAMP/ 2>/dev/null || true
source .env
sshpass -p "$DREAMHOST_PASS" rsync -avz --checksum --delete \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  --exclude '.git/' --exclude '.env' --exclude '.claude/' \
  --exclude 'Archive/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '*.py' --exclude 'img/' \
  --exclude 'CLAUDE.md' --exclude 'PLI-*' --exclude '*.bak*' \
  --exclude '*.docx' --exclude 'banner.html' --exclude 'index2.html' \
  --exclude 'archive2.html' --exclude 'Draft*' --exclude 'Database Style/' \
  --exclude 'no image/' --exclude 'single image/' --exclude 'deploy.sh' \
  --exclude '.gitignore' --exclude '.DS_Store' \
  -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3" \
  . "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/"
sshpass -p "$DREAMHOST_PASS" ssh \
  -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3 \
  "$DREAMHOST_USER@$DREAMHOST_HOST" \
  "find $DREAMHOST_REMOTE_PATH -type d -exec chmod 755 {} + && find $DREAMHOST_REMOTE_PATH -type f -exec chmod 644 {} +"
```

### Step 5: Generate metrics and archive metadata

Output the following terminal block for the user to paste and run themselves. Do not run it:

```bash
cd "/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli"
python3 generate_metrics.py
python3 generate_metadata.py
```

generate_metrics.py overwrites PLI-Project-Metrics.txt with current counts: total sites, total images, states represented, total acreage, and managing agencies.
generate_metadata.py overwrites archive-metadata/archive.csv with a full metadata export for archival use.

---

## NATIVE LANDS FIELD STYLE GUIDE

Write as a flowing series of facts separated by semicolons. Include: nation names with indigenous-language names in parentheses where known, territorial context, specific historical events (battles, treaties) with dates, and forced removal or reservation outcome. The native-land.ca API results (nativeland_cache.json) give territory names as a starting point — use web search to fill in the historical narrative.

**Model entry:**
> Shawnee (Shawanwaki) · Miami · Adena and Hopewell cultures; Little Miami River a major Shawnee territory; Shawnee ceded Ohio lands via Treaty of Greene Ville 1795

Do not write generic statements. Be specific about which nations, which events, which dates.

---

## Lightbox and site page layout
Site pages mirror the map panel: the record column (geology block with era
swatch and timeline bar, then uppercase-labeled sections) flows with the page,
beside a sticky photo pane (height 100vh minus margins) holding a single-column
image scroll (.photo-scroll) with a "View all N images" viewer button pinned
beneath it (.photo-foot). Images are full pane width at natural aspect and load
the full img/jpg files directly (lazy loaded); thumbs/ are used only by the map
index panel. RAW/XMP sidecar paths ride on the figure as data-raw / data-xmp.
If a map thumbnail is missing, generate it from the JPG with PIL (400px q82
thumb, 1200px q88 lg_ prefix) into thumbs/<slug>/ before generating.

Site pages load js/lightbox.js at the bottom of <body>. It is the same viewer
design as the map index lightbox (counter top center, close top right, side
arrows, bottom meta bar) with Download TIFF / RAW File / XML actions reading the
figure hrefs and data attributes. It intercepts clicks on figure download links;
lightbox.js reads .caption-title and .caption-filename from the hidden figcaption
and prefers img data-full for the viewer image. Do not add onclick handlers or
image interaction logic to the page template. No changes to sites.json needed.

Wikimedia Commons is the canonical source for TIFF downloads. The generator
reads ../pli-commons/upload_log.json and links Download TIFF (and the Commons
page action) via Special:FilePath using the exact logged filename; images not
yet uploaded hide those actions until the next generate after upload. RAW and
XML (.xmp sidecar) downloads stay on DreamHost under img/RAW/. The archive
page lists Download TIFF, Download RAW, and XML per image, hiding any that are
unavailable.

On mobile (max-width: 719px), CSS order places the photo grid above the record
column. The desktop two-column layout (min-width: 720px) is unaffected.
