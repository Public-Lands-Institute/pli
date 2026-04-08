#!/usr/bin/env python3
"""Deploy PLI site to DreamHost via SFTP."""

import os, stat
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import paramiko

HOST     = os.environ['DREAMHOST_HOST']
USER     = os.environ['DREAMHOST_USER']
PASS     = os.environ['DREAMHOST_PASS']
REMOTE   = os.environ['DREAMHOST_REMOTE_PATH']

EXCLUDE = {'.env', '.git', '__pycache__'}

def sftp_mkdir_p(sftp, remote_path):
    parts = Path(remote_path).parts
    current = ''
    for part in parts:
        current = str(Path(current) / part) if current else part
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)

def upload_dir(sftp, local_dir, remote_dir):
    local_dir = Path(local_dir)
    for item in sorted(local_dir.iterdir()):
        if item.name.startswith('.') or item.name in EXCLUDE:
            continue
        remote_path = f'{remote_dir}/{item.name}'
        if item.is_dir():
            try:
                sftp.stat(remote_path)
            except FileNotFoundError:
                sftp.mkdir(remote_path)
            upload_dir(sftp, item, remote_path)
        else:
            try:
                remote_stat = sftp.stat(remote_path)
                local_mtime = item.stat().st_mtime
                if local_mtime <= remote_stat.st_mtime:
                    continue
            except FileNotFoundError:
                pass
            print(f'  {remote_path}')
            sftp.put(str(item), remote_path)

print(f'Connecting to {HOST}...')
transport = paramiko.Transport((HOST, 22))
transport.connect(username=USER, password=PASS)
sftp = paramiko.SFTPClient.from_transport(transport)

print(f'Uploading to {REMOTE}...')
upload_dir(sftp, '.', REMOTE)

sftp.close()
transport.close()
print('Done.')
