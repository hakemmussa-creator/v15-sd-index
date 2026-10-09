#!/usr/bin/env python3
"""Add a day's entries to the encrypted Updates panel of a page (index.html or submittals.html).

Usage:
  PAGE_PASSWORD='...' python3 tools/add_updates.py index.html updates_day.json

updates_day.json: {"d": "2026-10-09", "label": "9 Oct 2026", "items": [
   {"r": "SD-ARC-083", "rev": "Rev.00", "t": "title", "k": "reply|new|add", "n": "optional note",
    "f": ["file names to review"], "u": "drive folder url"}]}
An entry with the same "d" replaces the earlier one. Newest day is listed first.
The page's password must be the one the page is already locked with.
"""
import base64, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_submittals import encrypt
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def dec(enc, pw):
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(enc["s"]), iterations=enc["n"]).derive(pw.encode())
    d = Cipher(algorithms.AES(key), modes.CBC(base64.b64decode(enc["i"]))).decryptor()
    pt = d.update(base64.b64decode(enc["c"])) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    txt = (u.update(pt) + u.finalize()).decode()
    if not txt.startswith("V15OK"):
        raise SystemExit("wrong password for this page")
    return json.loads(txt[5:])


def main():
    page, new = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
    pw = os.environ.get("PAGE_PASSWORD") or sys.exit("Set PAGE_PASSWORD")
    t = open(page, encoding="utf-8").read()
    # password check against the main data blob
    dec(json.loads(re.search(r"const ENC = (\{.*?\});", t, re.S).group(1)), pw)
    m = re.search(r"const UPD = (\{.*?\}|null);", t, re.S)
    days = [] if m.group(1) == "null" else dec(json.loads(m.group(1)), pw)
    days = [d for d in days if d["d"] != new["d"]] + [new]
    days.sort(key=lambda d: d["d"], reverse=True)
    t = t[:m.start(1)] + json.dumps(encrypt(days, pw)) + t[m.end(1):]
    assert "drive.google" not in t
    open(page, "w", encoding="utf-8").write(t)
    print(page, ":", len(days), "day(s),", sum(len(d["items"]) for d in days), "items")


if __name__ == "__main__":
    main()
