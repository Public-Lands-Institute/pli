#!/usr/bin/env python3
"""
Public Lands Institute: pull Suggest a Site submissions and merge them.

    python3 tools/pull_suggestions.py              # fetch from DreamHost, merge
    python3 tools/pull_suggestions.py --file X     # merge a local .jsonl instead
    python3 tools/pull_suggestions.py --dry-run    # show what would change

suggest.php appends one JSON line per submission to
<parent of DREAMHOST_REMOTE_PATH>/pli-inbox/suggestions.jsonl, outside the web
root. This script copies new lines into submissions/inbox.jsonl (gitignored:
it holds submitters' messages and emails), then merges each new submission
into submissions/suggestions.json:

  - a site already in suggestions.json gets times_suggested + 1
  - anything else becomes a new entry with status "received" and public false,
    so nothing reaches the public page until it is researched and approved

It also writes submissions/suggestions.csv for a quick look in a spreadsheet.
submissions/ is excluded from deploys, so none of this is published; build.py
reads suggestions.json and publishes only public entries' public fields.
"""

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SUGGESTIONS = 'submissions/suggestions.json'
INBOX = 'submissions/inbox.jsonl'
CSV_OUT = 'submissions/suggestions.csv'
STATUSES = ['received', 'researching', 'pending', 'planned', 'documented', 'declined']


def load_env():
    env = {}
    with open('.env') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def fetch_remote():
    env = load_env()
    remote_dir = os.path.dirname(env['DREAMHOST_REMOTE_PATH'].rstrip('/'))
    path = f'{remote_dir}/pli-inbox/suggestions.jsonl'
    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'PubkeyAuthentication=no',
           f'{env["DREAMHOST_USER"]}@{env["DREAMHOST_HOST"]}',
           f'cat {path} 2>/dev/null || true']
    if shutil.which('sshpass'):
        cmd = ['sshpass', '-e'] + cmd
        run_env = {**os.environ, 'SSHPASS': env['DREAMHOST_PASS']}
    else:
        # No sshpass: ssh asks for the DreamHost password in the terminal
        print('sshpass not installed; enter the DreamHost password when asked.')
        run_env = os.environ
    out = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True, env=run_env)
    return out.stdout


def slugify(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


STATE_WORDS = re.compile(
    r'\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|'
    r'florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|'
    r'maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|'
    r'nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|'
    r'north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|'
    r'south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|'
    r'wisconsin|wyoming)\b', re.I)


def match_key(text):
    """Comparable form of a site name: no state names, punctuation, or 'the'."""
    text = STATE_WORDS.sub(' ', text)
    return slugify(re.sub(r'\bthe\b', ' ', text, flags=re.I))


def find_existing(site_text, suggestions):
    key = match_key(site_text)
    if not key:
        return None
    for s in suggestions:
        k = match_key(s['name'])
        if key == k or (len(key) > 8 and (key in k or k in key)):
            return s
    return None


def write_csv(suggestions):
    cols = ['name', 'state', 'status', 'public', 'times_suggested', 'first_received',
            'agency_type', 'acreage', 'themes', 'note', 'review']
    with open(CSV_OUT, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for s in suggestions:
            w.writerow([', '.join(s.get(c, [])) if c == 'themes' else s.get(c, '')
                        for c in cols])


def main(argv):
    dry = '--dry-run' in argv
    if '--file' in argv:
        raw = open(argv[argv.index('--file') + 1]).read()
    else:
        raw = fetch_remote()

    with open(SUGGESTIONS) as f:
        suggestions = json.load(f)
    seen = set()
    if os.path.exists(INBOX):
        with open(INBOX) as f:
            seen = {line.strip() for line in f if line.strip()}

    new_lines = [l.strip() for l in raw.splitlines() if l.strip() and l.strip() not in seen]
    if not new_lines:
        print('No new submissions.')
        write_csv(suggestions)
        return

    for line in new_lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f'  skipped unreadable line: {line[:80]}')
            continue
        site = (rec.get('site') or '').strip()
        if not site:
            continue
        month = (rec.get('received') or '')[:7]
        hit = find_existing(site, suggestions)
        if hit:
            hit['times_suggested'] = hit.get('times_suggested', 1) + 1
            print(f'  +1  {hit["name"]} (now {hit["times_suggested"]})')
        else:
            sid = slugify(site)
            n, base = 2, sid
            while any(s['id'] == sid for s in suggestions):
                sid, n = f'{base}-{n}', n + 1
            suggestions.insert(0, {
                'id': sid, 'name': site, 'state': '', 'agency': '', 'agency_type': '',
                'designated': '', 'acreage': '', 'lat': None, 'lng': None,
                'status': 'received', 'public': False, 'times_suggested': 1,
                'first_received': month, 'themes': [], 'note': '',
                'review': 'New submission; see submissions/inbox.jsonl for the message.',
                'sources': [],
            })
            print(f'  new {site}')

    if dry:
        print(f'Dry run: {len(new_lines)} new line(s), nothing written.')
        return
    with open(INBOX, 'a') as f:
        for line in new_lines:
            f.write(line + '\n')
    with open(SUGGESTIONS, 'w') as f:
        json.dump(suggestions, f, ensure_ascii=False, indent=2)
        f.write('\n')
    write_csv(suggestions)
    print(f'Merged {len(new_lines)} submission(s). Wrote {SUGGESTIONS} and {CSV_OUT}.')


if __name__ == '__main__':
    main(sys.argv[1:])
