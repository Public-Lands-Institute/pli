"""
Portfolio builder export: write a numbered, captioned image set to a folder on the Desktop.

Run from the pli folder on your Mac:
    cd "/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli"
    python3 path/to/export_portfolio.py

Reads the TIFF masters in img/full/<slug>/<frame>.tif and writes, for each image:
JPG, sRGB, 72 dpi, 4000 px on the long edge, named NN_slug_frame.jpg in upload order.
Also writes captions.txt with the numbered captions. Never upscales: if a master is
smaller than 4000 px, or only the 2048 px img/jpg copy exists, it says so.
"""

import io
import os
import sys
from PIL import Image, ImageCms

Image.MAX_IMAGE_PIXELS = None

LONG_EDGE = 4000  # set to what the application asks for
DPI = (72, 72)
QUALITY = 95
OUT = os.path.expanduser("~/Desktop/Portfolio-Export")  # rename per application

# Fill from the final list: (upload number, site slug, frame, full caption).
SELECTION = [
    # (1, "big-oaks-national-wildlife-refuge", "_DSF4301",
    #  "Big Oaks National Wildlife Refuge, Indiana. ..."),
]

SRGB = ImageCms.createProfile("sRGB")
SRGB_BYTES = ImageCms.ImageCmsProfile(SRGB).tobytes()


# Frames filed under a different site folder than the one named in the caption.
SOURCE_SLUG = {"_DSF0602": "charons-garden-wilderness-area"}


def find_source(slug, frame):
    slug = SOURCE_SLUG.get(frame, slug)
    for folder, exts in (("full", (".tif", ".tiff", ".TIF", ".TIFF")), ("jpg", (".jpg", ".JPG", ".jpeg"))):
        for ext in exts:
            p = os.path.join("img", folder, slug, frame + ext)
            if os.path.exists(p):
                return p, folder
    return None, None


def to_8bit_rgb(im):
    # 16-bit greyscale TIFFs: scale down to 8 bits before converting.
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        im = im.point(lambda v: v / 256).convert("L")
    return im


def to_srgb(im):
    icc = im.info.get("icc_profile")
    im = to_8bit_rgb(im)
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            out_mode = "RGB"
            if im.mode == "L":
                im = im.convert("RGB")
            return ImageCms.profileToProfile(im, src, SRGB, outputMode=out_mode)
        except Exception as e:
            print(f"    colour profile not applied ({e}); converting directly")
    return im.convert("RGB")


def main():
    if not os.path.isdir("img"):
        sys.exit("Run this from the pli folder (the one containing img/).")
    os.makedirs(OUT, exist_ok=True)
    problems = []
    captions = []
    for n, slug, frame, caption in SELECTION:
        src, kind = find_source(slug, frame)
        name = f"{n:02d}_{slug}_{frame.lstrip('_')}.jpg"
        captions.append(f"{n:02d}  {name}\n{caption}\n")
        if not src:
            problems.append(f"{name}: no file found in img/full/{SOURCE_SLUG.get(frame, slug)}/ or img/jpg/{SOURCE_SLUG.get(frame, slug)}/")
            continue
        im = to_srgb(Image.open(src))
        w, h = im.size
        if max(w, h) > LONG_EDGE:
            s = LONG_EDGE / max(w, h)
            im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
        elif max(w, h) < LONG_EDGE:
            problems.append(f"{name}: source is only {max(w, h)} px ({src}); exported at that size, not upscaled")
        im.save(os.path.join(OUT, name), "JPEG", quality=QUALITY, dpi=DPI, icc_profile=SRGB_BYTES, optimize=True)
        print(f"{name:<70} {im.size[0]}x{im.size[1]}  from {kind}")
    with open(os.path.join(OUT, "captions.txt"), "w") as f:
        f.write("\n".join(captions))
    print(f"\nWrote {OUT}")
    if problems:
        print("\nCheck these:")
        for p in problems:
            print("  " + p)


if __name__ == "__main__":
    main()
