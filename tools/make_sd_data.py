#!/usr/bin/env python3
"""Build the "sd_data" part of publish/request.json from the SD Index sheet (Google Sheet exported as .xlsx).

Usage:
  V15_PASSWORD='...' python3 tools/make_sd_data.py "SD Index V15.xlsx" --updated "22 Oct 2026" \\
      [--old index.html --report report.json --links extra.json] > sd_data.json

Uses the same parser as build_page.py, so the sheet layout rules are unchanged (D-G = villa types,
HYPERLINK cells, orange = check, 'Drive Links' and 'Ref Matching Notes' tabs).
Output: {"enc": <encrypted {"z": zlib+base64 of the row data}>, "updated": "..."} - safe to commit (encrypted).
"""
import argparse, base64, json, os, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_page as bp

ap = argparse.ArgumentParser()
ap.add_argument("xlsx"); ap.add_argument("--updated", required=True)
ap.add_argument("--old"); ap.add_argument("--report"); ap.add_argument("--links")
a = ap.parse_args()
pw = os.environ.get("V15_PASSWORD") or sys.exit("Set V15_PASSWORD")
ws, links, notes = bp.load(a.xlsx)
if a.links:
    extra = json.load(open(a.links))
    links.update({(k if k.startswith(bp.PREFIX) else bp.PREFIX + k): v for k, v in extra.items()})
data, missing = bp.parse(ws, links, notes)
rep = {"items": sum(len(s["items"]) for g in data for s in g["subs"]),
       "links": sum(1 for g in data for s in g["subs"] for it in s["items"] for c in it["c"] if c.get("url")),
       "missing_links": missing}
if a.old:
    rep["changes"] = bp.diff(bp.decrypt_page(a.old, pw), data)
if a.report:
    json.dump(rep, open(a.report, "w"), indent=1, ensure_ascii=False)
z = base64.b64encode(zlib.compress(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 9)).decode()
print(json.dumps({"enc": bp.encrypt({"z": z}, pw), "updated": a.updated}, separators=(",", ":")))
