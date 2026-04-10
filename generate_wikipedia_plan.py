#!/usr/bin/env python3
"""
generate_wikipedia_plan.py

For each site in sites.json:
  1. Fetches all PLI Commons files matching that site name.
  2. Looks up the Wikipedia article (primary + secondary targets from geo/hydro fields).
  3. Counts existing images in each article.
  4. Writes PLI-Wikipedia-Image-Plan.md sorted by priority (fewest images first).

Run: python3 generate_wikipedia_plan.py
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SITES_JSON   = PROJECT_ROOT / "sites.json"
OUTPUT_FILE  = PROJECT_ROOT / "PLI-Wikipedia-Image-Plan.md"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WP_API      = "https://en.wikipedia.org/w/api.php"
USER_AGENT  = "PLIWikipediaPlanBot/1.0 (publiclandsinstitute.net)"

# Thumbnail images, icons, and navigation elements to exclude from image counts
IMAGE_NOISE = [
    "icon", "logo", "flag", "button", "arrow", "stub", "commons",
    "edit", "wikimedia", "question", "blank", "location", "map",
    "star", "featured", "sound", "protected", "padlock", "silhouette",
    "pictogram", "symbol", "badge", "seal", "emblem", ".svg",
]

ROMAN = ["I","II","III","IV","V","VI","VII","VIII","IX","X",
         "XI","XII","XIII","XIV","XV","XVI","XVII","XVIII","XIX","XX"]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def api_get(base_url, params, retries=3, delay=1.5):
    """GET a MediaWiki API endpoint, return parsed JSON."""
    url = base_url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                print(f"  WARNING: API call failed after {retries} attempts: {e}", file=sys.stderr)
                return {}


# ---------------------------------------------------------------------------
# Commons helpers
# ---------------------------------------------------------------------------

def fetch_all_pli_files():
    """
    Return dict mapping site-name-segment (as it appears in the filename)
    to list of file dicts: {title, url, commons_page}.
    Paginates until all files are fetched.
    """
    all_files = []
    params = {
        "action": "query",
        "list": "allimages",
        "aiuser": "Publiclandsinstitute",
        "aisort": "timestamp",
        "ailimit": "500",
        "aiprop": "url|timestamp|size",
        "format": "json",
    }
    while True:
        data = api_get(COMMONS_API, params)
        imgs = data.get("query", {}).get("allimages", [])
        all_files.extend(imgs)
        if "continue" not in data:
            break
        params["aicontinue"] = data["continue"]["aicontinue"]
        time.sleep(0.5)

    # Group by site name segment
    by_site = {}
    pattern = re.compile(r"File:Public Lands Institute - (.+?) - (\d+)\.")
    for f in all_files:
        m = pattern.match(f["title"])
        if not m:
            continue
        seg = m.group(1)
        num = int(m.group(2))
        title = f["title"]
        # Commons page URL uses underscores
        commons_page = "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_")
        entry = {
            "title": title,
            "url": f.get("url", ""),
            "commons_page": commons_page,
            "num": num,
        }
        by_site.setdefault(seg, []).append(entry)

    # Sort each site's files by number
    for seg in by_site:
        by_site[seg].sort(key=lambda x: x["num"])

    return by_site


# ---------------------------------------------------------------------------
# Wikipedia helpers
# ---------------------------------------------------------------------------

def is_content_image(title_lower):
    """Return True if the image title looks like a real content photo (not a UI element)."""
    return not any(noise in title_lower for noise in IMAGE_NOISE)


def get_wp_article(title):
    """
    Fetch a Wikipedia article by exact title.
    Returns (canonical_title, full_url, content_image_count) or None if not found.
    """
    data = api_get(WP_API, {
        "action": "query",
        "titles": title,
        "prop": "images|info",
        "imlimit": "100",
        "inprop": "url|displaytitle",
        "format": "json",
    })
    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        if pid == "-1":
            return None
        canonical = page.get("title", title)
        url = page.get("fullurl", "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")))
        images = page.get("images", [])
        count = sum(1 for i in images if is_content_image(i["title"].lower()))
        return canonical, url, count
    return None


def search_wp(query, limit=3):
    """Search Wikipedia and return list of (title,) results."""
    data = api_get(WP_API, {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(limit),
        "srinfo": "",
        "srprop": "",
        "format": "json",
    })
    return [r["title"] for r in data.get("query", {}).get("search", [])]


def resolve_article(name):
    """
    Try to find a Wikipedia article for `name`.
    First tries exact match, then search with a conservative relevance check.
    Returns (canonical_title, url, image_count) or None.
    """
    result = get_wp_article(name)
    if result:
        return result
    # Try search -- only accept if the result title shares meaningful words with query
    hits = search_wp(name, limit=3)
    name_words = set(w.lower() for w in name.split() if len(w) > 4)
    for hit in hits:
        hit_words = set(w.lower() for w in hit.split() if len(w) > 4)
        # Require at least 2 overlapping significant words, or the hit starts with the query
        overlap = name_words & hit_words
        if len(overlap) >= 2 or hit.lower().startswith(name.lower()[:15]):
            result = get_wp_article(hit)
            if result:
                return result
    return None


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

FORMATION_RE = re.compile(
    r"([A-Z][a-z]+(?: [A-Z][a-z]+)* "
    r"(?:Formation|Member|Group|Series|Shale|Limestone|Sandstone|Granite|Rhyolite|Dolomite|Conglomerate))"
)
RIVER_RE = re.compile(
    r"([A-Z][a-zA-Z\'-]+(?: [A-Z][a-zA-Z\'-]+){0,4} "
    r"(?:River|Creek|Fork|Run|Branch|Lake|Spring|Reservoir|Gorge|Canyon|Falls))"
)


def extract_secondary_targets(site):
    """
    Extract formation names and river/feature names from geological_age and hydrology.
    Returns list of candidate Wikipedia search strings, deduplicated, capped at 6.
    """
    geo = site.get("geological_age", "")
    hydro = site.get("hydrology", "")

    candidates = []

    for m in FORMATION_RE.finditer(geo):
        candidates.append(m.group(1))

    for m in RIVER_RE.finditer(hydro):
        term = m.group(1)
        # Skip very generic terms
        if term not in ("Ohio River", "Mississippi River"):
            candidates.append(term)

    # Also try the site's epoch as a search term if it contains a named unit
    epoch = site.get("epoch", "")
    epoch_names = re.findall(r"([A-Z][a-z]+ [A-Z][a-z]+)", epoch)
    for e in epoch_names[:1]:
        candidates.append(e)

    # Deduplicate preserving order, cap at 6
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
        if len(result) >= 6:
            break
    return result


# ---------------------------------------------------------------------------
# Wikitext suggestion
# ---------------------------------------------------------------------------

def make_wikitext(file_title, site_name, state):
    """Build a suggested wikitext image insertion line."""
    # file_title already includes the "File:" prefix from the API response
    bare = file_title.removeprefix("File:")
    caption = f"{site_name}, {state}. CC0 photograph by the Public Lands Institute."
    return f"[[File:{bare}|thumb|{caption}]]"


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

def priority_label(image_count):
    if image_count <= 2:
        return "high"
    if image_count <= 5:
        return "medium"
    return "low"


def priority_sort_key(entry):
    order = {"high": 0, "medium": 1, "low": 2, "no article": 3}
    primary = entry.get("primary")
    if primary is None:
        return (3, 999)
    return (order.get(entry["priority"], 4), primary["image_count"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading sites.json...")
    with open(SITES_JSON) as f:
        sites = json.load(f)

    print("Fetching all PLI Commons files...")
    commons_by_site = fetch_all_pli_files()
    print(f"  Found files for {len(commons_by_site)} site name segments on Commons.")

    # Build lookup: site.name -> Commons segment
    # Commons filenames use the site's official name (may differ slightly from slug-based name)
    # Match by normalizing both sides
    def normalize(s):
        return re.sub(r"[^a-z0-9]", "", s.lower())

    commons_norm = {normalize(k): k for k in commons_by_site}

    results = []

    for i, site in enumerate(sites):
        name = site["name"]
        state = site["state"]
        slug = site["slug"]
        print(f"\n[{i+1}/{len(sites)}] {name}")

        # --- Match Commons files ---
        seg_key = commons_norm.get(normalize(name))
        files = commons_by_site.get(seg_key, []) if seg_key else []
        if not files:
            # Try partial match
            for norm_key, orig_key in commons_norm.items():
                if normalize(name)[:12] in norm_key or norm_key[:12] in normalize(name):
                    files = commons_by_site[orig_key]
                    break
        print(f"  Commons files: {len(files)}")

        # --- Primary Wikipedia article ---
        print(f"  Querying Wikipedia: {name}")
        primary = None
        wp_result = resolve_article(name)
        if wp_result:
            canon, url, img_count = wp_result
            primary = {"title": canon, "url": url, "image_count": img_count}
            print(f"    -> {canon} ({img_count} images)")
        else:
            print(f"    -> no article found")

        # --- Secondary targets ---
        secondary_candidates = extract_secondary_targets(site)
        secondaries = []
        for term in secondary_candidates:
            time.sleep(0.3)
            wp_result = resolve_article(term)
            if wp_result:
                canon, url, img_count = wp_result
                # Skip if it's the same article as primary
                if primary and canon == primary["title"]:
                    continue
                # Skip duplicates
                if any(s["title"] == canon for s in secondaries):
                    continue
                secondaries.append({"term": term, "title": canon, "url": url, "image_count": img_count})
                print(f"    secondary: {canon} ({img_count} images)")
            time.sleep(0.4)

        # --- Priority (based on primary article) ---
        if primary:
            priority = priority_label(primary["image_count"])
        elif secondaries:
            best_secondary_count = min(s["image_count"] for s in secondaries)
            priority = priority_label(best_secondary_count)
        else:
            priority = "no article"

        # --- Best candidate image (Roman numeral I, or lowest numbered available) ---
        best_file = files[0] if files else None

        results.append({
            "site": site,
            "files": files,
            "primary": primary,
            "secondaries": secondaries,
            "priority": priority,
            "best_file": best_file,
        })

        time.sleep(0.5)

    # Sort: high > medium > low > no article, then fewest images first
    results.sort(key=priority_sort_key)

    # --- Write Markdown report ---
    print(f"\nWriting {OUTPUT_FILE.name}...")
    lines = []

    lines.append("# PLI Wikipedia Image Plan")
    lines.append(f"\nGenerated: {date.today().strftime('%B %d, %Y')}")
    lines.append(f"Sites evaluated: {len(results)}")
    lines.append(f"Sites with PLI Commons files: {sum(1 for r in results if r['files'])}")
    lines.append("\nPriority: **high** = 0-2 images in article | **medium** = 3-5 | **low** = 6+")
    lines.append("\n---\n")

    current_priority = None

    for r in results:
        site     = r["site"]
        files    = r["files"]
        primary  = r["primary"]
        secs     = r["secondaries"]
        priority = r["priority"]
        best     = r["best_file"]

        # Priority section header
        if priority != current_priority:
            current_priority = priority
            label = priority.upper()
            lines.append(f"\n## Priority: {label}\n")

        lines.append(f"### {site['name']}")
        lines.append(f"\n**State:** {site['state']}  ")
        lines.append(f"**Priority:** {priority}  ")
        if files:
            lines.append(f"**PLI Commons files available:** {len(files)}\n")
        else:
            lines.append("**PLI Commons files available:** none uploaded yet\n")

        # Primary Wikipedia target
        lines.append("#### Primary Wikipedia Target\n")
        if primary:
            lines.append(f"- **Article:** [{primary['title']}]({primary['url']})")
            lines.append(f"- **Current image count:** {primary['image_count']}")
        else:
            lines.append("- No Wikipedia article found for this site name.")
            search_url = "https://en.wikipedia.org/wiki/Special:Search?search=" + urllib.parse.quote(site["name"])
            lines.append(f"- Search: [{site['name']} on Wikipedia]({search_url})")

        lines.append("")

        # Secondary targets
        if secs:
            lines.append("#### Secondary Wikipedia Targets\n")
            for s in secs:
                sec_priority = priority_label(s["image_count"])
                lines.append(f"- [{s['title']}]({s['url']}) -- {s['image_count']} images -- priority: {sec_priority}")
                lines.append(f"  *(matched from: \"{s['term']}\")*")
            lines.append("")

        # Available Commons files
        if files:
            lines.append("#### Available PLI Commons Files\n")
            for idx, f in enumerate(files):
                roman = ROMAN[idx] if idx < len(ROMAN) else str(idx + 1)
                lines.append(f"- **{roman}.** [{f['title']}]({f['commons_page']})")
            lines.append("")

            # Suggested wikitext
            if best:
                lines.append("#### Suggested Wikitext Insertion\n")
                wikitext = make_wikitext(best["title"], site["name"], site["state"])
                lines.append("```")
                lines.append(wikitext)
                lines.append("```")
                lines.append("")
                bare_title = best["title"].removeprefix("File:")
                lines.append(
                    f"Place in the article body or infobox. "
                    f"`{bare_title}` is the first uploaded image for this site (Roman numeral I). "
                    f"Substitute a higher-numbered file if a more representative scene exists."
                )
                lines.append("")
        else:
            lines.append("*No PLI Commons files uploaded for this site yet.*\n")

        lines.append("---\n")

    output = "\n".join(lines)
    with open(OUTPUT_FILE, "w") as f:
        f.write(output)

    print(f"Done. Report written to {OUTPUT_FILE.name}")
    print(f"\nSummary by priority:")
    for p in ("high", "medium", "low", "no article"):
        count = sum(1 for r in results if r["priority"] == p)
        print(f"  {p}: {count} sites")


if __name__ == "__main__":
    main()
