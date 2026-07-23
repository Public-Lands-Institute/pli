#!/usr/bin/env python3
"""
Public Lands Institute — social card generator.
Run from the repo root:
    python3 tools/make_cards.py

Writes 1200x630 JPEG cards into img/cards/:
  <slug>.jpg   each site's first photograph (data/photos.json order),
               letterboxed on #161616, with the site name and
               "PUBLIC LANDS INSTITUTE · CC0" in Inter, uppercase, letterspaced
  site.jpg     one generic typographic card for the section pages
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

CARD_W, CARD_H = 1200, 630
BG = (22, 22, 22)          # #161616
FG = (232, 232, 232)       # #e8e8e8
MUTED = (140, 140, 140)    # #8c8c8c
TEXT_BAND = 150            # bottom band reserved for text
FONT_LIGHT = 'fonts/Inter-Light.ttf'


def tracked_width(font, text, tracking):
    return sum(font.getlength(ch) + tracking for ch in text) - (tracking if text else 0)


def draw_tracked(draw, xy, text, font, tracking, fill):
    """Draw text with letterspacing (tracking in px between characters)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + tracking


def draw_centered(draw, y, text, font, tracking, fill):
    w = tracked_width(font, text, tracking)
    draw_tracked(draw, ((CARD_W - w) / 2, y), text, font, tracking, fill)


def card_base():
    return Image.new('RGB', (CARD_W, CARD_H), BG)


def letterbox(card, photo_path):
    photo = Image.open(photo_path).convert('RGB')
    box_w, box_h = CARD_W, CARD_H - TEXT_BAND
    scale = min(box_w / photo.width, box_h / photo.height)
    new = photo.resize((round(photo.width * scale), round(photo.height * scale)),
                       Image.LANCZOS)
    card.paste(new, ((box_w - new.width) // 2, (box_h - new.height) // 2))


def site_card(name, photo_path, out_path):
    card = card_base()
    letterbox(card, photo_path)
    draw = ImageDraw.Draw(card)
    # Shrink long names until they fit with a 40 px margin each side
    size, tracking = 30, 4.2
    name_font = ImageFont.truetype(FONT_LIGHT, size)
    while size > 16 and tracked_width(name_font, name.upper(), tracking) > CARD_W - 80:
        size -= 1
        tracking = size * 0.14
        name_font = ImageFont.truetype(FONT_LIGHT, size)
    brand_font = ImageFont.truetype(FONT_LIGHT, 16)
    draw_centered(draw, CARD_H - TEXT_BAND + 38, name.upper(), name_font, tracking, FG)
    draw_centered(draw, CARD_H - TEXT_BAND + 92, 'PUBLIC LANDS INSTITUTE · CC0',
                  brand_font, 2.9, MUTED)
    card.save(out_path, 'JPEG', quality=88)


def generic_card(out_path):
    card = card_base()
    draw = ImageDraw.Draw(card)
    title_font = ImageFont.truetype(FONT_LIGHT, 44)
    sub_font = ImageFont.truetype(FONT_LIGHT, 16)
    draw_centered(draw, 262, 'PUBLIC LANDS INSTITUTE', title_font, 10.6, FG)
    draw_centered(draw, 340, 'AN ONGOING PHOTOGRAPHIC INDEX OF AMERICAN PUBLIC LANDS · CC0',
                  sub_font, 2.9, MUTED)
    card.save(out_path, 'JPEG', quality=88)


def main():
    os.makedirs('img/cards', exist_ok=True)
    with open('sites.json') as f:
        sites = json.load(f)
    with open('data/photos.json') as f:
        photos = json.load(f)
    made = 0
    for site in sites:
        slug = site['slug']
        entries = photos.get(slug, [])
        if not entries:
            print(f'  skipped {slug}: no photographs')
            continue
        cam = os.path.basename(entries[0]['thumb'])
        photo_path = f'img/jpg/{slug}/{cam}'
        site_card(site['name'], photo_path, f'img/cards/{slug}.jpg')
        made += 1
    generic_card('img/cards/site.jpg')
    print(f'img/cards/: {made} site cards + site.jpg')


if __name__ == '__main__':
    main()
