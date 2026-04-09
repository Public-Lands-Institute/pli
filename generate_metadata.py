#!/usr/bin/env python3
"""
Public Lands Institute — archive metadata generator.
Produces archive-metadata/archive.csv and archive-metadata/schema.json
from sites.json, sites_meta.json, and inaturalist_cache.json.

Run from the PLI project root:
    python3 generate_metadata.py
"""

import csv
import json
import os
import re

STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming',
}

CONSERVATION_KEYWORDS = [
    'National Natural Landmark',
    'National Historic Landmark',
    'National Park',
    'National Wildlife Refuge',
    'National River',
    'Superfund',
    'State Nature Preserve',
    'State Historic Site',
    'World Heritage',
]

def derive_tags(site, meta):
    tags = []

    # State full name
    state_code = site.get('state', '')
    if state_code in STATE_NAMES:
        tags.append(STATE_NAMES[state_code])

    # Agency type
    agency_type = meta.get('agency_type', '')
    if agency_type:
        tags.append(agency_type)

    # Conservation status keywords (case-insensitive dedup)
    conservation = site.get('conservation_status', '')
    tags_lower = [t.lower() for t in tags]
    for keyword in CONSERVATION_KEYWORDS:
        if keyword.lower() in conservation.lower():
            if keyword.lower() not in tags_lower:
                tags.append(keyword)
                tags_lower.append(keyword.lower())

    return tags


def format_tags(tags):
    """Format tags as a Zotero-compatible array string: [Tag1, Tag2]"""
    cleaned = [t.strip() for t in tags if t.strip()]
    return '[' + ', '.join(cleaned) + ']'


def derive_taxa(slug, inat_cache):
    """Get observed taxa groups from iNat cache."""
    # Try with common radius suffixes
    for radius in [5, 8, 10]:
        key = f'{slug}:{radius}'
        if key in inat_cache:
            counts = inat_cache[key].get('taxa_counts', [])
            if counts:
                return [t['label'] for t in counts]
    return []


def format_taxa(taxa_list):
    """Format taxa as array string: [Plants, Birds]"""
    if not taxa_list:
        return ''
    return '[' + ', '.join(taxa_list) + ']'


def main():
    with open('sites.json') as f:
        sites = json.load(f)
    with open('sites_meta.json') as f:
        meta = json.load(f)
    with open('inaturalist_cache.json') as f:
        inat_cache = json.load(f)

    os.makedirs('archive-metadata', exist_ok=True)

    fieldnames = [
        'Location',
        'GPS',
        'Native_Lands',
        'Tags',
        'Geological_Age',
        'Ecology',
        'Hydrology',
        'Taxa',
        'Acreage',
    ]

    rows = []
    for site in sites:
        slug = site.get('slug', '')
        site_meta = meta.get(slug, {})

        lat = site.get('lat', '')
        lng = site.get('lng', '')
        gps = f'{lat}, {lng}' if lat and lng else site.get('gps', '')

        tags = derive_tags(site, site_meta)
        taxa = derive_taxa(slug, inat_cache)

        rows.append({
            'Location': site.get('name', ''),
            'GPS': gps,
            'Native_Lands': site.get('native_lands', ''),
            'Tags': format_tags(tags),
            'Geological_Age': site.get('geological_age', ''),
            'Ecology': site.get('ecology', ''),
            'Hydrology': site.get('hydrology', ''),
            'Taxa': format_taxa(taxa),
            'Acreage': site.get('acreage', ''),
        })

    csv_path = 'archive-metadata/archive.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {csv_path} ({len(rows)} rows)')

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Public Lands Institute Archive Metadata",
        "description": "Field definitions for archive.csv. CC0 Public Domain.",
        "type": "object",
        "properties": {
            "Location": {
                "type": "string",
                "description": "Official name of the protected area."
            },
            "GPS": {
                "type": "string",
                "description": "Decimal degree coordinates of the park center or main entrance. Format: lat, lng."
            },
            "Native_Lands": {
                "type": "string",
                "description": "Indigenous nations with historical presence, including territorial context, treaties, and displacement history."
            },
            "Tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keyword tags including state name, agency type, and conservation designations. Stored as array string [Tag1, Tag2] for Zotero compatibility."
            },
            "Geological_Age": {
                "type": "string",
                "description": "Age in millions of years and rock type. Format: ~450 Mya Ordovician limestone."
            },
            "Ecology": {
                "type": "string",
                "description": "Dominant plant communities, notable species, and habitat type."
            },
            "Hydrology": {
                "type": "string",
                "description": "Watershed, named waterways, and notable hydrological features."
            },
            "Taxa": {
                "type": "array",
                "items": {"type": "string"},
                "description": "iNaturalist observed taxa groups (Plants, Birds, Insects, etc.). Stored as array string [Taxa1, Taxa2]."
            },
            "Acreage": {
                "type": "string",
                "description": "Total acreage of the protected area per managing agency."
            }
        }
    }

    schema_path = 'archive-metadata/schema.json'
    with open(schema_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2)
    print(f'Wrote {schema_path}')


if __name__ == '__main__':
    main()
