---
name: portfolio-builder
description: Build an application portfolio from the Public Lands Institute photographs, for a grant, fellowship, residency or exhibition (W. Eugene Smith, Guggenheim, Creative Capital, Loghaven and similar). Use when Jordan asks to choose sites or images for an application, write captions, sequence a set, or export upload files.
---

# Portfolio builder

The method used for the W. Eugene Smith Grant 2026 (Prior Use, 40 images). Claude recommends sites and drafts captions; Jordan chooses the frames; Claude captions the exact frames chosen, marks a recommended set, and exports the files.

## 1. Read before choosing anything

- The application text Jordan supplies: description, proposal, any caption examples. The description's argument sets the sequence.
- The application's image rules: maximum count, format, color space, dpi, minimum size, how past work must be marked.
- sites.json, especially displacement_tenure and shadow_history. These records are the fact source unless an outside source is named. The GitHub copy can lag Jordan's local copy; if sites or photos seem missing, ask for the current sites.json or the image files.
- data/photos.json and thumbs/<slug>/lg_*.jpg (1200 px previews) to see what exists.

## 2. Recommend sites first

- Sections follow the argument (for Prior Use: the project, other military land, the first taking, the second taking, contamination, then close on the project).
- Survey every site record, not only the ones Jordan names: search shadow_history and displacement_tenure for terms that fit the argument (for Prior Use: Army, ordnance, National Guard, condemnation, eminent domain, uranium, Superfund).
- One line per site on why it is in. Say plainly when a site is weak or off-argument. Keep a short alternates list with draft captions.

## 3. Contact-sheet page for choosing frames

Publish an Artifact page:
- A card per site with the reason, lettered draft captions, notes on frames that change the caption, and every frame as a 1000 px preview published under v/<slug>/. Include frames filed under a sub-site folder (Charon's Garden sits inside Wichita Mountains).
- Click to mark; the red number is the order within the site and picks the caption slot. A larger viewer with arrow keys and P to mark.
- Picks save in the viewer's browser; Copy my picks produces a list to paste back. Sites without repository files get a box for file names, and Jordan can attach those images in chat.

## 4. Captions

- Format: Site, State. Former use or taking; one fact about people. Past work ends with "(Public Lands Institute, past work)"; the project being proposed carries no label.
- Project captions should hit hardest: numbers, dates, who was removed, what is still in the ground.
- Frames from the same site carry different facts, so any of them can be swapped in.
- Every fact comes from the site record or a named source; list outside sources and anything to confirm.
- Match the caption to the frame. Check EXIF GPS when location matters (Badlands North vs South Unit, Nantahala Lake vs Fontana, Spearfish Canyon vs Whitewood Creek). Name what the frame shows when it carries a human trace: inscriptions, dwellings, buildings, signs, smokestacks.
- When Jordan moves a caption to another frame, give the frame that lost it the displaced caption.

## 5. Weigh a recommended set

- Second page with only Jordan's picks: every frame with its caption, the recommended set marked and numbered in upload order, click to swap, a running count against the limit, Copy final list.
- Group each site's frames together. Open with the project; hold one strong project frame for the close.
- Check neighbors: two similar frames side by side (two flat horizons, two lakes) should be separated.
- In the reply, name what to cut first and which bench frames earn a place, with one reason each.

## 6. Finish

- A read-only final page: numbered frames with full captions and Copy all captions.
- Export with export_portfolio.py in this folder. Fill SELECTION from the final list, set LONG_EDGE and OUT, and give Jordan the command to run on Jordan's Mac: it reads the TIFF masters in img/full/<slug>/, which exist only on that machine, and writes numbered sRGB JPGs plus captions.txt to the Desktop. It never upscales. Add SOURCE_SLUG entries for frames filed under another folder.
- Keep application files out of the repository and off the website. Scratch work belongs in the session scratchpad.

## Writing rules

No em or en dashes. No short choppy sentences, no "X, not Y" for rhythm, no poetic flourish or jargon. Be direct about weak pictures and weak sites.
