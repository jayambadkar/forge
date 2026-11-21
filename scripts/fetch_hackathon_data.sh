#!/usr/bin/env bash
# Download the public development book into data/hackathon.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/data/hackathon"
TMP="$(mktemp -d)"
curl -sL -o "$TMP/hackathon.zip" "https://drive.usercontent.google.com/download?id=1WcZKDHAhpaNjbAxau0Mmecwvy80OXD_9&export=download&confirm=t"
unzip -q "$TMP/hackathon.zip" -x '__MACOSX/*' -d "$TMP"
rm -rf "$DEST/institutions" "$DEST/BRIEF.html" "$DEST/README.md"
mkdir -p "$DEST"
cp -a "$TMP/hackathon/institutions" "$DEST/institutions"
cp -a "$TMP/hackathon/BRIEF.html" "$TMP/hackathon/README.md" "$DEST/"
rm -rf "$TMP"
echo "fetched $DEST"
