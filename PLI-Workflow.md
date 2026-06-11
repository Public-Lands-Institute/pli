# Public Lands Institute — Step-by-Step Workflow

Last verified against code 2026-06-09 (generate_sites.py, upload_next.py).

---

## A. Adding a New Site ("gotime [site name]")

### 1. Confirm the official name and slug
Confirm the full official name before doing anything else — it drives folder names, Commons filenames, JSON keys, and the slug.
Slug format: lowercase, hyphenated (e.g. `bighorn-national-forest`).

### 2. Create image folders immediately
Do this right after confirming the name — before research is done — so photos can be dropped in while research is in progress:
```bash
mkdir -p img/jpg/<slug> img/full/<slug>
```
RAW files (`.NEF`/`.RAF`/`.xmp`) go in the shared flat folder `img/RAW/` (not per-slug).

### 3. Research every field
Read first, to match tone and avoid duplication:
- `sites.json` (first ~60 lines for structure/format)
- `sites_meta.json` (full)
- `shadow_history_bibliography.txt` (full)
- `nativeland_cache.json` (grep for the new slug — too large to read whole)

Research and source every field:
`geological_age, epoch, native_lands, displacement_tenure, shadow_history, ecology, hydrology, acreage, conservation_status, endangered_species, gps, lat, lng, inat_radius_km`, plus `agency, agency_type, territory` for `sites_meta.json`.

### 4. Verify before presenting
Run the factual-accuracy audit on every field (see Section E below) — endonyms, treaty language, sourced numbers, and especially the **shadow_history "underreported" test**. Silently apply clear corrections; flag anything unresolved.

### 5. Present the draft and wait for approval
Show all fields in a readable summary. **Hard stop** — do not write anything until the user confirms or corrects.

### 6. Write the approved entry to three files
- **`sites.json`** — insert at position 0 (top of array). Field order:
  `geological_age, epoch, native_lands, displacement_tenure, shadow_history, ecology, hydrology, acreage` (displayed), then `conservation_status, endangered_species, gps, lat, lng, inat_radius_km` (not displayed).
- **`sites_meta.json`** — insert new key at top:
  ```json
  "slug": { "agency": "...", "agency_type": "...", "territory": ["Nation1", "Nation2"] }
  ```
- **`shadow_history_bibliography.txt`** — if `shadow_history` is non-empty, add a new section at the top (after header lines) listing sources consulted, in the same format as existing sections. Update the "Generated" date.

### 7. Wait for photos
Ask the user to drop JPGs into `img/jpg/<slug>/`, TIFFs into `img/full/<slug>/`, and RAW+XMP into `img/RAW/`. **Hard stop** — do not proceed until confirmed ready.

### 8. Upload TIFFs to Commons
```bash
cd ~/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli-commons
python3 upload_next.py --site <slug>
```
With `--site`, this uploads the **entire pending folder for that site in one run** (no 5-image cap — that cap only applies to the old no-filter cron mode). Falls back to JPG if no TIFF exists. Names files `Public Lands Institute - {Site Name} - NNN.tif` (zero-padded, stable per `upload_log.json`).

This must happen **before** generation — `generate_sites.py` builds the same `Public Lands Institute - {site name} - NNN.tif` filename deterministically for the lightbox's Commons/raw/XML download links, and those links 404 until the matching Commons file exists.

### 9. Generate thumbnails for the new slug
`generate_sites.py` does **not** create `thumbs/<slug>/` itself. If it's missing, the new site silently shows **zero images** on the index, lightbox, and archive — even though `img/jpg/<slug>/` is fully populated. Before running the generator:
```python
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

slug = "<slug>"
JPG_DIR = Path("img/jpg") / slug
THUMB_DIR = Path("thumbs") / slug
THUMB_DIR.mkdir(parents=True, exist_ok=True)

for src_jpg in sorted(JPG_DIR.glob("*.jpg")):
    thumb = THUMB_DIR / src_jpg.name
    large = THUMB_DIR / ("lg_" + src_jpg.name)
    if not thumb.exists():
        img = Image.open(src_jpg); img.thumbnail((400, 400))
        img.save(thumb, 'JPEG', quality=82, optimize=True)
    if not large.exists():
        img = Image.open(src_jpg); img.thumbnail((1200, 1200))
        img.save(large, 'JPEG', quality=88, optimize=True)
```
Produces `thumbs/<slug>/<filename>.jpg` (400x400, q82) and `thumbs/<slug>/lg_<filename>.jpg` (1200x1200, q88).

### 10. Generate
```bash
python3 generate_sites.py
```
Verify the new slug appears with populated `thumb`/`large` paths in the generated `PHOTOS` dict before proceeding.

### 11. Image upload to DreamHost
JPGs and shared RAW only — **never `img/full/` (TIFFs go to Commons only, not DreamHost)**:
```bash
cd "/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli"
source .env
sshpass -p "$DREAMHOST_PASS" rsync -av \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3" \
  img/jpg/<slug>/ "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/img/jpg/<slug>/"
sshpass -p "$DREAMHOST_PASS" rsync -av \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3" \
  img/RAW/ "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/img/RAW/"
```
No `-z` flag — JPGs/TIFFs are already compressed. `img/RAW/` is a flat shared folder synced in full every time; rsync skips files already matching by size/mtime, so only new files actually transfer despite walking the whole 89GB tree.

### 12. Archive, regenerate confirmation, HTML/JSON deploy, metrics
Same as Section B (Update workflow) below, steps 2-4.

---

## B. Updating an Existing Site with New Images ("update [site]")

### 1. Add photos
JPG → `img/jpg/<slug>/`, TIFF → `img/full/<slug>/`, RAW+XMP → `img/RAW/`.

### 2. Upload + image deploy
```bash
cd ~/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli-commons
python3 upload_next.py --site <slug>
```
Then the same JPG + RAW rsync as Section A step 11.

### 3. Regenerate, archive, deploy
```bash
cd "/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli"
python3 generate_sites.py
STAMP=$(date +%Y-%m-%d_%H-%M)
mkdir -p Archive/$STAMP/sites
cp *.html Archive/$STAMP/ 2>/dev/null || true
cp sites/*.html Archive/$STAMP/sites/ 2>/dev/null || true
cp sites.json sites_meta.json nativeland_cache.json shadow_history_bibliography.txt shadow_history_methodology.txt Archive/$STAMP/ 2>/dev/null || true
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
```

### 4. HTML/JSON deploy (3 phases — always all 3)
```bash
source .env
# Phase 2: HTML/JS/JSON/text — checksum-accurate, deletes removed files, skips images and .py
sshpass -p "$DREAMHOST_PASS" rsync -avz --checksum --delete \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  --exclude '.git/' --exclude '.env' --exclude '.claude/' \
  --exclude 'Archive/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '*.py' --exclude 'img/' \
  -e "ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3" \
  . "$DREAMHOST_USER@$DREAMHOST_HOST:$DREAMHOST_REMOTE_PATH/"
# Phase 3 (mandatory every deploy): fix permissions on existing files, not just transferred ones
sshpass -p "$DREAMHOST_PASS" ssh \
  -o StrictHostKeyChecking=no -o PubkeyAuthentication=no -o ControlMaster=auto -o ControlPath=/tmp/pli_ssh_mux -o ControlPersist=300 -o ServerAliveInterval=60 -o ServerAliveCountMax=3 \
  "$DREAMHOST_USER@$DREAMHOST_HOST" \
  "find $DREAMHOST_REMOTE_PATH -type d -exec chmod 755 {} + && find $DREAMHOST_REMOTE_PATH -type f -exec chmod 644 {} +"
python3 generate_metrics.py && python3 generate_metadata.py
```

---

## C. Standalone Archive ("archive")

Point-in-time snapshot, copy-only, distinct from the dated deploy archives:
```bash
FOLDER="Instance ($(python3 -c 'import datetime; n=datetime.datetime.now(); print(f"{n.month}-{n.day} {n.hour}-{n.minute:02d}")'))"
mkdir -p "Archive/$FOLDER/sites"
cp *.html "Archive/$FOLDER/" 2>/dev/null || true
cp sites/*.html "Archive/$FOLDER/sites/" 2>/dev/null || true
cp sites.json sites_meta.json inaturalist_cache.json nativeland_cache.json shadow_history_bibliography.txt shadow_history_methodology.txt PLI-Project-Metrics.txt "Archive/$FOLDER/" 2>/dev/null || true
echo "Archived to Archive/$FOLDER"
```
Prune `Instance *` folders older than 30 days, always keeping the two most recent.

---

## D. Standalone Verify ("verify [site]")

Same audit as Section E, runnable independently against a proposed or existing entry. Output format: state what was verified, what was corrected, and what needs a user decision. Never silent — always end with a confirmation or a flag list.

---

## E. Factual Accuracy Audit (embedded in gotime, also standalone as "verify")

- **Terminology**: check every Indigenous endonym against tribal nation sites, Wikipedia, native-land.ca. Remove or substitute if unverifiable — never invent.
- **Evidentiary basis**: for "archaeological evidence" claims, confirm whether the source is archaeology, written record, or oral tradition, and attribute correctly.
- **Treaty language**: fetch actual treaty terms for every treaty named. Distinguish cession vs. hunting-rights surrender vs. boundary recognition. Never say "ceded" for a treaty that only restricted use.
- **Qualifiers**: remove "nominally," "reportedly," etc. unless directly supported by a cited source.
- **Numerical claims**: verify dates, acreage, public law numbers against NPS/federal legislation/census data. Flag anything unsourceable.
- **Agency/contamination claims**: confirm pollution claims are documented by EPA/NPS/peer-review for THIS site specifically, not the region generally.
- **GPS/acreage**: spot-check against PAD-US or the managing agency.
- **NAGPRA**: check the Federal Register for Notices of Inventory Completion if relevant. Cite or omit.
- **Named individuals in shadow history**: only include if directly attributed in a verifiable source. Flag candidates for user confirmation, never infer.
- **Shadow history "underreported" test** (added 2026-06-09): shadow_history means industrial contamination, forced removal, segregated/exploitative labor, archaeological extraction, or institutional abuse that is *documented but underreported*. If the managing agency already has an interpretive sign or a heritage page celebrating the item (e.g. "Tie Hack Era," pioneer railroad lore), it is the **opposite** of underreported and does not belong in shadow_history — even if true and well-sourced. Don't pad the field to make it feel substantive; an empty or one-item shadow_history is a correct result if that's what the research supports.

### Royce cession / displacement_tenure notes
- Most Midwest/West sites: cite Royce cession numbers (USFS Tribal Ceded Lands layer or TNGenNet).
- **Kentucky, Tennessee, and other non-federal-domain states**: no Royce cession applies (Royce has no maps for KY/MD/VA/SC). Document the colonial-era dispossession chain instead (Fort Stanwix 1768, Hard Labour/Lochaber, Camp Charlotte 1774, Sycamore Shoals/Henderson's Purchase 1775, VA military bounty grants) and note explicitly "no federal Royce cession applies."
- To check: query `https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TribalCessionLands_01/MapServer/0` for the site coordinates — no features returned means no Royce cession applies.

---

## F. Hard rules (never violate)

- No em dashes or en dashes anywhere in output or field values.
- Never add an "images" count field to sites.json.
- Plain numeric captions (1, 2, 3...), not roman numerals.
- New sites always go at position 0 in `sites.json` and the top of `sites_meta.json`.
- `img/full/` (TIFFs) → Commons only, **never** rsynced to DreamHost.
- `img/jpg/` and `img/RAW/` → DreamHost.
- Always run `generate_sites.py` and confirm output (including `thumbs/<slug>/` populated) before deploying.
- Always deploy after generating, unless told otherwise.
- Always run all 3 deploy phases — chmod (phase 3) is mandatory every time, not just when files changed.
- Never use git worktrees for this project; always work in the main repo.
- Never use browser preview tools — they don't work in this environment.
- Re-read CLAUDE.md + this document at the start of every new-site request, even mid-session.

---

## G. Known issue to watch

`generate_sites.py` builds Commons filenames as `Public Lands Institute - {site name} - {i+1:03d}.tif` based on the **current alphabetical order** of images for that site at generation time. `upload_next.py` assigns numbers **stably** (logged in `upload_log.json`, never reassigned once set). If images are added out of alphabetical order relative to existing ones, or a JPG-only entry is later replaced by a TIFF, these two numbering schemes can diverge and produce 404s on Commons/raw download links. If a site's download links 404 after an update, check `upload_log.json` numbering against the generated page's archive filenames first.
