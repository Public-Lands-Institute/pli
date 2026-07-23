"""
Portfolio plate generator — one composed JPEG per site: photograph + full
record text, styled to match the live site (dark theme, Inter, uppercase
tracked labels), for leave-behind / application portfolios.

Read CLAUDE.md, sites.json, sites_meta.json, and generate_sites.py before
changing this — the design tokens and geologic-era color table are copied
from the live site CSS / generator so plates stay visually consistent with
publiclandsinstitute.net. The live site is Inter on a dark ground, not the
EB Garamond / light palette an earlier draft of these instructions assumed.
"""

import argparse
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

CANVAS_WIDTH = 3400
MARGIN = 130
GUTTER = 80
MAX_BYTES = 10 * 1024 * 1024
QUALITY_FLOOR = 80

BG = (22, 22, 22)
FG = (232, 232, 232)
MUTED = (140, 140, 140)
RULE = (59, 59, 59)

FONT_DIR = "fonts"
FONTS = {
    "thin": os.path.join(FONT_DIR, "Inter-Thin.ttf"),
    "light": os.path.join(FONT_DIR, "Inter-Light.ttf"),
    "regular": os.path.join(FONT_DIR, "Inter-Regular.ttf"),
    "medium": os.path.join(FONT_DIR, "Inter-Medium.ttf"),
}
_font_cache = {}


def font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONTS[weight], size)
    return _font_cache[key]


# Same table as GEO_TIMESCALE in generate_sites.py — keep in sync.
GEO_TIMESCALE = [
    ('Archean', '#3a3a52', 4000), ('Proterozoic', '#5c5c8a', 2500),
    ('Cambrian', '#a0522d', 541), ('Ordovician', '#c8a86e', 485),
    ('Silurian', '#7ecfc0', 444), ('Devonian', '#4aaa78', 419),
    ('Mississippian', '#3d7fbf', 359), ('Pennsylvanian', '#5d5abf', 323),
    ('Permian', '#9b59b6', 299), ('Triassic', '#e07050', 252),
    ('Jurassic', '#c8a840', 201), ('Cretaceous', '#d4b840', 145),
    ('Paleogene', '#d4704a', 66), ('Eocene', '#d4704a', 56), ('Oligocene', '#d4704a', 34),
    ('Neogene', '#c85a8a', 23),
    ('Quaternary', '#8c8c8c', 2.6), ('Pleistocene', '#8c8c8c', 2.6),
]
EARTH_TIMELINE_MYA = 541


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def match_era(geo_text, epoch_text):
    combined = geo_text + ('; ' + epoch_text if epoch_text else '')
    clauses = re.split(r'[;.]', combined)
    best = None
    for clause in clauses:
        c = clause.lower()
        for era, color, oldest in GEO_TIMESCALE:
            if era.lower() in c and (best is None or oldest > best[2]):
                best = (era, color, oldest)
    if not best:
        return None
    era, color, oldest = best
    pct = min(100, round(oldest / EARTH_TIMELINE_MYA * 100))
    return era, hex_to_rgb(color), pct


def wrap_text(text, fnt, max_width):
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_tracked(draw, xy, text, fnt, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += fnt.getlength(ch) + tracking
    return x


def tracked_width(text, fnt, tracking):
    return sum(fnt.getlength(ch) + tracking for ch in text) - (tracking if text else 0)


FIELD_ORDER = [
    ("geological_age", "Geologic Age"),
    ("epoch", "Epoch"),
    ("native_lands", "Native Lands"),
    ("displacement_tenure", "Displacement & Tenure"),
    ("shadow_history", "Shadow History"),
    ("ecology", "Ecology"),
    ("hydrology", "Hydrology"),
    ("acreage", "Acreage"),
    ("gps", "GPS"),
]

LABEL_SIZE = 24
LABEL_TRACKING = 3
BODY_SIZE = 32
BODY_LINE_HEIGHT = round(BODY_SIZE * 1.65)
SECTION_GAP = 46
RULE_GAP = 28


def section_lines(field_key, text, col_width):
    fnt = font("light", BODY_SIZE)
    if field_key == "geological_age":
        # era row + bar occupy fixed extra height, handled by caller
        return wrap_text(text, fnt, col_width)
    return wrap_text(text, fnt, col_width)


def measure_section_height(field_key, text, col_width, era_info):
    lines = section_lines(field_key, text, col_width)
    h = RULE_GAP + LABEL_SIZE + 14
    if field_key == "geological_age" and era_info:
        h += 34 + 14  # era row
        h += 10 + 14  # bar
    h += len(lines) * BODY_LINE_HEIGHT
    h += SECTION_GAP
    return h, lines


def draw_section(draw, x, y, col_width, label, field_key, text, era_info):
    draw.line([(x, y), (x + col_width, y)], fill=RULE, width=2)
    y += RULE_GAP
    draw_tracked(draw, (x, y), label.upper(), font("medium", LABEL_SIZE), MUTED, LABEL_TRACKING)
    y += LABEL_SIZE + 14

    if field_key == "geological_age" and era_info:
        era, color, pct = era_info
        r = 9
        draw.ellipse([x, y, x + r * 2, y + r * 2], fill=color)
        draw.text((x + r * 2 + 16, y - 4), era, font=font("light", 30), fill=FG)
        y += 34 + 14
        bar_w = col_width
        draw.rectangle([x, y, x + bar_w, y + 8], fill=(42, 42, 42))
        draw.rectangle([x, y, x + round(bar_w * pct / 100), y + 8], fill=color)
        y += 10 + 14

    body_font = font("light", BODY_SIZE)
    for line in wrap_text(text, body_font, col_width):
        draw.text((x, y), line, font=body_font, fill=FG)
        y += BODY_LINE_HEIGHT
    y += SECTION_GAP
    return y


def build_plate(site, agency):
    slug = site["slug"]
    img_name = site.get("portfolio_image")
    jpg_dir = os.path.join("img", "jpg", slug)
    if img_name:
        photo_path = os.path.join(jpg_dir, img_name)
        if not os.path.isfile(photo_path):
            raise FileNotFoundError(f"{slug}: portfolio_image {img_name} not found in {jpg_dir}")
    else:
        candidates = sorted(f for f in os.listdir(jpg_dir) if f.lower().endswith((".jpg", ".jpeg")))
        if not candidates:
            raise FileNotFoundError(f"{slug}: no images in {jpg_dir}")
        photo_path = os.path.join(jpg_dir, candidates[0])

    photo = Image.open(photo_path).convert("RGB")
    pw, ph = photo.size
    photo_w = CANVAS_WIDTH - 2 * MARGIN
    photo_h = round(photo_w * ph / pw)
    photo_resized = photo.resize((photo_w, photo_h), Image.LANCZOS)
    offset_x = MARGIN

    fields = [(key, label, site.get(key, "")) for key, label in FIELD_ORDER]
    fields = [(k, l, t) for k, l, t in fields if t]

    era_info = match_era(site.get("geological_age", ""), site.get("epoch", ""))

    content_width = CANVAS_WIDTH - 2 * MARGIN
    total_chars = sum(len(t) for k, l, t in fields if k not in ("acreage", "gps"))
    two_col = total_chars > 1600
    col_width = (content_width - GUTTER) // 2 if two_col else content_width

    heights = []
    for k, l, t in fields:
        h, _ = measure_section_height(k, t, col_width, era_info if k == "geological_age" else None)
        heights.append(h)
    total_text_h = sum(heights)

    if two_col:
        col1, col2, h1, h2 = [], [], 0, 0
        for (k, l, t), h in zip(fields, heights):
            if h1 <= h2:
                col1.append((k, l, t))
                h1 += h
            else:
                col2.append((k, l, t))
                h2 += h
        record_h = max(h1, h2)
    else:
        col1, col2 = fields, []
        record_h = total_text_h

    header_h = 118 + 44 + 40  # name + state line + gap
    footer_h = 90
    total_h = MARGIN + photo_h + 56 + header_h + record_h + footer_h + MARGIN

    canvas = Image.new("RGB", (CANVAS_WIDTH, total_h), BG)
    canvas.paste(photo_resized, (offset_x, MARGIN))
    draw = ImageDraw.Draw(canvas)

    y = MARGIN + photo_h + 56
    draw.text((MARGIN, y), site["name"], font=font("light", 92), fill=FG)
    y += 118
    subhead = f"{site['state']}   ·   {agency.upper()}"
    draw_tracked(draw, (MARGIN, y), subhead, font("medium", 30), MUTED, 4)
    y += 44 + 40

    x1 = MARGIN
    yy1 = y
    for k, l, t in col1:
        yy1 = draw_section(draw, x1, yy1, col_width, l, k, t, era_info if k == "geological_age" else None)

    if two_col:
        x2 = MARGIN + col_width + GUTTER
        yy2 = y
        for k, l, t in col2:
            yy2 = draw_section(draw, x2, yy2, col_width, l, k, t, era_info if k == "geological_age" else None)
        y = max(yy1, yy2)
    else:
        y = yy1

    y += footer_h - 40
    draw.line([(MARGIN, y), (CANVAS_WIDTH - MARGIN, y)], fill=RULE, width=2)
    y += 24
    draw.text((MARGIN, y), "PUBLIC LANDS INSTITUTE  ·  JORDAN TATE", font=font("regular", 24), fill=MUTED)

    return canvas


def export(canvas, dest):
    quality = 95
    while quality >= QUALITY_FLOOR:
        canvas.save(dest, "JPEG", quality=quality, optimize=True)
        size = os.path.getsize(dest)
        if size <= MAX_BYTES:
            return size, quality
        quality -= 3
    size = os.path.getsize(dest)
    if size > MAX_BYTES:
        raise RuntimeError(
            f"{dest}: cannot fit under {MAX_BYTES / 1024 / 1024:.0f}MB at quality "
            f"floor {QUALITY_FLOOR} (got {size / 1024 / 1024:.2f}MB)"
        )
    return size, quality


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site")
    ap.add_argument("--sites")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sites = json.load(open("sites.json"))
    meta = json.load(open("sites_meta.json"))

    if args.site:
        slugs = [args.site]
    elif args.sites:
        slugs = [s.strip() for s in args.sites.split(",")]
    else:
        slugs = [s["slug"] for s in sites]

    by_slug = {s["slug"]: s for s in sites}
    os.makedirs("portfolio", exist_ok=True)

    for slug in slugs:
        site = by_slug.get(slug)
        if not site:
            print(f"SKIP {slug}: not found in sites.json")
            continue
        agency = meta.get(slug, {}).get("agency", "")
        dest = os.path.join("portfolio", f"{slug}.jpg")
        if args.dry_run:
            print(f"WOULD GENERATE {dest}")
            continue
        canvas = build_plate(site, agency)
        size, quality = export(canvas, dest)
        print(f"{slug:<45} {canvas.size[0]}x{canvas.size[1]:<10} q{quality:<4} {size / 1024 / 1024:.2f}MB")


if __name__ == "__main__":
    main()
