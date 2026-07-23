"""
Export high-resolution work-sample JPEGs for the Loghaven residency application.

Loghaven requires: 8 JPEGs, one artwork per image, <=3MB each, no baked-in text
(captions are entered separately in the application form).

Pulls from the full-resolution TIFF source (img/full/<slug>/<file>.tif), resizes
to a ~4500px long edge, and exports at the highest JPEG quality that fits the
3MB cap (quality floor 80 — fails loudly rather than degrading further).
"""

import os
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

LONG_EDGE = 4500
MAX_BYTES = 3 * 1024 * 1024
QUALITY_FLOOR = 80
OUTPUT_DIR = "loghaven_submission"

SELECTIONS = [
    ("fernald-preserve", "_DSF1138.tif"),
    ("badlands-national-park", "_DSF2731.tif"),
    ("pipestone-national-monument", "_DSF2635.tif"),
    ("yellowstone-national-park", "_DSF3006.tif"),
    ("black-hills-national-forest", "_DSF2896.tif"),
    ("pointe-mouillee-state-game-area", "_DSF1837.tif"),
    ("ocmulgee-mounds-national-historical-park", "_DSF3792.tif"),
    ("ohoopee-dunes-wildlife-management-area", "_DSF3777.tif"),
]


def export(slug, filename):
    src = os.path.join("img", "full", slug, filename)
    src_im = Image.open(src).convert("RGB")
    w0, h0 = src_im.size

    dest = os.path.join(OUTPUT_DIR, f"{slug}.jpg")
    long_edge = LONG_EDGE
    while True:
        scale = long_edge / max(w0, h0)
        if scale < 1:
            im = src_im.resize((round(w0 * scale), round(h0 * scale)), Image.LANCZOS)
        else:
            im = src_im

        quality = 95
        while quality >= QUALITY_FLOOR:
            im.save(dest, "JPEG", quality=quality, optimize=True)
            size = os.path.getsize(dest)
            if size <= MAX_BYTES:
                return dest, im.size, size, quality
            quality -= 3

        # Quality floor reached without fitting; step down resolution and retry.
        if long_edge <= 2000:
            raise RuntimeError(
                f"{slug}: cannot fit under 3MB even at {long_edge}px / quality "
                f"{QUALITY_FLOOR} (got {size / 1024 / 1024:.2f}MB)"
            )
        long_edge = round(long_edge * 0.85)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"{'slug':<45} {'dims':<14} {'quality':<8} {'size':<10}")
    for slug, filename in SELECTIONS:
        dest, dims, size, quality = export(slug, filename)
        print(f"{slug:<45} {dims[0]}x{dims[1]:<8} {quality:<8} {size / 1024 / 1024:.2f}MB")


if __name__ == "__main__":
    main()
