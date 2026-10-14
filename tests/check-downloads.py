#!/usr/bin/env python3
"""Usage: check-downloads.py [base-url]

Proves every package the live indexes list can be downloaded the way apt, dnf
and pacman download it: through the Cloudflare redirect to the media-server
GitHub release. Per entry it checks that
  1. the repo path redirects to a media-server release download URL,
  2. that URL answers after all redirects, and
  3. the release's own .sha256 file matches the SHA-256 in the index,
so a redirect to the wrong release fails here instead of on a user's machine.
"""
import gzip
import io
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'https://repo.nomercy.tv').rstrip('/')
RELEASES = 'https://github.com/NoMercy-Entertainment/nomercy-media-server/releases/'
# Cloudflare refuses the default Python user agent.
HEADERS = {'User-Agent': 'nomercy-packages-check/1 curl/8'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


no_redirect = urllib.request.build_opener(NoRedirect)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
        return r.read()


def first_hop(url):
    """The Location the repo answers with, without following it."""
    try:
        no_redirect.open(urllib.request.Request(url, method='HEAD', headers=HEADERS), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            return e.headers['Location']
        raise
    raise RuntimeError('answered without a redirect (is the file on Pages again?)')


def status_after_redirects(url):
    with urllib.request.urlopen(urllib.request.Request(url, method='HEAD', headers=HEADERS), timeout=60) as r:
        return r.status


entries = []  # (path, sha256 the index promises)
packages = get(f'{BASE}/apt/dists/stable/main/binary-amd64/Packages').decode()
for block in packages.strip().split('\n\n'):
    entries.append(('apt/' + re.search(r'^Filename: (\S+)', block, re.M).group(1),
                    re.search(r'^SHA256: (\w+)', block, re.M).group(1)))

repomd = get(f'{BASE}/rpm/repodata/repomd.xml').decode()
primary = re.search(r'href="(repodata/[^"]*primary\.xml\.(?:gz|zst))"', repomd).group(1)
raw = get(f'{BASE}/rpm/{primary}')
# Newer createrepo_c writes zstd; the standard library reads only gzip before Python 3.14.
xml = gzip.decompress(raw) if primary.endswith('.gz') else subprocess.run(
    ['zstd', '-dc'], input=raw, capture_output=True, check=True).stdout
for pkg in re.findall(r'<package .*?</package>', xml.decode(), re.S):
    entries.append(('rpm/' + re.search(r'<location href="([^"]+)"', pkg).group(1),
                    re.search(r'<checksum type="sha256"[^>]*>(\w+)<', pkg).group(1)))

db = tarfile.open(fileobj=io.BytesIO(get(f'{BASE}/arch/x86_64/nomercy.db')))
for member in db.getmembers():
    if member.name.endswith('/desc'):
        desc = db.extractfile(member).read().decode()
        entries.append(('arch/x86_64/' + re.search(r'%FILENAME%\n(\S+)', desc).group(1),
                        re.search(r'%SHA256SUM%\n(\w+)', desc).group(1)))

failed = 0
for path, want in entries:
    try:
        target = first_hop(f'{BASE}/{path}')
        if not target.startswith(RELEASES):
            raise RuntimeError(f'redirects to {target}, not a media-server release')
        status = status_after_redirects(target)
        have = get(target + '.sha256').decode().split()[0]
        if have != want:
            raise RuntimeError(f'release sha256 {have[:12]} != index sha256 {want[:12]}')
    except Exception as e:  # noqa: BLE001 - every failure kind is reported the same way
        print(f'FAIL {path}: {e}')
        failed += 1
        continue
    print(f'ok   {path} -> {target[len(RELEASES):]} ({status})')

print(f'check-downloads: {len(entries) - failed} of {len(entries)} downloadable')
sys.exit(1 if failed or not entries else 0)
