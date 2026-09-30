#!/usr/bin/env python3
"""Check the install page against the real repo.

Usage: check-page.py <index.html> <built-tree-dir>

Checks, per tab:
  a) the packages named in the install command equal the real package "nomercy"
  b) every https://repo.nomercy.tv/... path the commands name exists in the tree
  c) the apt key step creates /etc/apt/keyrings before it writes into it
"""
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

REAL_PACKAGE = "nomercy"
BASE = "https://repo.nomercy.tv"


class Tabs(HTMLParser):
    """Collect the text of every <code> block, grouped by tab-content id."""

    def __init__(self):
        super().__init__()
        self.tab = None
        self.tab_depth = 0
        self.depth = 0
        self.in_code = False
        self.buf = []
        self.tabs = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            self.depth += 1
            if "tab-content" in (a.get("class") or "").split() and self.tab is None:
                self.tab = a.get("id")
                self.tab_depth = self.depth
                self.tabs[self.tab] = []
        if tag == "code" and self.tab:
            self.in_code = True
            self.buf = []

    def handle_endtag(self, tag):
        if tag == "code" and self.in_code:
            self.in_code = False
            self.tabs[self.tab].append(html.unescape("".join(self.buf)).strip())
        if tag == "div":
            if self.tab is not None and self.depth == self.tab_depth:
                self.tab = None
            self.depth -= 1

    def handle_data(self, data):
        if self.in_code:
            self.buf.append(data)


def url_exists(tree: Path, url: str) -> bool:
    rel = url[len(BASE):].split("?")[0].lstrip("/")
    rel = rel.replace("$arch", "x86_64")
    p = tree / rel
    if p.is_file():
        return True
    if p.is_dir():
        # a repo root: apt needs dists/stable/Release, pacman needs the db
        return (p / "dists/stable/Release").is_file() or (p / "nomercy.db").is_file()
    return False


def main():
    page, tree = Path(sys.argv[1]), Path(sys.argv[2])
    parser = Tabs()
    parser.feed(page.read_text(encoding="utf-8"))
    failures = []
    for tab, blocks in parser.tabs.items():
        for i, cmd in enumerate(blocks):
            m = re.search(r"(?:apt install|dnf install|pacman -S)\s+(.*)$", cmd, re.M)
            if m:
                pkgs = m.group(1).split()
                if pkgs != [REAL_PACKAGE]:
                    failures.append(f"[{tab}] (a) package names {pkgs}, real package is ['{REAL_PACKAGE}']: {cmd}")
            for url in re.findall(r"https://repo\.nomercy\.tv/[^\s\"']*", cmd):
                if not url_exists(tree, url):
                    failures.append(f"[{tab}] (b) {url} does not exist in the tree")
            if "-o /etc/apt/keyrings/" in cmd:
                same = "mkdir" in cmd and cmd.index("mkdir") < cmd.index("-o /etc/apt/keyrings/")
                earlier = any("mkdir" in e and "/etc/apt/keyrings" in e for e in blocks[:i])
                if not (same or earlier):
                    failures.append(f"[{tab}] (c) writes /etc/apt/keyrings/ without creating it first: {cmd}")
    if not parser.tabs:
        failures.append("no tabs found in the page")
    for f in failures:
        print("FAIL", f)
    print(f"check-page: {len(failures)} failed, tabs={sorted(parser.tabs)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
