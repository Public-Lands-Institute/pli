from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

slug = "silver-lake-state-park"
JPG_DIR = Path("img/jpg") / slug
THUMB_DIR = Path("thumbs") / slug
THUMB_DIR.mkdir(parents=True, exist_ok=True)

for src in sorted(JPG_DIR.glob("*.jpg")):
    thumb = THUMB_DIR / src.name
    large = THUMB_DIR / ("lg_" + src.name)
    if not thumb.exists():
        im = Image.open(src)
        im.thumbnail((400, 400))
        im.save(thumb, "JPEG", quality=82, optimize=True)
    if not large.exists():
        im = Image.open(src)
        im.thumbnail((1200, 1200))
        im.save(large, "JPEG", quality=88, optimize=True)

print("thumbs:", len(list(THUMB_DIR.glob("*.jpg"))))
