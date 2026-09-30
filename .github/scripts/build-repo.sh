#!/usr/bin/env bash
# Builds the signed apt, rpm and pacman repositories into $OUT from the
# packages in $DOWNLOADS. The workflow calls this; run it locally the same way.
#
# Environment:
#   LATEST      newest version, for example 0.1.533 (required)
#   GNUPGHOME   a keyring that holds the repository signing key (required)
#   DOWNLOADS   folder with the downloaded packages (default: downloads)
#   OUT         output tree (default: website)
#   RPM_IMAGE   container used when createrepo_c is not installed (default: fedora:latest)
#   ARCH_IMAGE  container used when repo-add is not installed (default: archlinux:latest)
#
# Every failing step fails the script. A half-built repository is never deployed.
set -euo pipefail

LATEST="${LATEST:?LATEST is required}"
: "${GNUPGHOME:?GNUPGHOME must point at a keyring that holds the signing key}"
DOWNLOADS="${DOWNLOADS:-downloads}"
OUT="${OUT:-website}"
RPM_IMAGE="${RPM_IMAGE:-fedora:latest}"
ARCH_IMAGE="${ARCH_IMAGE:-archlinux:latest}"

die() { echo "ERROR: $*" >&2; exit 1; }

command -v gpg >/dev/null || die "gpg is not installed"
command -v dpkg-scanpackages >/dev/null || die "dpkg-scanpackages is not installed (dpkg-dev)"
KEY_FPR="$(gpg --batch --list-secret-keys --with-colons | awk -F: '/^fpr/ {print $10; exit}')"
[ -n "$KEY_FPR" ] || die "no secret key in GNUPGHOME"
sign() { gpg --batch --yes --local-user "$KEY_FPR" "$@"; }

# Run a tool from a container when it is not installed. Files go in and out as
# tar streams, so this works on a runner that is itself a container: a
# bind-mounted path would name the wrong machine.
need_docker() { command -v docker >/dev/null || die "$1 is not installed and docker is not available"; }

# ---------------------------------------------------------------- APT
echo "=== APT ==="
mkdir -p "$OUT/apt/pool/main/n/nomercy" "$OUT/apt/dists/stable/main/binary-amd64"
shopt -s nullglob
debs=("$DOWNLOADS"/*_amd64.deb)
[ "${#debs[@]}" -gt 0 ] || die "no .deb packages in $DOWNLOADS"
cp "${debs[@]}" "$OUT/apt/pool/main/n/nomercy/"

if [ -f "$OUT/apt/pool/main/n/nomercy/nomercy_${LATEST}_amd64.deb" ]; then
  ln -sf "nomercy_${LATEST}_amd64.deb" "$OUT/apt/pool/main/n/nomercy/nomercy_latest_amd64.deb"
fi

(
  cd "$OUT/apt"
  dpkg-scanpackages --multiversion pool/ > dists/stable/main/binary-amd64/Packages
  gzip -k -f dists/stable/main/binary-amd64/Packages
)

(
  cd "$OUT/apt/dists/stable"
  cat > Release <<'EOF'
Origin: NoMercy Entertainment
Label: NoMercy
Suite: stable
Codename: stable
Version: 1.0
Architectures: amd64
Components: main
Description: NoMercy Entertainment Repository
EOF
  echo "Date: $(date -u '+%a, %d %b %Y %H:%M:%S UTC')" >> Release
  echo "SHA256:" >> Release
  for file in main/binary-amd64/Packages main/binary-amd64/Packages.gz; do
    [ -f "$file" ] || die "$file missing"
    echo " $(sha256sum "$file" | cut -d' ' -f1) $(stat -c%s "$file") $file" >> Release
  done
  sign --clear-sign -o InRelease Release
  sign --detach-sign --armor -o Release.gpg Release
)

# ---------------------------------------------------------------- RPM
echo "=== RPM ==="
mkdir -p "$OUT/rpm/packages"
rpms=("$DOWNLOADS"/*.rpm)
[ "${#rpms[@]}" -gt 0 ] || die "no .rpm packages in $DOWNLOADS"
[ -f "$DOWNLOADS/nomercy-${LATEST}-1.x86_64.rpm" ] || die "the rpm of the latest release ($LATEST) is missing"
cp "${rpms[@]}" "$OUT/rpm/packages/"

if command -v createrepo_c >/dev/null; then
  (cd "$OUT/rpm" && createrepo_c .)
else
  need_docker createrepo_c
  tar -C "$OUT/rpm" -cf - packages \
    | docker run --rm -i "$RPM_IMAGE" sh -ec \
        'dnf -qy install createrepo_c >&2; mkdir /w; tar -xf - -C /w; createrepo_c /w >&2; tar -C /w -cf - repodata' \
    | tar -C "$OUT/rpm" -xf -
fi
[ -f "$OUT/rpm/repodata/repomd.xml" ] || die "createrepo_c did not write repodata/repomd.xml"

# Packages are not signed yet. The signed repomd.xml holds their checksums, so
# repo_gpgcheck=1 protects them; gpgcheck=0 until the packages are signed too.
cat > "$OUT/rpm/nomercy.repo" <<'EOF'
[nomercy]
name=NoMercy Entertainment
baseurl=https://repo.nomercy.tv/rpm
enabled=1
gpgcheck=0
repo_gpgcheck=1
gpgkey=https://repo.nomercy.tv/nomercy_repo.gpg.pub
EOF
sign --detach-sign --armor -o "$OUT/rpm/repodata/repomd.xml.asc" "$OUT/rpm/repodata/repomd.xml"

# ---------------------------------------------------------------- Arch
echo "=== Arch ==="
mkdir -p "$OUT/arch/x86_64"
pkgs=("$DOWNLOADS"/*.pkg.tar.zst)
[ "${#pkgs[@]}" -gt 0 ] || die "no .pkg.tar.zst packages in $DOWNLOADS"
LATEST_PKG="nomercy-${LATEST}-1-x86_64.pkg.tar.zst"
[ -f "$DOWNLOADS/$LATEST_PKG" ] || die "the Arch package of the latest release ($LATEST) is missing"
cp "${pkgs[@]}" "$OUT/arch/x86_64/"

# pacman keeps one version per package name in the database: the latest.
# Older files stay downloadable for anyone pinning a version.
DB_DIR="$OUT/arch/x86_64"
if command -v repo-add >/dev/null; then
  (cd "$DB_DIR" && repo-add nomercy.db.tar.gz "$LATEST_PKG")
else
  need_docker repo-add
  tar -C "$DB_DIR" -cf - "$LATEST_PKG" \
    | docker run --rm -i "$ARCH_IMAGE" sh -ec \
        'mkdir /w; tar -xf - -C /w; cd /w; repo-add nomercy.db.tar.gz nomercy-*.pkg.tar.zst >&2; tar -cf - nomercy.db.tar.gz nomercy.files.tar.gz' \
    | tar -C "$DB_DIR" -xf -
fi
[ -f "$DB_DIR/nomercy.db.tar.gz" ] || die "repo-add did not write nomercy.db.tar.gz"
# GitHub Pages does not serve symlinks: pacman asks for nomercy.db and
# nomercy.db.sig, so they are real copies.
rm -f "$DB_DIR/nomercy.db" "$DB_DIR/nomercy.files"
cp "$DB_DIR/nomercy.db.tar.gz" "$DB_DIR/nomercy.db"
cp "$DB_DIR/nomercy.files.tar.gz" "$DB_DIR/nomercy.files"
sign --detach-sign -o "$DB_DIR/nomercy.db.sig" "$DB_DIR/nomercy.db"

echo "=== Tree built ==="
find "$OUT" -maxdepth 3 -not -name '*.deb' -not -name '*.rpm' -not -name '*.zst' | sort | head -60
