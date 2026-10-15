#!/usr/bin/env python3
"""Build the small Pages portion of the tv.nomercy Maven repository."""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET


REPOS = {
    "nomercy-player-core-kmp": "nomercy-player-core-",
    "nomercy-video-player-kmp": "nomercy-video-player-",
    "nomercy-music-player-kmp": "nomercy-music-player-",
}


def releases(repo, fixture_dir):
    if fixture_dir:
        return json.loads((Path(fixture_dir) / f"{repo}.json").read_text())
    url = f"https://api.github.com/repos/NoMercy-Entertainment/{repo}/releases?per_page=100"
    result = []
    while url:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "nomercy-maven-metadata"}
        if os.environ.get("GH_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as response:
            result.extend(json.load(response))
            link = response.headers.get("Link", "")
        match = re.search(r'<([^>]+)>; rel="next"', link)
        url = match.group(1) if match else None
    return result


def version_key(version):
    # The libraries use numeric dotted versions, optionally followed by a suffix.
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:-(.+))?", version)
    if not match:
        raise ValueError(f"unsupported release version: {version}")
    return (tuple(int(part) for part in match.group(1).split(".")), match.group(2) is None, match.group(2) or "")


def inventory(fixture_dir):
    artifacts = {}
    state = []
    for repo, prefix in REPOS.items():
        for release in releases(repo, fixture_dir):
            if release.get("draft") or release.get("prerelease"):
                continue
            tag = release["tag_name"]
            if not tag.startswith("v"):
                continue
            version = tag[1:]
            version_key(version)
            matching = []
            for asset in release.get("assets", []):
                name = asset["name"]
                match = re.fullmatch(rf"({re.escape(prefix)}[a-z0-9-]+)-{re.escape(version)}(?:[.-].+)", name)
                if match:
                    matching.append((match.group(1), asset))
            if not matching:
                continue  # Older releases may only contain an XCFramework.
            by_artifact = {}
            for artifact, asset in matching:
                by_artifact.setdefault(artifact, set()).add(asset["name"])
            for artifact, names in by_artifact.items():
                if f"{artifact}-{version}.pom" not in names or f"{artifact}-{version}.module" not in names:
                    # Some historical releases uploaded only part of a variant.
                    # Do not advertise a version Gradle cannot resolve.
                    print(f"skipping incomplete publication: {repo} {tag} {artifact}", file=sys.stderr)
                    continue
                incomplete = [name for name in names
                              if not name.endswith((".asc", ".md5", ".sha1"))
                              and not all(name + ext in names for ext in (".asc", ".md5", ".sha1"))]
                if incomplete:
                    print(f"historical publication lacks signature or checksum: {repo} {tag} {artifact}: {incomplete[0]}", file=sys.stderr)
                newest = max((asset.get("updated_at") or release["published_at"] for item, asset in matching if item == artifact))
                artifacts.setdefault(artifact, {})[version] = newest
            state.append((repo, tag, sorted((asset["id"], asset["name"], asset.get("digest")) for _, asset in matching)))
    if not artifacts:
        raise ValueError("no published Maven release assets found")
    return artifacts, state


def build_metadata(output, artifacts):
    for artifact, versions in sorted(artifacts.items()):
        ordered = sorted(versions, key=version_key)
        latest = ordered[-1]
        root = ET.Element("metadata")
        ET.SubElement(root, "groupId").text = "tv.nomercy"
        ET.SubElement(root, "artifactId").text = artifact
        versioning = ET.SubElement(root, "versioning")
        ET.SubElement(versioning, "latest").text = latest
        ET.SubElement(versioning, "release").text = latest
        entries = ET.SubElement(versioning, "versions")
        for version in ordered:
            ET.SubElement(entries, "version").text = version
        ET.SubElement(versioning, "lastUpdated").text = datetime.fromisoformat(
            max(versions.values()).replace("Z", "+00:00")
        ).strftime("%Y%m%d%H%M%S")
        content = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
        folder = output / "tv" / "nomercy" / artifact
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "maven-metadata.xml").write_bytes(content)
        for algorithm in ("md5", "sha1", "sha256", "sha512"):
            (folder / f"maven-metadata.xml.{algorithm}").write_text(hashlib.new(algorithm, content).hexdigest())
    print(f"wrote metadata and four checksums for {len(artifacts)} artifacts")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--state-only", action="store_true")
    args = parser.parse_args()
    artifacts, state = inventory(args.fixture_dir)
    if args.state_only:
        print(hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest())
    else:
        if not args.output:
            parser.error("--output is required")
        build_metadata(args.output, artifacts)


if __name__ == "__main__":
    main()
