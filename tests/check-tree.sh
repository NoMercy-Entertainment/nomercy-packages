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
echo "check-tree: $fail failed"
[ "$fail" -eq 0 ]
