"""
Extract the Palandri & Kharaka parameter rows into a small committed fixture.

Called by fetch_pk_tables.sh. Splitting the PDF text on "Table N." is
unreliable because the table-of-contents lines match too, so instead we keep
any line that looks like an actual parameter row: a mineral name followed by a
negative log-k and a numeric activation energy.

Usage: python3 extract_pk_fixture.py <pdftotext-output> <fixture-out>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HEADER = (
    "# Extract of USGS OFR 2004-1068 (Palandri & Kharaka 2004) parameter rows.\n"
    "# Source: https://pubs.usgs.gov/of/2004/1068/pdf/OFR_2004_1068.pdf\n"
    "# Public domain (US Government work). Committed as a test fixture so\n"
    "# test_kinetics.py gate 4 can re-verify every kinetic constant offline\n"
    "# rather than trusting a hand transcription.\n"
    "#\n"
    "# Columns, per the source table footnotes:\n"
    "#   log k : rate constant at 25 C, pH = 0, mol m-2 s-1\n"
    "#   E     : Arrhenius activation energy, kJ mol-1\n"
    "#   n     : reaction order with respect to H+\n\n"
)

# A parameter row: leading mineral name, then log k (negative, 2 dp), then E.
ROW = re.compile(r"^\s*([A-Za-z][A-Za-z\- ]{2,20}?)\s+(-\d+\.\d{2})\s+(-?\d+\.\d)\b")


def main(src: Path, out: Path) -> int:
    rows, seen = [], set()
    for line in src.read_text(errors="replace").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        name = m.group(1).strip().lower()
        # Skip prose that happens to be followed by numbers.
        if " " in name or len(name) < 4:
            continue
        key = (name, m.group(2), m.group(3))
        if key in seen:
            continue
        seen.add(key)
        rows.append(line.rstrip())

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEADER + "\n".join(rows) + "\n")
    print(f"wrote {out} ({len(rows)} parameter rows, {out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
