#!/usr/bin/env python3
"""Set (or change) the DM inspections sheet that index.html reads live.

Usage: PAGE_PASSWORD=... python3 tools/set_dm_source.py index.html <drive file id> [log tab name]

The sheet must be link-shared "Anyone with the link - Viewer". Its FIRST tab is the DM table
(row 3 onwards: col D Emaar No, E type, F/H/J/L/N ref no, G/I/K/M/O status); the optional log tab
has a header row starting with "Date" (Date | Emaar No | Type | Stage | DM ref no | Status).
The id is stored encrypted (const DMS) so only people with the page password can find the sheet.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_submittals import encrypt

page, fid = sys.argv[1], sys.argv[2]
log = sys.argv[3] if len(sys.argv) > 3 else "Updates log"
t = open(page, encoding="utf-8").read()
new = "const DMS = " + json.dumps(encrypt({"id": fid, "log": log}, os.environ["PAGE_PASSWORD"])) + ";"
t, n = re.subn(r"const DMS = (\{.*?\}|null|__DMS__);", lambda m: new, t, count=1, flags=re.S)
if n != 1:
    sys.exit("const DMS not found - page has no DM panel")
open(page, "w", encoding="utf-8").write(t)
print("DM source set:", page, "log tab:", log)
