#!/bin/bash
# deploy.sh — rebuild site and push to GitHub
set -e

PLI_DIR="$(cd "$(dirname "$0")" && pwd)"
COMMONS_DIR="$(dirname "$PLI_DIR")/pli-commons"
BUILD_SCRIPT="/tmp/build_pli.py"

echo "==> Generating thumbnails for new photos..."
python3 - << 'PYEOF'
import json, shutil
from pathlib import Path
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

IMG_BASE  = Path.home() / "Library/CloudStorage/OneDrive-UniversityofCincinnati/pli/img"
THUMB_DIR = Path.home() / "Library/CloudStorage/OneDrive-UniversityofCincinnati/pli/thumbs"
LOG_PATH  = Path.home() / "Library/CloudStorage/OneDrive-UniversityofCincinnati/pli-commons/upload_log.json"
MAP_PATH  = Path("/tmp/pli_photo_map.json")

log = json.load(open(LOG_PATH))
photo_map = json.load(open(MAP_PATH)) if MAP_PATH.exists() else {}

made = 0
for e in log:
    fname   = e['commons_filename']
    slug    = e['slug']
    src_jpg = IMG_BASE / 'jpg' / slug / Path(e['source_path']).with_suffix('.jpg').name
    if not src_jpg.exists():
        continue

    thumb_dir = THUMB_DIR / slug
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb  = thumb_dir / src_jpg.name
    large  = thumb_dir / ('lg_' + src_jpg.name)

    entry = photo_map.get(fname) or {}
    changed = False

    if not thumb.exists():
        img = Image.open(src_jpg); img.thumbnail((400, 400))
        img.save(thumb, 'JPEG', quality=82, optimize=True)
        changed = True; made += 1

    if not large.exists():
        img = Image.open(src_jpg); img.thumbnail((1200, 1200))
        img.save(large, 'JPEG', quality=88, optimize=True)
        changed = True

    if changed or not entry:
        PLI_THUMBS = str(THUMB_DIR)
        photo_map[fname] = {
            'thumb': str(thumb),
            'large': str(large),
            'date':  e.get('uploaded_at','')[:10],
        }

json.dump(photo_map, open(MAP_PATH, 'w'))
print(f"  {made} new thumbnails generated")
PYEOF

echo "==> Rebuilding index.html..."
python3 "$BUILD_SCRIPT"

echo "==> Staging and committing..."
cd "$PLI_DIR"
git add index.html thumbs/

if git diff --cached --quiet; then
    echo "  Nothing new to commit."
else
    git commit -m "Rebuild site — updated photos and content

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
fi

echo "==> Pushing to GitHub..."
git push

echo "==> Done. Live at https://publiclandsinstitute.net/"
