#!/usr/bin/env python3
"""Build the private MAS / PQN submittal index page (submittals.html).

Usage:
  SUB_PASSWORD='...' python3 tools/build_submittals.py --csv mas.csv --csv pqn.csv \
      [--links links.json] [--old submittals.html] [--out submittals.html] [--updated "9 Oct 2026"] [--report r.json]

Inputs
  --csv    Unifier log exports (columns: Reference No, Revision No., Title, Discipline). Repeatable.
           If no --csv is given, the item list is taken from the --old page (decrypted), so links can be
           added later without the CSVs.
  --links  JSON {ref: drive_folder_url}. Merged over any links already in the --old page.

Data is grouped by the discipline code inside the reference number (ARC, STR, ID, MEC/HVAC/MEP, ELE),
one row per reference (highest revision wins for the title). Everything (titles and Drive links) lives
only inside the AES-encrypted blob; the password is never written to the page or the repo.
"""
import argparse, base64, csv, datetime, json, os, re, sys

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

REF_RE = re.compile(r"^GPD-V15-QTGC-(MAS|PQN)-([A-Z]+)-(\d+)$")
GROUPS = [  # (page heading, discipline codes)
    ("Architectural", ["ARC"]),
    ("Structural", ["STR"]),
    ("Interior Design", ["ID"]),
    ("Mechanical / Plumbing / HVAC", ["MEC", "HVAC", "MEP"]),
    ("Electrical", ["ELE"]),
]
ITERATIONS = 150000
HERE = os.path.dirname(os.path.abspath(__file__))


def rev_no(s):
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else -1


def read_csvs(paths):
    best = {}
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                ref = (r.get("Reference No") or "").strip()
                if not REF_RE.match(ref):
                    continue
                rv = rev_no(r.get("Revision No."))
                if ref not in best or rv > best[ref][0]:
                    best[ref] = (rv, " ".join((r.get("Title") or "").split()))
    return {ref: t for ref, (rv, t) in best.items()}


def encrypt(data, password):
    plain = ("V15OK" + json.dumps(data, separators=(",", ":"), ensure_ascii=False)).encode()
    salt, iv = os.urandom(16), os.urandom(16)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(password.encode())
    p = padding.PKCS7(128).padder()
    ct = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    pt = p.update(plain) + p.finalize()
    out = ct.update(pt) + ct.finalize()
    b = lambda x: base64.b64encode(x).decode()
    return {"s": b(salt), "i": b(iv), "n": ITERATIONS, "c": b(out)}


def decrypt_page(path, password):
    t = open(path, encoding="utf-8").read()
    enc = json.loads(re.search(r"const ENC = (\{.*?\});", t, re.S).group(1))
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(enc["s"]), iterations=enc["n"]).derive(password.encode())
    d = Cipher(algorithms.AES(key), modes.CBC(base64.b64decode(enc["i"]))).decryptor()
    pt = d.update(base64.b64decode(enc["c"])) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    txt = (u.update(pt) + u.finalize()).decode()
    if not txt.startswith("V15OK"):
        raise SystemExit("Old page did not decrypt with this password")
    return json.loads(txt[5:])


def flat(data):
    return {it["r"]: it for g in data for it in g["items"]}


def build(titles, links):
    code_group = {c: name for name, codes in GROUPS for c in codes}
    data = [{"g": name, "items": []} for name, _ in GROUPS]
    idx = {g["g"]: g for g in data}
    for ref, title in titles.items():
        typ, code, num = REF_RE.match(ref).groups()
        g = idx[code_group.get(code, GROUPS[0][0])] if code in code_group else None
        if g is None:
            g = idx.setdefault("Other", {"g": "Other", "items": []})
            if g not in data:
                data.append(g)
        g["items"].append({"r": ref, "t": title, "ty": typ, "u": links.get(ref, "")})
    for g in data:
        g["items"].sort(key=lambda it: (it["ty"], REF_RE.match(it["r"]).group(2), int(REF_RE.match(it["r"]).group(3))))
    return [g for g in data if g["items"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="append", default=[])
    ap.add_argument("--links")
    ap.add_argument("--old")
    ap.add_argument("--out", default="submittals.html")
    ap.add_argument("--updated", default=datetime.date.today().strftime("%d %b %Y").lstrip("0"))
    ap.add_argument("--report")
    a = ap.parse_args()
    pw = os.environ.get("SUB_PASSWORD")
    if not pw:
        sys.exit("Set SUB_PASSWORD")
    old = flat(decrypt_page(a.old, pw)) if a.old and os.path.exists(a.old) else {}
    titles = read_csvs(a.csv) if a.csv else {r: it["t"] for r, it in old.items()}
    links = {r: it["u"] for r, it in old.items() if it.get("u")}
    if a.links:
        links.update(json.load(open(a.links)))
    data = build(titles, links)
    items = [it for g in data for it in g["items"]]
    report = {
        "items": len(items),
        "MAS": sum(it["ty"] == "MAS" for it in items),
        "PQN": sum(it["ty"] == "PQN" for it in items),
        "links": sum(bool(it["u"]) for it in items),
        "missing_links": [it["r"] for it in items if not it["u"]],
        "added": sorted(set(titles) - set(old)) if old else [],
        "removed": sorted(set(old) - set(titles)) if old else [],
        "groups": {g["g"]: len(g["items"]) for g in data},
    }
    old_upd = "null"
    old_sta = "null"
    if a.old and os.path.exists(a.old):
        m = re.search(r"const UPD = (\{.*?\}|null);", open(a.old, encoding="utf-8").read(), re.S)
        old_upd = m.group(1) if m else "null"
        m2 = re.search(r"const STA = (\{.*?\}|null);", open(a.old, encoding="utf-8").read(), re.S)
        old_sta = m2.group(1) if m2 else "null"
    tpl = open(os.path.join(HERE, "submittals_template.html"), encoding="utf-8").read()
    html = tpl.replace("__ENC__", json.dumps(encrypt(data, pw))).replace("__UPDATED__", a.updated).replace("__UPD__", old_upd).replace("__STA__", old_sta)
    assert "drive.google" not in html and "MATERIAL SUBMITTAL" not in html
    open(a.out, "w", encoding="utf-8").write(html)
    if a.report:
        json.dump(report, open(a.report, "w"), indent=1)
    s = dict(report)
    s["missing_links"] = len(s["missing_links"])
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
