#!/usr/bin/env python3
"""Apply a small publish request to the pages (run by .github/workflows/publish.yml).

The daily Claude run cannot push the large page files, so it commits only publish/request.json
through the GitHub connector; this script rebuilds the pages from it on GitHub Actions.

Env: SD_PASSWORD (index.html), SUB_PASSWORD (submittals.html) – repository secrets.
publish/request.json:
  {"id": "2026-10-13",                        # any label, used in the commit message
   "sub_add": [{"ref": "GPD-V15-QTGC-MAS-ARC-099", "rev": "Rev.00", "title": "...", "url": "drive folder url"}],
   "updates_index": {d,label,items} | null,   # same format as tools/add_updates.py
   "updates_sub":   {d,label,items} | null,
   "status": {"MAS-ARC-099": ["U", 0], ...},  # only new/changed keys; merged into the stored map
   "patch": [{"file": "index.html", "old": "...", "new": "..."}],  # plain-text code fix; old must match exactly once
   "sd_data": {"enc": {s,i,n,c}, "updated": "22 Oct 2026"}}   # full SD index rows (from the Google Sheet)
Missing keys = nothing to do for that part.
sd_data: the whole index.html row data (the ENC structure build_page.py makes), zlib-compressed, base64'd as
{"z": "..."} and encrypted with the SD page password (tools/make_sd_data.py builds it from the sheet export).
It replaces the page's ENC block, so new SD refs / moved refs / new rows publish without uploading index.html.
"""
import csv, json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from add_updates import dec
import build_submittals as bs

IDX, SUB = os.path.join(ROOT, "index.html"), os.path.join(ROOT, "submittals.html")


def run(args, pw_env):
    env = dict(os.environ, **pw_env)
    r = subprocess.run([sys.executable] + args, cwd=ROOT, env=env, capture_output=True, text=True)
    print(r.stdout.strip()[-1500:])
    if r.returncode:
        print(r.stderr[-3000:]); sys.exit(r.returncode)


def main():
    req_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "publish", "request.json")
    req = json.load(open(req_path, encoding="utf-8"))
    sdpw, subpw = os.environ["SD_PASSWORD"], os.environ["SUB_PASSWORD"]
    tmp = tempfile.mkdtemp()

    if req.get("sd_data"):
        import base64, zlib
        inner = dec(req["sd_data"]["enc"], sdpw)
        data = json.loads(zlib.decompress(base64.b64decode(inner["z"])).decode("utf-8"))
        if not isinstance(data, list) or not data or "subs" not in data[0]:
            sys.exit("sd_data: unexpected structure")
        n_items = sum(len(s["items"]) for g in data for s in g["subs"])
        t = open(IDX, encoding="utf-8").read()
        m = re.search(r"const ENC = (\{.*?\});", t, re.S)
        old_items = sum(len(s["items"]) for g in dec(json.loads(m.group(1)), sdpw) for s in g["subs"])
        if n_items < old_items * 0.9:
            sys.exit("sd_data: item count dropped %d -> %d, refusing" % (old_items, n_items))
        t = t[:m.start(1)] + json.dumps(bs.encrypt(data, sdpw)) + t[m.end(1):]
        if req["sd_data"].get("updated"):
            t = re.sub(r"(· Updated )[^.<]+(\.<br>)", lambda x: x.group(1) + req["sd_data"]["updated"] + x.group(2), t, count=1)
        open(IDX, "w", encoding="utf-8").write(t)
        print("sd_data: index rows replaced (%d -> %d items)" % (old_items, n_items))

    if req.get("sub_add"):
        old = bs.decrypt_page(SUB, subpw)
        rows = [(it["r"], "", it["t"]) for g in old for it in g["items"]]
        have = {r for r, _, _ in rows}
        links = {}
        for a in req["sub_add"]:
            if a["ref"] not in have:
                rows.append((a["ref"], a.get("rev", ""), a["title"]))
            if a.get("url"):
                links[a["ref"]] = a["url"]
        c, l, rep = os.path.join(tmp, "sub.csv"), os.path.join(tmp, "links.json"), os.path.join(tmp, "rep.json")
        with open(c, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["Reference No", "Revision No.", "Title"]); w.writerows(rows)
        json.dump(links, open(l, "w"))
        run(["tools/build_submittals.py", "--csv", c, "--old", "submittals.html", "--links", l,
             "--out", "submittals.html", "--report", rep], {"SUB_PASSWORD": subpw})
        r = json.load(open(rep))
        if r.get("removed") or r.get("missing_links"):
            sys.exit("build_submittals report not clean: removed=%s missing_links=%s" % (r.get("removed"), r.get("missing_links")))
        print("added:", r.get("added"))

    for key, page, pw in (("updates_index", "index.html", sdpw), ("updates_sub", "submittals.html", subpw)):
        if req.get(key):
            p = os.path.join(tmp, key + ".json"); json.dump(req[key], open(p, "w", encoding="utf-8"), ensure_ascii=False)
            run(["tools/add_updates.py", page, p], {"PAGE_PASSWORD": pw})

    if req.get("status"):
        t = open(IDX, encoding="utf-8").read()
        m = re.search(r"const STA = (\{.*?\}|null);", t, re.S)
        sta = dec(json.loads(m.group(1)), sdpw) if m and m.group(1) != "null" else {}
        sta.update(req["status"])
        p = os.path.join(tmp, "status.json"); json.dump(sta, open(p, "w"))
        run(["tools/set_status.py", "index.html", p], {"PAGE_PASSWORD": sdpw})
        run(["tools/set_status.py", "submittals.html", p], {"PAGE_PASSWORD": subpw})
    for p in req.get("patch") or []:
        if p["file"] not in ("index.html", "submittals.html", "ifc.html"):
            sys.exit("patch: file not allowed: %s" % p["file"])
        f = os.path.join(ROOT, p["file"]); t = open(f, encoding="utf-8").read()
        n = t.count(p["old"])
        if n != 1:
            sys.exit("patch: old text found %d times in %s" % (n, p["file"]))
        open(f, "w", encoding="utf-8").write(t.replace(p["old"], p["new"]))
        print("patched", p["file"])

    print("request", req.get("id"), "applied")


if __name__ == "__main__":
    main()
