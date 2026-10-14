#!/usr/bin/env bash
# Usage: check-tree.sh <built-tree-dir>
# Checks a built repo tree has everything the install page needs.
set -u
T="${1:?tree dir}"
fail=0
need() { # path description
  if [ -e "$T/$1" ]; then echo "ok   $1"; else echo "FAIL missing $1 ($2)"; fail=$((fail+1)); fi
}
need apt/dists/stable/Release "apt"
need apt/dists/stable/InRelease "apt"
need apt/dists/stable/Release.gpg "apt"
need apt/dists/stable/main/binary-amd64/Packages "apt"
need rpm/nomercy.repo "dnf repo file"
need rpm/repodata/repomd.xml "rpm metadata"
need rpm/repodata/repomd.xml.asc "rpm metadata signature"
need arch/x86_64/nomercy.db "pacman database"
need arch/x86_64/nomercy.db.sig "pacman database signature"
need nomercy_repo.gpg.pub "public key"
need CNAME "pages"
need .nojekyll "pages"
if [ -f "$T/rpm/nomercy.repo" ]; then
  grep -q '^repo_gpgcheck=1' "$T/rpm/nomercy.repo" || { echo "FAIL nomercy.repo lacks repo_gpgcheck=1"; fail=$((fail+1)); }
  grep -q '^gpgkey=https://repo.nomercy.tv/nomercy_repo.gpg.pub' "$T/rpm/nomercy.repo" || { echo "FAIL nomercy.repo gpgkey"; fail=$((fail+1)); }
fi
# Package files live on the media-server GitHub releases; Cloudflare redirects
# their repo.nomercy.tv paths there. A copy in the tree would push the Pages site
# past its 1 GB limit again (it reached about 3.3 GB).
binaries="$(find "$T" -type f \( -name '*.deb' -o -name '*.rpm' -o -name '*.pkg.tar.zst' \) | head -5)"
if [ -n "$binaries" ]; then
  echo "FAIL package files in the tree (they are served from GitHub releases):"
  echo "$binaries" | sed 's/^/     /'
  fail=$((fail+1))
fi
size_mb=$(( $(du -sk "$T" | cut -f1) / 1024 ))
if [ "$size_mb" -gt 500 ]; then
  echo "FAIL tree is ${size_mb} MB; the Pages limit is 1 GB"
  fail=$((fail+1))
else
  echo "ok   tree is ${size_mb} MB"
fi
echo "check-tree: $fail failed"
[ "$fail" -eq 0 ]
