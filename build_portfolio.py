#!/usr/bin/env python3
"""Build PLI photographic portfolio PDFs (10 / 15 / 20 page editions).

One page per site: a horizontal hero image across the top, then the site's own
record text flowing in two columns beneath it, reproduced VERBATIM from
sites.json under the site's own labels (Geology / Epoch / Native lands /
Displacement & Tenure / Shadow History / Ecology / Hydrology / Acreage / GPS),
in the same order the website renders. No invented captions. Text fills the
column area and clips at the frame edge (as much as fits). Endonyms render via
Arial Unicode MS. Editions are nested supersets of a single 17-site selection.
"""
import os, json
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "img", "jpg")
CACHE = "/tmp/pli_portfolio_cache"
os.makedirs(CACHE, exist_ok=True)

# Unicode body font for endonyms (Šakówiŋ, Nʉmʉnʉʉ, etc.)
UNI = "Helvetica"
for cand in ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
             "/Library/Fonts/Arial Unicode.ttf"]:
    if os.path.exists(cand):
        pdfmetrics.registerFont(TTFont("AUni", cand)); UNI = "AUni"; break

PW, PH = letter
INK = (0.10, 0.10, 0.10)
GRAY = (0.45, 0.45, 0.45)
FAINT = (0.74, 0.74, 0.74)
M = 42

SITES = {s["slug"]: s for s in json.load(open(os.path.join(ROOT, "sites.json")))}
META = json.load(open(os.path.join(ROOT, "sites_meta.json")))
TOTAL_SITES = len(SITES)

PROJECT = ("The Public Lands Institute is an ongoing photographic index of American "
    "public lands. Each site is recorded alongside its geological, ecological, and "
    "land use history: treaty cessions, designation changes, industrial "
    "contamination, and remediation. Every image is released into the public domain "
    "under CC0 and distributed through Wikimedia Commons for unrestricted use.")

SOURCES = ("Site records draw on primary repositories: EPA Superfund and cleanup "
    "databases; National Park Service administrative histories; National Archives "
    "Civilian Conservation Corps records; Library of Congress Chronicling America; "
    "federal and state court records; Royce cession maps and treaty texts; "
    "native-land.ca territory data; and iNaturalist research grade observations. "
    "Travel writing, tourism copy, and managing agency press releases are not "
    "accepted as sources.")

# one chosen image per site (1-based picks from the photographer, resolved to file)
IMG = {
 "pipestone-national-monument": "_DSF2635.jpg",
 "badlands-national-park": "_DSF2731.jpg",
 "mount-rushmore-national-memorial": "_DSF2816.jpg",
 "yellowstone-national-park": "_DSF3006.jpg",
 "wichita-mountains-national-wildlife-refuge": "_DSF0670.jpg",
 "hopewell-culture-national-historical-park": "_DSF1437.jpg",
 "mounds-state-park": "_DSF2411.jpg",
 "mammoth-cave-national-park": "_DSF0923.jpg",
 "pine-hills-nature-preserve": "_DSF2294.jpg",
 "shades-state-park": "_DSF2279.jpg",
 "new-river-gorge-national-park": "_DSF1372.jpg",
 "red-river-gorge-geological-area": "_DSF1505.jpg",
 "krejci-dump": "_DSF2105.jpg",
 "cuyahoga-valley-national-park": "_DSF2152.jpg",
 "fernald-preserve": "_DSF1138.jpg",
 "pointe-mouillee-state-game-area": "_DSF1831.jpg",
 "bryce-canyon-national-park": "_DSF3216.jpg",
 "fort-hill-state-memorial": "_DSF2222.jpg",
}

FIELDS = [
 ("Geology", "geological_age"),
 ("Epoch", "epoch"),
 ("Native lands", "native_lands"),
 ("Displacement & Tenure", "displacement_tenure"),
 ("Shadow History", "shadow_history"),
 ("Ecology", "ecology"),
 ("Hydrology", "hydrology"),
 ("Acreage", "acreage"),
 ("GPS", "gps"),
]

TEN = ["pipestone-national-monument", "badlands-national-park", "yellowstone-national-park",
       "mammoth-cave-national-park", "fernald-preserve", "new-river-gorge-national-park",
       "red-river-gorge-geological-area", "pine-hills-nature-preserve", "krejci-dump"]
FIFTEEN = TEN + ["mount-rushmore-national-memorial",
       "hopewell-culture-national-historical-park", "cuyahoga-valley-national-park",
       "shades-state-park", "wichita-mountains-national-wildlife-refuge"]
TWENTY = FIFTEEN + ["mounds-state-park", "pointe-mouillee-state-game-area",
       "bryce-canyon-national-park", "fort-hill-state-memorial"]

def prep(rel, maxedge=1500):
    src = os.path.join(SRC, rel)
    key = os.path.join(CACHE, rel.replace("/", "__"))
    im = Image.open(src)
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    s = min(1.0, maxedge / max(w, h))
    if s < 1.0:
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    im.save(key, "JPEG", quality=86)
    return key, im.size[0], im.size[1]


SITE_BASE = "https://publiclandsinstitute.net"
COMMONS = "https://commons.wikimedia.org/w/index.php?search=Public+Lands+Institute"


def site_url(slug):
    return "%s/sites/%s.html" % (SITE_BASE, slug)


def tracked(c, x, y, text, font, size, color, tr=0.0):
    t = c.beginText(x, y); t.setFont(font, size); t.setFillColorRGB(*color)
    t.setCharSpace(tr); t.textOut(text); c.drawText(t)


def twidth(c, text, font, size, tr=0.0):
    return c.stringWidth(text, font, size) + tr * max(0, len(text) - 1)


def link_line(c, x, y, segments, font, size, color, tr=0.0):
    """Draw a line of (text, url|None) segments; url segments become clickable."""
    for text, url in segments:
        tracked(c, x, y, text, font, size, color, tr)
        w = twidth(c, text, font, size, tr)
        if url:
            c.linkURL(url, (x, y - 2, x + w, y + size - 1), relative=0, thickness=0)
        x += w + tr
    return x


def footer(c):
    c.setStrokeColorRGB(*FAINT); c.setLineWidth(0.5); c.line(M, 46, PW - M, 46)
    link_line(c, M, 33, [("PUBLIC LANDS INSTITUTE  ·  JORDAN TATE", SITE_BASE)],
              "Helvetica", 7, GRAY, 1.1)


def title_page(c):
    c.setFillColorRGB(1, 1, 1); c.rect(0, 0, PW, PH, fill=1, stroke=0)
    LM = 64
    tracked(c, LM, PH - 150, "PUBLIC LANDS", "Helvetica-Bold", 30, INK, 1.5)
    tracked(c, LM, PH - 186, "INSTITUTE", "Helvetica-Bold", 30, INK, 1.5)
    c.setStrokeColorRGB(*INK); c.setLineWidth(1.1); c.line(LM, PH - 206, PW - LM, PH - 206)
    tracked(c, LM, PH - 226, "PHOTOGRAPHIC PORTFOLIO", "Helvetica", 10.5, GRAY, 2.6)
    t = c.beginText(LM, PH - 300); t.setFont("Helvetica", 10.5); t.setLeading(16)
    t.setFillColorRGB(*INK); t.setCharSpace(0)
    for ln in simpleSplit(PROJECT, "Helvetica", 10.5, PW - 2 * LM - 40):
        t.textLine(ln)
    c.drawText(t)
    tracked(c, LM, 196, "JORDAN TATE", "Helvetica-Bold", 13, INK, 1.2)
    c.setStrokeColorRGB(*FAINT); c.setLineWidth(0.6); c.line(LM, 84, PW - LM, 84)
    link_line(c, LM, 66, [
        ("CC0 PUBLIC DOMAIN  ·  DISTRIBUTED VIA ", None),
        ("WIKIMEDIA COMMONS", COMMONS),
        ("  ·  ", None),
        ("PUBLICLANDSINSTITUTE.NET", SITE_BASE),
    ], "Helvetica", 8, GRAY, 1.4)
    c.showPage()


def site_page(c, slug):
    s = SITES[slug]
    url = site_url(slug)
    c.setFillColorRGB(1, 1, 1); c.rect(0, 0, PW, PH, fill=1, stroke=0)
    # hero image, full content width, top
    path = prep("%s/%s" % (slug, IMG[slug]))
    p, iw, ih = path
    box_w = PW - 2 * M
    draw_w = box_w
    draw_h = box_w * ih / iw
    if draw_h > 388:
        draw_h = 388; draw_w = draw_h * iw / ih
    x = M + (box_w - draw_w) / 2
    top = PH - 44
    c.drawImage(p, x, top - draw_h, width=draw_w, height=draw_h, mask=None)
    c.setStrokeColorRGB(*FAINT); c.setLineWidth(0.5)
    c.rect(x, top - draw_h, draw_w, draw_h, fill=0, stroke=1)
    img_bottom = top - draw_h
    # title block (linked to the site's record page)
    ty = img_bottom - 22
    tracked(c, M, ty, s["name"], "Helvetica-Bold", 14, INK, 0.2)
    c.linkURL(url, (M, ty - 3, M + twidth(c, s["name"], "Helvetica-Bold", 14, 0.2), ty + 13),
              relative=0, thickness=0)
    agency = META.get(slug, {}).get("agency", "")
    tracked(c, M, img_bottom - 35, ("%s   ·   %s" % (s["state"], agency)).upper(),
            "Helvetica", 7, GRAY, 1.0)
    # record text, manual two-column flow (deterministic; clips at column 2 end)
    gap = 24
    colw = (box_w - gap) / 2
    x_cols = [M, M + colw + gap]
    text_top = img_bottom - 50
    text_bottom = 58
    VS, LS = 10.3, 6.8           # value leading, label size
    items = []                  # ('label'|'val', text)
    for label, fld in FIELDS:
        val = str(s.get(fld, "")).strip()
        if not val:
            continue
        items.append(("label", label.upper()))
        for ln in simpleSplit(val, UNI, 8.0, colw - 8):
            items.append(("val", ln))
    col, y = 0, text_top
    i = 0
    while i < len(items):
        kind, txt = items[i]
        need = (VS + 16) if kind == "label" else VS   # keep label with its first line
        if y - need < text_bottom:
            if col == 0:
                col, y = 1, text_top
                continue
            break
        if kind == "label":
            y -= 7
            tracked(c, x_cols[col], y, txt, "Helvetica-Bold", LS, GRAY, 0.6)
            y -= (LS + 4)
        else:
            t = c.beginText(x_cols[col], y); t.setFont(UNI, 8.0)
            t.setFillColorRGB(*INK); t.setCharSpace(0); t.textOut(txt); c.drawText(t)
            y -= VS
        i += 1
    if i < len(items):                  # record clipped: linked continuation cue
        more = "… more"
        my = max(y, 49)
        tracked(c, x_cols[1], my, more, "Helvetica-Oblique", 8, GRAY, 0)
        c.linkURL(url, (x_cols[1], my - 2, x_cols[1] + twidth(c, more, "Helvetica-Oblique", 8),
                  my + 8), relative=0, thickness=0)
    footer(c)
    c.showPage()


def colophon_page(c):
    c.setFillColorRGB(1, 1, 1); c.rect(0, 0, PW, PH, fill=1, stroke=0)
    LM = 64

    def block(heading, body, top):
        tracked(c, LM, top, heading.upper(), "Helvetica-Bold", 16, INK, 1.4)
        c.setStrokeColorRGB(*INK); c.setLineWidth(1.0)
        c.line(LM, top - 14, PW - LM, top - 14)
        t = c.beginText(LM, top - 44); t.setFont(UNI, 10.5); t.setLeading(16.5)
        t.setFillColorRGB(*INK); t.setCharSpace(0)
        lines = simpleSplit(body, UNI, 10.5, PW - 2 * LM)
        for ln in lines:
            t.textLine(ln)
        c.drawText(t)
        return top - 44 - 16.5 * len(lines)

    proj = (PROJECT + "  The plates collected here are selected from an archive of "
            "%d documented sites across the United States." % TOTAL_SITES)
    after = block("The Project", proj, PH - 150)
    block("Sources", SOURCES, after - 56)
    footer(c)
    c.showPage()


def build(order, out, closing=False):
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle("Public Lands Institute Portfolio"); c.setAuthor("Jordan Tate")
    n = len(order)
    title_page(c)
    for slug in order:
        site_page(c, slug)
    if closing:
        colophon_page(c)
    c.save()
    pages = 1 + n + (1 if closing else 0)
    print("wrote", os.path.basename(out), "(%d pages)" % pages)


if __name__ == "__main__":
    build(TEN, os.path.join(ROOT, "PLI-Portfolio-10pg.pdf"))
    build(FIFTEEN, os.path.join(ROOT, "PLI-Portfolio-15pg.pdf"))
    build(TWENTY, os.path.join(ROOT, "PLI-Portfolio-20pg.pdf"), closing=True)
