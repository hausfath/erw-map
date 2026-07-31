#!/usr/bin/env bash
# Regenerate tests/fixtures/pk2004_tables.txt from the primary source.
#
# Palandri & Kharaka (2004), USGS Open-File Report 2004-1068. Public domain
# (US Government work). We commit only the parameter tables -- ~5 KB -- so that
# test_kinetics.py gate 4 can re-verify every kinetic constant offline instead
# of trusting a hand transcription.
#
# Requires: curl, pdftotext (poppler), python3
set -euo pipefail

cd "$(dirname "$0")/.."
URL="https://pubs.usgs.gov/of/2004/1068/pdf/OFR_2004_1068.pdf"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "fetching $URL"
curl -sSfL -A "Mozilla/5.0" -o "$TMP/pk.pdf" "$URL"
pdftotext -layout "$TMP/pk.pdf" "$TMP/pk.txt"

mkdir -p tests/fixtures
python3 scripts/extract_pk_fixture.py "$TMP/pk.txt" tests/fixtures/pk2004_tables.txt

# Raw PDF is discarded by the trap: download, derive, delete.
python3 scripts/test_kinetics.py
