#!/usr/bin/env python3
"""Build the password-protected V15 shop drawing index page from the Excel index.

Usage:
  V15_PASSWORD='...' python3 tools/build_page.py "SD Index V15 - Drive Links RevXX.xlsx" \
      [--out index.html] [--old index.html] [--updated "9 Oct 2026"] [--report report.json]

Reads sheet '4.SD (2)':
  - Column A text + column B empty  -> heading row (top-level if text contains '/', else sub-section)
  - Column A number                 -> drawing row; B = description; D..G = 4BR T01, 4BR T02, 5BR T03, 5BR T04
  - D..G cell = =HYPERLINK("url","GPD-V15-QTGC-SD-XXX-NNN") -> clickable ref
              = plain ref text      -> URL from the 'Drive Links' sheet (B ref / E url) or --links JSON; else reported missing
              = any other text      -> shown as status (NOT SUBMITTED, NOT IN REGISTER, N/A, a date ...)
  - Orange fill (FFC000) -> "check" flag (best-match ref); yellow fill (FFFF00) on "NOT IN REGISTER" -> highlighted
The decrypted data never contains the password; Drive links only exist inside the encrypted blob.
"""
import argparse, base64, datetime, json, os, re, sys

import openpyxl
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PREFIX = "GPD-V15-QTGC-SD-"
REF_RE = re.compile(r"^GPD-V15-QTGC-SD-[A-Z]+-\d+$")
LINK_RE = re.compile(r'^=HYPERLINK\("([^"]+)","([^"]+)"\)$')
TYPES = ["4BR T01", "4BR T02", "5BR T03", "5BR T04"]
ITERATIONS = 150000
HERE = os.path.dirname(os.path.abspath(__file__))

# Friendlier section names on the page (sheet headings are kept as-is in Excel)
RENAME = {
    "EXCAVATION WORKS": "Excavation",
    "ARCH GENERAL ARRENGEMENT": "Architectural General Arrangement",
    "RCP DRAWINGS": "Reflected Ceiling Plans",
    "ID GENERAL ARRENGEMENT": "ID General Arrangement",
    "WATERPROOFING &INSULATION": "Waterproofing & Insulation",
}


def nice(name):
    key = " ".join(name.split()).upper()
    if key in RENAME:
        return RENAME[key]
    n = re.sub(r"\s*(SHOP ?DRAWINGS|DRAWINGS)$", "", key, flags=re.I).title()
    return (n.replace("Arrengement", "Arrangement").replace("Id ", "ID ").replace("Mep", "MEP")
             .replace("Rcp", "RCP").replace(" And ", " and "))


def fill_rgb(cell):
    try:
        f = cell.fill
        if f is None or f.fill_type != "solid":
            return ""
        return (f.fgColor.rgb or "").upper() if isinstance(f.fgColor.rgb, str) else ""
    except Exception:
        return ""


def load(path):
    wb = openpyxl.load_workbook(path)  # formulas kept (HYPERLINK text)
    ws = wb["4.SD (2)"]
    links = {}
    if "Drive Links" in wb.sheetnames:
        for row in wb["Drive Links"].iter_rows(min_row=2, values_only=True):
            ref_cell, url = row[1], row[4]
            m = LINK_RE.match(str(ref_cell or ""))
            ref = m.group(2) if m else (ref_cell or "")
            if ref and url:
                links[str(ref).strip()] = str(url).strip()
    notes = {}
    if "Ref Matching Notes" in wb.sheetnames:
        for r in wb["Ref Matching Notes"].iter_rows(min_row=2, values_only=True):
            if r[4] and r[10]:
                notes[(str(r[4]).strip(), str(r[3]).strip())] = str(r[10])
    return ws, links, notes


def parse(ws, links, notes):
    groups, cur, sub = [], None, None
    missing, seen_sub = [], {}
    for r in range(5, ws.max_row + 1):
        a, b = ws.cell(r, 1).value, ws.cell(r, 2).value
        if a is None and b is None:
            continue
        if isinstance(a, str) and a.strip() and b is None:
            name = " ".join(a.split())
            if name.upper() in ("TOTAL",):
                break
            if "/" in name:  # top-level discipline heading
                cur = {"g": name.title().replace(" Shop Drawings", "").replace("Id", "ID").replace("Mep", "MEP"), "subs": []}
                groups.append(cur)
            else:
                if cur is None:
                    cur = {"g": "Drawings", "subs": []}
                    groups.append(cur)
                sub = {"s": nice(name), "items": []}
                cur["subs"].append(sub)
            continue
        if isinstance(a, (int, float)) and b:
            if sub is None:
                sub = {"s": "General", "items": []}
                cur["subs"].append(sub)
            cells = []
            for i, c in enumerate(range(4, 8)):
                cell = ws.cell(r, c)
                v = "" if cell.value is None else str(cell.value).strip()
                rgb = fill_rgb(cell)
                m = LINK_RE.match(v)
                if m:
                    ref, url = m.group(2), m.group(1)
                elif REF_RE.match(v):
                    ref, url = v, links.get(v, "")
                    if not url:
                        missing.append({"row": r, "type": TYPES[i], "ref": v})
                else:
                    ref = url = ""
                if ref and url:
                    chk = notes.get((ref, ["4BR Type 01", "4BR Type 02", "5BR Type 03", "5BR Type 04"][i]), "check this ref") if rgb.endswith("FFC000") else ""
                    cells.append({"ref": ref.replace(PREFIX, ""), "url": url, "chk": chk})
                elif ref:
                    cells.append({"txt": ref.replace(PREFIX, "") + " (no link)", "nf": True})
                else:
                    if re.match(r"^\d{4}-\d{2}-\d{2}", v):
                        v = datetime.date.fromisoformat(v[:10]).strftime("%d %b %Y")
                    cells.append({"txt": v, "nf": v.upper() == "NOT IN REGISTER"})
            sub["items"].append({"n": int(a), "d": " ".join(str(b).split()), "c": cells})
    # page-only fix: a repeated sub-section name (e.g. second ELEVATIONS block holding porcelain cladding)
    for g in groups:
        for s in g["subs"]:
            seen_sub[s["s"]] = seen_sub.get(s["s"], 0) + 1
            if seen_sub[s["s"]] > 1 and s["items"]:
                s["s"] = s["items"][0]["d"].strip().title()
        g["subs"] = [s for s in g["subs"] if s["items"]]
    return groups, missing


def encrypt(data, password):
    plain = ("V15OK" + json.dumps(data, separators=(",", ":"), ensure_ascii=False)).encode()
    salt, iv = os.urandom(16), os.urandom(16)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(password.encode())
    p = padding.PKCS7(128).padder()
    pt = p.update(plain) + p.finalize()
    e = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = e.update(pt) + e.finalize()
    b = lambda x: base64.b64encode(x).decode()
    return {"s": b(salt), "i": b(iv), "n": ITERATIONS, "c": b(ct)}


def decrypt_page(path, password):
    t = open(path, encoding="utf-8").read()
    m = re.search(r"const ENC = (\{.*?\});", t, re.S)
    enc = json.loads(m.group(1))
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(enc["s"]), iterations=enc["n"]).derive(password.encode())
    d = Cipher(algorithms.AES(key), modes.CBC(base64.b64decode(enc["i"]))).decryptor()
    pt = d.update(base64.b64decode(enc["c"])) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    txt = (u.update(pt) + u.finalize()).decode()
    if not txt.startswith("V15OK"):
        raise SystemExit("Old page did not decrypt with this password")
    return json.loads(txt[5:])


def flatten(data):
    out = {}
    for g in data:
        for s in g["subs"]:
            for it in s["items"]:
                for i, c in enumerate(it["c"]):
                    out[(it["d"], TYPES[i])] = c.get("ref") and (c["ref"], c["url"]) or (c.get("txt", ""), "")
    return out


def diff(old, new):
    o, n = flatten(old), flatten(new)
    changes = []
    for k in sorted(set(o) | set(n)):
        if o.get(k) != n.get(k):
            changes.append({"drawing": k[0], "type": k[1],
                            "old": (o.get(k) or ("", ""))[0], "new": (n.get(k) or ("", ""))[0],
                            "link_changed": (o.get(k) or ("", ""))[1] != (n.get(k) or ("", ""))[1]})
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--out", default="index.html")
    ap.add_argument("--old", help="currently deployed index.html, to report what changed")
    ap.add_argument("--updated", default=datetime.date.today().strftime("%d %b %Y").lstrip("0"))
    ap.add_argument("--report", help="write a JSON report here")
    ap.add_argument("--links", help="JSON file {ref: drive_folder_url} for refs not linked in the Excel (looked up in Drive by folder name)")
    a = ap.parse_args()
    pw = os.environ.get("V15_PASSWORD")
    if not pw:
        sys.exit("Set V15_PASSWORD")
    ws, links, notes = load(a.xlsx)
    if a.links:
        extra = json.load(open(a.links))
        links.update({(k if k.startswith(PREFIX) else PREFIX + k): v for k, v in extra.items()})
    data, missing = parse(ws, links, notes)
    items = sum(len(s["items"]) for g in data for s in g["subs"])
    nlinks = sum(1 for g in data for s in g["subs"] for it in s["items"] for c in it["c"] if c.get("url"))
    report = {"items": items, "links": nlinks, "missing_links": missing,
              "sections": [s["s"] for g in data for s in g["subs"]]}
    if a.old and os.path.exists(a.old):
        report["changes"] = diff(decrypt_page(a.old, pw), data)
    old_upd = "null"
    old_sta = "null"
    if a.old and os.path.exists(a.old):
        m = re.search(r"const UPD = (\{.*?\}|null);", open(a.old, encoding="utf-8").read(), re.S)
        old_upd = m.group(1) if m else "null"
        m2 = re.search(r"const STA = (\{.*?\}|null);", open(a.old, encoding="utf-8").read(), re.S)
        old_sta = m2.group(1) if m2 else "null"
    tpl = open(os.path.join(HERE, "page_template.html"), encoding="utf-8").read()
    html = tpl.replace("__ENC__", json.dumps(encrypt(data, pw))).replace("__UPDATED__", a.updated).replace("__UPD__", old_upd).replace("__STA__", old_sta)
    assert "drive.google" not in html
    open(a.out, "w", encoding="utf-8").write(html)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in report.items() if k != "sections"}, indent=1, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main()
