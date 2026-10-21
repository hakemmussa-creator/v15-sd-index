#!/usr/bin/env python3
"""Build ifc.html (IFC drawing package tab) from a listing of the IFC folder.

The IFC package is a fixed, issued set: build once, no daily updates.

Usage:
  IFC_PASSWORD=... python3 tools/build_ifc.py tree.json --out ifc.html [--sample]

tree.json = {"n": "IFC Package", "d": [child nodes], "f": [drawings], "cnt": {ext: count}}
  node    = {"n": label, "d": [...], "f": [...], "cnt": {...}, "u": optional Drive folder url}
  drawing = {"t": file stem, "x": {"pdf": {"s": bytes, "u": optional Drive file url}, "dwg": {...}}}
Head, logo, colours and the password lock are taken from tools/submittals_template.html so the
three tabs look the same; the tree view itself is tools/ifc_part.html.
"""
import argparse, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_submittals import encrypt


def strip(n):
    out = {"n": n["n"], "d": [strip(d) for d in n["d"]], "f": [], "cnt": n["cnt"]}
    if n.get("u"):
        out["u"] = n["u"]
    for f in n["f"]:
        out["f"].append({"t": f["t"], "x": {e: {k: v for k, v in x.items() if k in ("s", "u")} for e, x in f["x"].items()}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tree")
    ap.add_argument("--out", default="ifc.html")
    ap.add_argument("--sample", action="store_true", help="show the 'links after upload' note")
    a = ap.parse_args()
    pw = os.environ["IFC_PASSWORD"]
    tree = strip(json.load(open(a.tree, encoding="utf-8")))
    sub = open(os.path.join(HERE, "submittals_template.html"), encoding="utf-8").read()
    head = sub[:sub.index("</head>")]
    head = re.sub(r"<title>.*?</title>", "<title>V15 IFC Drawing Package</title>", head)
    logo = re.search(r'<img class="logo"[^>]*>', sub).group(0)
    header = (f'<header class="tb">{logo}<small>Grand Polo Club &amp; Resort · Cluster Montura (V15)</small>'
              '<h1>IFC Drawing Package</h1><p>Issued for Construction set by discipline. Tap a branch to open it; '
              'tap a level above to go back.</p><div class="nav2"><a href="./">Shop drawing index</a>'
              '<a href="./submittals.html">MAS / PQN / RFI</a></div></header>')
    note = ('<p class="note">Sample for review – PDF / DWG buttons and Drive folder links are connected once the '
            'IFC upload to Google Drive is complete.</p>') if a.sample else ""
    part = open(os.path.join(HERE, "ifc_part.html"), encoding="utf-8").read()
    part = part.replace("__HEADER__", header).replace("__NOTE__", note).replace("__ENC__", json.dumps(encrypt(tree, pw)))
    html = head.replace("</style>\n", "</style>\n", 1) + part
    open(a.out, "w", encoding="utf-8").write(html)

    def walk(n):
        c = [1, len(n["f"])]
        for d in n["d"]:
            x = walk(d); c[0] += x[0]; c[1] += x[1]
        return c
    f, d = walk(tree)
    print(json.dumps({"out": a.out, "folders": f, "drawings": d, "bytes": len(html)}))


if __name__ == "__main__":
    main()
