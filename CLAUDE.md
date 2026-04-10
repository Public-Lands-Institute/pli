# Public Lands Institute

Static photographic index of public lands. CC0 Public Domain.
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
Before deploying, archive the current generated files:
  DATE=$(date +%Y-%m-%d)
  mkdir -p Archive/$DATE/sites
  cp *.html Archive/$DATE/ 2>/dev/null || true
  cp sites/*.html Archive/$DATE/sites/ 2>/dev/null || true
  cp sites.json sites_meta.json nativeland_cache.json shadow_history_bibliography.txt shadow_history_methodology.txt Archive/$DATE/ 2>/dev/null || true
Then deploy (two-phase — keeps deploys fast even as image library grows):
  source .env
  # Phase 1: HTML/JS/JSON/text files — checksum-accurate, deletes removed files, skips images
  sshpass -p "$DREAMHOST_PASS" rsync -avz --checksum --delete \
    --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    --exclude '.git/' --exclude '.env' --exclude '.claude/' \
    --exclude 'Archive/' --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude '*.py' --exclude 'img/' \
    -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no" \
    . "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/"
  # Phase 2: Images — skip existing (images are immutable once uploaded, never re-checksum)
  sshpass -p "$DREAMHOST_PASS" rsync -avz --ignore-existing \
    --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
    -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no" \
    img/ "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/img/"

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

## research_metadata.py
Queries native-land.ca treaties API to populate displacement_tenure.
Run: python3 research_metadata.py
Safe to re-run; skips already-populated entries. Complex sites (Mammoth Cave, etc.) are flagged TODO for manual research.

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
- **displacement_tenure**: Land cession and tenure history. Run research_metadata.py after adding to sites.json, or manually research treaties. Format: "Ceded via [Treaty Name]; [additional context]." Complex cases (enslaved labor, litigation) require manual narrative.
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

### Step 4: Generate and deploy

Run python3 generate_sites.py and confirm the new .html file appears in the output list. Then deploy via lftp (archive first per deploy protocol above).

### Step 5: Generate metrics

After deploy completes, run:

  python3 generate_metrics.py

This overwrites PLI-Project-Metrics.txt in the project root with current counts: total sites, total images, states represented, total acreage, managing agencies, and Wikimedia Commons upload totals. The file is regenerated on every site addition and always reflects current state. This step runs automatically via a post-deploy hook when deploy.py is used; run it manually if deploying via rsync.

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
