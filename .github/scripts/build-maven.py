#!/usr/bin/env python3
"""Builds the Maven index of repo.nomercy.tv/maven into <out>/maven.

Usage: build-maven.py <out>        (needs the gh CLI, logged in or GH_TOKEN set)

The artifact files (pom, module, jar, klib, aar, their checksums and .asc
signatures) are assets on each library's own GitHub release vX. Cloudflare
redirects /maven/tv/nomercy/<artifact>/<version>/<file> to that release. This
site holds only what Gradle and Maven ask for besides those files: one
maven-metadata.xml per artifact, listing every version that has a .pom on a
release, plus its checksums.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

OUT = sys.argv[1]
GROUP = 'tv.nomercy'
# Library repo -> the artifact prefix the Cloudflare rule for that repo matches.
# A .pom whose name does not start with its repo's prefix would be unreachable,
# so it fails the build instead of being listed.
LIBRARIES = {
    'NoMercy-Entertainment/nomercy-player-core-kmp': 'nomercy-player-core-kmp',
    'NoMercy-Entertainment/nomercy-video-player-kmp': 'nomercy-video-player',
    'NoMercy-Entertainment/nomercy-music-player-kmp': 'nomercy-music-player',
}
VERSION = r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?'


def releases(repo):
    out = subprocess.run(
        ['gh', 'api', '--paginate', f'repos/{repo}/releases?per_page=100',
         '--jq', '.[] | select(.draft == false) | {tag: .tag_name, assets: [.assets[].name]}'],
        capture_output=True, text=True, check=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def version_key(v):
    core, _, pre = v.partition('-')
    # A release sorts after its pre-releases: 1.0.0-rc1 < 1.0.0.
    return [int(x) for x in core.split('.')] + [0 if pre else 1, pre]


versions = {}  # artifact -> set of versions
for repo, prefix in LIBRARIES.items():
    for rel in releases(repo):
        tag_version = rel['tag'][1:] if rel['tag'].startswith('v') else None
        for name in rel['assets']:
            m = re.fullmatch(rf'(.+)-({VERSION})\.pom', name)
            if not m:
                continue
            artifact, version = m.groups()
            if version != tag_version:
                sys.exit(f'{repo} {rel["tag"]}: {name} is version {version}, but the redirect sends it to tag v{version}')
            if not artifact.startswith(prefix):
                sys.exit(f'{repo} {rel["tag"]}: {artifact} does not start with {prefix}, so no redirect rule reaches it')
            versions.setdefault(artifact, set()).add(version)

if not versions:
    sys.exit('no .pom assets found on any release')

stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
for artifact, found in sorted(versions.items()):
    ordered = sorted(found, key=version_key)
    releases_only = [v for v in ordered if '-' not in v] or ordered
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<metadata>',
        f'  <groupId>{GROUP}</groupId>',
        f'  <artifactId>{artifact}</artifactId>',
        '  <versioning>',
        f'    <latest>{ordered[-1]}</latest>',
        f'    <release>{releases_only[-1]}</release>',
        '    <versions>',
        *[f'      <version>{v}</version>' for v in ordered],
        '    </versions>',
        f'    <lastUpdated>{stamp}</lastUpdated>',
        '  </versioning>',
        '</metadata>',
        '',
    ]
    data = '\n'.join(lines).encode()
    folder = os.path.join(OUT, 'maven', *GROUP.split('.'), artifact)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'maven-metadata.xml'), 'wb') as f:
        f.write(data)
    for algorithm in ('md5', 'sha1', 'sha256', 'sha512'):
        with open(os.path.join(folder, f'maven-metadata.xml.{algorithm}'), 'w') as f:
            f.write(hashlib.new(algorithm, data).hexdigest())

print(f'maven: {len(versions)} artifacts, {sum(len(v) for v in versions.values())} artifact versions')
