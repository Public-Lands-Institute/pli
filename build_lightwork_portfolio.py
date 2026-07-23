#!/usr/bin/env python3
"""Build Light Work 2027 AiR SlideRoom portfolio JPGs from Tate-Portfolio.pdf.

Cover (p1) and back matter (p22) export as-is. Each site plate crops the
embedded photograph from the top of its page and composites a clean, consistent
caption block beneath it. Output: 1280px wide, 72dpi, JPG q92, < 5MB each.
"""
import os
import fitz
from PIL import Image, ImageDraw, ImageFont

PDF = os.path.expanduser("~/Downloads/Tate-Portfolio.pdf")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lightwork-portfolio")
os.makedirs(OUT, exist_ok=True)

W = 1280            # final width
RENDER_DPI = 300    # rasterization resolution before downscale
SCALE = RENDER_DPI / 72.0

# Caption typography (pixels, in the final 1280px coordinate system)
MARGIN = 48
TOP_PAD = 24
BOT_PAD = 24
NAME_PX = 20
AGENCY_PX = 11
BODY_PX = 11
NAME_LH = 26
AGENCY_LH = 15
SEP_H = 14          # blank separator line
BODY_LH = 16
GAP_NAME_AGENCY = 6
NAME_COLOR = (17, 17, 17)
SUB_COLOR = (68, 68, 68)
RULE_COLOR = (204, 204, 204)
BG = (255, 255, 255)

ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
ARIAL_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
f_name = ImageFont.truetype(ARIAL_BOLD, NAME_PX)
f_agency = ImageFont.truetype(ARIAL, AGENCY_PX)
f_body = ImageFont.truetype(ARIAL, BODY_PX)

# (outfile, page, name, agency, body)  -- en/em dashes normalized to project house style
SITES = [
    ("02-arches.jpg", 2, "Arches National Park", "UT  ·  NATIONAL PARK SERVICE",
     "Unceded Ute (Sheberetch) homeland. Dispossession through Mormon colonization and disease; no ratified treaty ever extinguished Ute title. Proclaimed national monument 1929, established as national park 1971."),
    ("03-badlands.jpg", 3, "Badlands National Park", "SD  ·  NATIONAL PARK SERVICE",
     "U.S. Army Air Force seized 341,726 acres of Pine Ridge Reservation by eminent domain in 1942 for bombing and gunnery range; 125 Oglala Lakota families forcibly relocated. Unexploded ordnance remains across the former range; cleanup incomplete. Returned to NPS management 1968."),
    ("04-black-hills.jpg", 5, "Black Hills National Forest", "SD  ·  USDA FOREST SERVICE",
     "Paha Sapa, heart of everything that is, to the Lakota. Congress seized the Black Hills in 1877 in violation of the Fort Laramie Treaty; U.S. Supreme Court ruled the taking unconstitutional in 1980. Homestake Gold Mine discharged cyanide, zinc, and copper into Gold Run Creek for decades; Whitewood Creek listed on the Superfund NPL 1983."),
    ("05-bryce.jpg", 6, "Bryce Canyon National Park", "UT  ·  NATIONAL PARK SERVICE",
     "Unceded Southern Paiute homeland; no ratified treaty ever extinguished Paiute title. Mormon colonization of the 1860s-1870s displaced the Paiute from the surrounding plateaus. Federal termination policy of the 1950s further devastated Paiute communities."),
    ("06-elephant-rocks.jpg", 8, "Elephant Rocks State Park", "MO  ·  MISSOURI STATE PARKS",
     "Osage Nation (Wazhazhe) territory, ceded under duress via Treaty of 1808. Iron County granite quarried commercially from 1869 as a company town of ~700 residents; silica dust exposure produced occupational silicosis among quarry workers. Two abandoned quarry pits remain within the park without documented remediation."),
    ("07-fernald.jpg", 9, "Fernald Preserve", "OH  ·  U.S. DEPARTMENT OF ENERGY, OFFICE OF LEGACY MANAGEMENT",
     "Uranium feed materials production center for the U.S. nuclear weapons program, 1951-1989. DOE concealed groundwater contamination from residents for four years. K-65 silos stored radium-226-contaminated waste; NIOSH documented elevated lung cancer risk among workers. Remediation completed 2006; opened as wildlife refuge 2007."),
    ("08-ford-marsh.jpg", 10, "Ford Marsh Unit, Detroit River International Wildlife Refuge", "MI  ·  U.S. FISH AND WILDLIFE SERVICE",
     "Potawatomi and Wyandot territory ceded via Treaty of Detroit (1807); Potawatomi removed via Trail of Death, 1838-1840. Site operated successively as a steel mill, WWII munitions facility, and automotive plant before Ford donated 242 acres to USFWS in 2010."),
    ("09-hopewell.jpg", 12, "Hopewell Culture National Historical Park", "OH  ·  NATIONAL PARK SERVICE",
     "U.S. Army purchased the Mound City tract in 1917 and built Camp Sherman, a 9,700-acre WWI training cantonment, directly over and around the earthworks; 120,000 soldiers passed through before decommissioning in 1921. Designated national monument 1923; inscribed UNESCO World Heritage Site 2023."),
    ("10-johnsons.jpg", 13, "Johnson's Shut-Ins State Park", "MO  ·  MISSOURI STATE PARKS",
     "Osage Nation (Wazhazhe) territory, ceded under duress via Treaty of 1808. Assembled and donated to the state by heir to a regional lead-mining fortune. On December 14, 2005, the Taum Sauk upper reservoir failed, releasing 1.4 billion gallons of water that destroyed the lower park. AmerenUE pled no contest to Clean Water Act violation; $102.3 million settlement funded restoration completed 2010."),
    ("11-krejci.jpg", 14, "Krejci Dump, Cuyahoga Valley National Park", "OH  ·  NATIONAL PARK SERVICE",
     "Unregulated hazardous waste disposal site operated 1948-1980, accepting industrial waste from Ford, GM, Chrysler, 3M, and Chevron; PCBs, dioxins, arsenic, and benzene buried in unlined trenches. NPS acquired the property in 1985 not knowing it was contaminated. CERCLA remediation certified complete December 2020; 200-acre restored reserve opened to public access the same month."),
    ("12-maquoketa.jpg", 15, "Maquoketa Caves State Park", "IA  ·  IOWA DNR",
     "Eastern Iowa strip ceded under the Black Hawk Purchase (1832), extracted as punitive condition of Black Hawk's defeat, with Black Hawk held prisoner during signing. Woodland-period pottery, stone tools, and projectile points recovered from the caves are held in collections; no NAGPRA compliance documentation is available in public records."),
    ("13-mounds.jpg", 16, "Mounds State Park", "IN  ·  INDIANA DNR",
     "Adena and Hopewell earthwork complex; Delaware (Lenape) and Miami homeland, ceded via Treaty of 1818. Union Traction Company operated a 40-acre amusement park directly on the earthwork complex from 1897 to 1929, with the roller coaster, skating rink, and merry-go-round built among the mounds."),
    ("14-pipestone.jpg", 18, "Pipestone National Monument", "MN  ·  NATIONAL PARK SERVICE",
     "Sacred catlinite quarry used by Plains nations for more than 3,000 years. The Pipestone Indian Training School, a federal BIA off-reservation boarding school, operated on monument grounds from 1893 to ~1953; a campus cemetery holds graves of children who died there. Today 23 federally affiliated tribes retain free quarry permit rights."),
    ("15-wichita.jpg", 20, "Wichita Mountains National Wildlife Refuge", "OK  ·  U.S. FISH AND WILDLIFE SERVICE",
     "Carved directly from the Kiowa-Comanche-Apache Reservation on July 4, 1901, the same day McKinley opened the KCA land lottery. CCC labor constructed 46 concrete dams, 50 miles of improved roads, and a hydroelectric system in the 1930s. The Quanah Artillery Range (15,850 acres) has operated along the refuge's southern boundary since 1957."),
    ("16-yellowstone.jpg", 21, "Yellowstone National Park", "WY  ·  NATIONAL PARK SERVICE",
     "Template for what scholars call fortress conservation: protected wilderness created through removal of its Indigenous inhabitants. The Tukudika (Mountain Shoshone) were the only documented year-round residents; forcibly removed to reservations by ~1880. Ward v. Race Horse (1896) abrogated tribal hunting rights; not overturned until Herrera v. Wyoming (2019)."),
]

doc = fitz.open(PDF)


def render_page_full(pno):
    pix = doc[pno - 1].get_pixmap(matrix=fitz.Matrix(SCALE, SCALE))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    h = round(W * img.height / img.width)
    return img.resize((W, h), Image.LANCZOS)


def render_photo(pno):
    pg = doc[pno - 1]
    info = pg.get_image_info()
    bbox = info[0]["bbox"] if info else (47, 44, 565, 432)
    rect = fitz.Rect(*bbox)
    pix = pg.get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), clip=rect)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    h = round(W * img.height / img.width)
    return img.resize((W, h), Image.LANCZOS)


def wrap(text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = word if not cur else cur + " " + word
        if font.getlength(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_tracked(draw, xy, text, font, fill, track=0.7):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + track


def save_jpg(img, name):
    path = os.path.join(OUT, name)
    img.save(path, "JPEG", quality=92, dpi=(72, 72))
    return path, os.path.getsize(path)


def build_plate(outfile, pno, name, agency, body):
    photo = render_photo(pno)
    ph = photo.height
    text_w = W - 2 * MARGIN
    body_lines = wrap(body, f_body, text_w)
    cap_h = (TOP_PAD + NAME_LH + GAP_NAME_AGENCY + AGENCY_LH + SEP_H
             + len(body_lines) * BODY_LH + BOT_PAD)
    total_h = ph + 1 + cap_h
    canvas = Image.new("RGB", (W, total_h), BG)
    canvas.paste(photo, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.line([(0, ph), (W, ph)], fill=RULE_COLOR, width=1)
    y = ph + 1 + TOP_PAD
    d.text((MARGIN, y), name, font=f_name, fill=NAME_COLOR)
    y += NAME_LH + GAP_NAME_AGENCY
    draw_tracked(d, (MARGIN, y), agency, f_agency, SUB_COLOR)
    y += AGENCY_LH + SEP_H
    for ln in body_lines:
        d.text((MARGIN, y), ln, font=f_body, fill=SUB_COLOR)
        y += BODY_LH
    path, size = save_jpg(canvas, outfile)
    return path, size, total_h, len(body_lines)


def main():
    print(f"Output: {OUT}")
    # Cover
    p, s = save_jpg(render_page_full(1), "01-cover.jpg")
    print(f"  01-cover.jpg            {os.path.basename(p):24} {s/1e6:5.2f} MB")
    # Site plates
    for outfile, pno, name, agency, body in SITES:
        path, size, h, nl = build_plate(outfile, pno, name, agency, body)
        flag = "  <-- body >3 lines" if nl > 3 else ""
        print(f"  {outfile:24} p{pno:<2} {W}x{h:<4} {size/1e6:5.2f} MB  body={nl}ln{flag}")
    # Back matter
    p, s = save_jpg(render_page_full(22), "17-back.jpg")
    print(f"  17-back.jpg             {os.path.basename(p):24} {s/1e6:5.2f} MB")
    # Verify sizes
    over = [f for f in os.listdir(OUT) if f.endswith('.jpg')
            and os.path.getsize(os.path.join(OUT, f)) > 5 * 1024 * 1024]
    print("ALL UNDER 5MB" if not over else f"OVER 5MB: {over}")
    print("file count:", len([f for f in os.listdir(OUT) if f.endswith('.jpg')]))


if __name__ == "__main__":
    main()
