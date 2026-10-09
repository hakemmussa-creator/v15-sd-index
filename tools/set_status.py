#!/usr/bin/env python3
"""Store the latest Unifier status per reference (encrypted) in a page, for the colour coding.

Usage:
  PAGE_PASSWORD='...' python3 tools/set_status.py index.html status.json
status.json: {"SD-ARC-052": ["B", 2], "MAS-ARC-098": ["C", 0], ...}   # [code, latest rev]
code: A/B approved (green) · C/D/F resubmit (red) · U under review (yellow) · E information (grey).
Rule used: latest revision record; Pending_By_Engineer -> U; else Employer's Representative decision if any,
else consultant code (Consustatuts), else 'Approved' status -> A, else U.
The whole map is stored in both pages (each page only shows its own refs).
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_submittals import encrypt
from add_updates import dec


def main():
    page, stat = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
    pw = os.environ.get("PAGE_PASSWORD") or sys.exit("Set PAGE_PASSWORD")
    t = open(page, encoding="utf-8").read()
    dec(json.loads(re.search(r"const ENC = (\{.*?\});", t, re.S).group(1)), pw)  # password check
    m = re.search(r"const STA = (\{.*?\}|null);", t, re.S)
    if not m:
        sys.exit("page has no STA slot – rebuild it from the v2 template first")
    t = t[:m.start(1)] + json.dumps(encrypt(stat, pw)) + t[m.end(1):]
    open(page, "w", encoding="utf-8").write(t)
    print(page, ":", len(stat), "statuses stored")


if __name__ == "__main__":
    main()
