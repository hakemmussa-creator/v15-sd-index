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
   "status": {"MAS-ARC-099": ["U", 0], ...}}  # only new/changed keys; merged into the stored map
Missing keys = nothing to do for that part. SD rows new to index.html are NOT handled here (they need the
Excel); those still go through the normal build_page.py route.
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
    print("request", req.get("id"), "applied")


if __name__ == "__main__":
    main()
