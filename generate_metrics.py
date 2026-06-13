#!/usr/bin/env python3
"""
generate_metrics.py

Generates PLI-Project-Metrics.txt in the project root.
Reads sites.json and sites_meta.json, scans img/jpg/ for image counts,
and queries the Wikimedia Commons API for upload totals.

Run manually or triggered automatically after deploy.
"""

import json
import os
import re
import urllib.request
import urllib.parse
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SITES_JSON   = PROJECT_ROOT / "sites.json"
META_JSON    = PROJECT_ROOT / "sites_meta.json"
IMG_DIR      = PROJECT_ROOT / "img" / "jpg"
OUTPUT_FILE  = PROJECT_ROOT / "PLI-Project-Metrics.txt"

COMMONS_API  = "https://commons.wikimedia.org/w/api.php"
COMMONS_USER = "Pli-tate"


def count_images():
    """Count all .jpg files under img/jpg/ across all site folders."""
    if not IMG_DIR.exists():
        return 0
    return sum(1 for f in IMG_DIR.rglob("*.jpg"))


def sum_acreage(sites):
    """
    Sum the acreage field across all sites.
    Extracts the first numeric value (with optional comma thousands separators)
    from the field; ignores parenthetical notes or secondary figures.
    Returns (total_int, skipped_count).
    """
    total = 0
    skipped = 0
    for site in sites:
        raw = site.get("acreage", "").strip()
        # Match the first number that may include comma-separated thousands
        match = re.search(r"[\d,]+", raw)
        if match:
            try:
                total += float(match.group().replace(",", ""))
            except ValueError:
                skipped += 1
        else:
            skipped += 1
    return int(round(total)), skipped


def query_commons_uploads():
    """
    Query Commons API for total upload count by COMMONS_USER.
    Handles API continuation to get the full count.
    Returns integer count, or None on failure.
    """
    count = 0
    params = {
        "action": "query",
        "list": "allimages",
        "aiuser": COMMONS_USER,
        "aisort": "timestamp",   # required by the API whenever aiuser is set
        "ailimit": "max",   # 500 per page
        "aiprop": "title",
        "format": "json",
    }

    try:
        while True:
            url = COMMONS_API + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "PLIMetricsBot/1.0 (publiclandsinstitute.net)"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())

            images = data.get("query", {}).get("allimages", [])
            count += len(images)

            # Check for continuation
            if "continue" in data:
                params["aicontinue"] = data["continue"]["aicontinue"]
            else:
                break

        return count

    except Exception as e:
        return None


def main():
    # Load sites.json
    with open(SITES_JSON) as f:
        sites = json.load(f)

    # Load sites_meta.json
    with open(META_JSON) as f:
        meta = json.load(f)

    # Core counts
    total_sites  = len(sites)
    total_images = count_images()

    # States
    states = sorted(set(
        s["state"].strip().upper()
        for s in sites
        if s.get("state", "").strip()
    ))
    total_states = len(states)

    # Acreage
    total_acreage, acreage_skipped = sum_acreage(sites)
    acreage_note = ""
    if acreage_skipped:
        acreage_note = f" ({acreage_skipped} site(s) with no parseable acreage excluded)"

    # Agencies (from sites_meta.json)
    agencies = sorted(set(
        v["agency"].strip()
        for v in meta.values()
        if v.get("agency", "").strip()
    ))
    total_agencies = len(agencies)

    # Wikimedia Commons uploads
    commons_count = query_commons_uploads()
    if commons_count is None:
        commons_uploads_line = "Total Wikimedia Commons uploads: API unavailable -- check manually"
    else:
        commons_uploads_line = f"Total Wikimedia Commons uploads: {commons_count}"

    # Build output
    lines = [
        f"Date generated: {date.today().strftime('%B %d, %Y')}",
        f"Total sites: {total_sites}",
        f"Total images: {total_images}",
        f"States represented: {total_states}",
        f"State list: {', '.join(states)}",
        f"Total acreage represented: {total_acreage:,}{acreage_note}",
        f"Managing agencies represented: {total_agencies}",
        commons_uploads_line,
        "Total Wikimedia Commons file views: check manually",
    ]

    output = "\n".join(lines) + "\n"

    with open(OUTPUT_FILE, "w") as f:
        f.write(output)

    print(f"Metrics written to {OUTPUT_FILE.name}")
    print(output.rstrip())


if __name__ == "__main__":
    main()
