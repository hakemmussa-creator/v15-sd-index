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
   "sd_data": {"enc": {s,i,n,c}, "updated": "22 Oct 2026"},   # full SD index rows (from the Google Sheet)
   "sd_sheet": true,                          # read the SD Index Google Sheet directly (preferred, keeps requests small)
   "updated": "22 Oct 2026"}                  # optional label for the index 'Updated' line
Missing keys = nothing to do for that part.
sd_sheet: the sheet id is stored encrypted (SD page password) in publish/sd_sheet.json; the sheet is link-readable,
so the Action exports it as .xlsx, parses it like build_page.py and replaces the index rows only when they changed
(refuses a >10 % item drop or refs without a Drive link).
updates_*: items are MERGED into an existing entry of the same day (same r+k+rev replaced), unless "updates_replace": true.
Writes publish/result.json (counts only, no refs or links) so the run can be checked from the repo.
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


def today_label():
    import datetime
    d = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=4)  # Asia/Dubai
    return "%d %s" % (d.day, d.strftime("%b %Y"))


def merged_day(page, new, pw, replace=False):
    t = open(page, encoding="utf-8").read()
    m = re.search(r"const UPD = (\{.*?\}|null);", t, re.S)
    days = [] if (not m or m.group(1) == "null") else dec(json.loads(m.group(1)), pw)
    old = next((d for d in days if d["d"] == new["d"]), None)
    if not old or replace:
        return new
    k = lambda it: (it.get("r"), it.get("k"), it.get("rev"))
    seen = {k(it) for it in new["items"]}
    return dict(new, items=new["items"] + [it for it in old["items"] if k(it) not in seen])


def replace_index_rows(data, sdpw, updated):
    n_items = sum(len(s["items"]) for g in data for s in g["subs"])
    t = open(IDX, encoding="utf-8").read()
    m = re.search(r"const ENC = (\{.*?\});", t, re.S)
    old = dec(json.loads(m.group(1)), sdpw)
    old_items = sum(len(s["items"]) for g in old for s in g["subs"])
    if n_items < old_items * 0.9:
        return old, "refused: item count %d -> %d" % (old_items, n_items)
    t = t[:m.start(1)] + json.dumps(bs.encrypt(data, sdpw)) + t[m.end(1):]
    t = re.sub(r"(· Updated )[^.<]+(\.<br>)", lambda x: x.group(1) + updated + x.group(2), t, count=1)
    open(IDX, "w", encoding="utf-8").write(t)
    return old, "%d -> %d items" % (old_items, n_items)


def sd_from_sheet(sdpw, tmp, updated):
    import importlib, subprocess, urllib.request
    try:
        importlib.import_module("openpyxl")
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True)
    import build_page as bp
    sid = dec(json.load(open(os.path.join(ROOT, "publish", "sd_sheet.json"))), sdpw)["id"]
    x = os.path.join(tmp, "sd.xlsx")
    urllib.request.urlretrieve("https://docs.google.com/spreadsheets/d/%s/export?format=xlsx" % sid, x)
    ws, links, notes = bp.load(x)
    data, missing = bp.parse(ws, links, notes)
    if missing:
        return "skipped: %d refs without a Drive link" % len(missing)
    t = open(IDX, encoding="utf-8").read()
    old = dec(json.loads(re.search(r"const ENC = (\{.*?\});", t, re.S).group(1)), sdpw)
    ch = bp.diff(old, data)
    if not ch:
        return "no change"
    _, msg = replace_index_rows(data, sdpw, updated)
    return "%d cells changed (%s)" % (len(ch), msg) if not msg.startswith("refused") else msg


def main():
    req_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "publish", "request.json")
    req = json.load(open(req_path, encoding="utf-8"))
    sdpw, subpw = os.environ["SD_PASSWORD"], os.environ["SUB_PASSWORD"]
    tmp = tempfile.mkdtemp()
    result = {"id": req.get("id")}
    updated = req.get("updated") or (req.get("sd_data") or {}).get("updated") or today_label()

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
        result["sd"] = "sd_data %d -> %d items" % (old_items, n_items)

    if req.get("sd_sheet") and not req.get("sd_data"):
        result["sd"] = sd_from_sheet(sdpw, tmp, updated)
        print("sd_sheet:", result["sd"])

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
            day = merged_day(os.path.join(ROOT, page), req[key], pw, req.get("updates_replace"))
            result[key] = len(day["items"])
            p = os.path.join(tmp, key + ".json"); json.dump(day, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            run(["tools/add_updates.py", page, p], {"PAGE_PASSWORD": pw})

    if req.get("status"):
        t = open(IDX, encoding="utf-8").read()
        m = re.search(r"const STA = (\{.*?\}|null);", t, re.S)
        sta = dec(json.loads(m.group(1)), sdpw) if m and m.group(1) != "null" else {}
        sta.update(req["status"])
        result["status"] = len(req["status"])
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

    if req.get("sub_add"):
        result["sub_add"] = len(req["sub_add"])
    result["ok"] = True
    rp = os.path.join(ROOT, "publish", "result.json")
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    json.dump(result, open(rp, "w"), indent=1)
    if os.environ.get("GITHUB_ACTIONS"):
        subprocess.run(["git", "add", "publish/result.json"], cwd=ROOT)
    print("request", req.get("id"), "applied", json.dumps(result))


if __name__ == "__main__":
    main()
