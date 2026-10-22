#!/usr/bin/env python3
"""Daily V15 routine helper (runs in Claude's workspace on a clone of this repo).

  SD_PASSWORD=.. SUB_PASSWORD=.. python3 tools/daily.py build report.json [--links links.json] [--out request.json]
      report.json = output of V15.check() in the Unifier tab (tools/unifier_lib.js).
      links.json  = {"SD-STR-123": "https://drive.google.com/drive/folders/<id>"} for folders created today.
      Writes the publish request (status, Updates entries with folder links, new MAS/PQN/RFI refs, sd_sheet)
      and prints a short summary. Folder links come from the decrypted pages; missing ones are listed.
  python3 tools/daily.py tracker report.json rows.json [--links links.json]
      rows.json = Sheets get_values result of Tracker!A6:C1000 (saved to a file).
      Prints {"requests": [...]} for ONE update_spreadsheet call on the V15 Rejected Tracker
      (row updates, new rows inserted inside their log group, hide/unhide, date line).
  SD_PASSWORD=.. SUB_PASSWORD=.. python3 tools/daily.py verify request.json [--wait 300]
      Waits for the GitHub Action commit, then checks origin/main: request applied and removed, statuses,
      Updates items and new refs present. Prints one line: OK ... or FAIL ...
"""
import argparse, datetime, json, os, re, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
TRACKER_ID, SUMMARY_ID = 573721541, 360940572
key = lambda r: re.sub(r"^GPD-V1?5?-QTGC-", "", r)


def now_dxb():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=4)


def label(d):
    return "%d %s" % (d.day, d.strftime("%b %Y"))


def dec_block(text, name, pw):
    from add_updates import dec
    m = re.search(r"const %s = (\{.*?\}|null);" % name, text, re.S)
    return None if (not m or m.group(1) == "null") else dec(json.loads(m.group(1)), pw)


def url_map(root_text=None):
    """{key: folder url} from both pages (SD keys as 'SD-STR-001')."""
    sdpw, subpw = os.environ["SD_PASSWORD"], os.environ["SUB_PASSWORD"]
    it = root_text or {}
    idx = it.get("index.html") or open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    sub = it.get("submittals.html") or open(os.path.join(ROOT, "submittals.html"), encoding="utf-8").read()
    m = {}
    for g in dec_block(idx, "ENC", sdpw):
        for s in g["subs"]:
            for row in s["items"]:
                for c in row["c"]:
                    if c.get("ref") and c.get("url"):
                        m["SD-" + c["ref"]] = c["url"]
    for g in dec_block(sub, "ENC", subpw):
        for row in g["items"]:
            if row.get("u"):
                m[key(row["r"])] = row["u"]
    return m


def load_links(p):
    return {key(k): v for k, v in (json.load(open(p)) if p else {}).items()}


def cmd_build(a):
    rep = json.load(open(a.report))
    urls = url_map(); urls.update(load_links(a.links))
    d = now_dxb(); ds = d.strftime("%Y-%m-%d")
    missing = []
    def item(e):
        u = urls.get(e["r"], "")
        if not u: missing.append(e["r"])
        return {"r": e["r"], "rev": e["rev"], "t": e["t"], "k": e["k"], "n": e["n"], "f": e.get("f", []), "u": u}
    ev = rep.get("ev", [])
    ui = [item(e) for e in ev if e["log"] == "SD"]
    us = [item(e) for e in ev if e["log"] != "SD"]
    req = {"id": d.strftime("%Y-%m-%d-%H%M"), "sd_sheet": True, "updated": label(d)}
    if ui: req["updates_index"] = {"d": ds, "label": label(d), "items": ui}
    if us: req["updates_sub"] = {"d": ds, "label": label(d), "items": us}
    if rep.get("st"): req["status"] = rep["st"]
    adds = []
    for n in rep.get("newSub", []):
        u = urls.get(key(n["ref"]), "")
        if not u: missing.append(key(n["ref"]))
        adds.append({"ref": n["ref"], "rev": n["rev"], "title": n["title"], "url": u})
    if adds: req["sub_add"] = adds
    out = a.out or os.path.join(tempfile.gettempdir(), "request.json")
    json.dump(req, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("request:", out, os.path.getsize(out), "bytes | updates SD %d / sub %d | status %d | sub_add %d | new SD refs %s%s" % (
        len(ui), len(us), len(rep.get("st", {})), len(adds), [n["r"] for n in rep.get("newSD", [])] or "none",
        (" | MISSING LINKS: %s" % sorted(set(missing))) if missing else ""))


def serial(s):
    y, m, dd = map(int, s[:10].split("-"))
    return (datetime.date(y, m, dd) - datetime.date(1899, 12, 30)).days


def cell(v):
    if isinstance(v, (int, float)): return {"userEnteredValue": {"numberValue": v}}
    if isinstance(v, str) and v.startswith("="): return {"userEnteredValue": {"formulaValue": v}}
    return {"userEnteredValue": {"stringValue": v or ""}}


def cmd_tracker(a):
    rep = json.load(open(a.report)); vals = json.load(open(a.rows)).get("values", [])
    rows = []  # [row number, No, log, ref]
    for i, r in enumerate(vals):
        if len(r) >= 3 and r[2]:
            rows.append([6 + i, r[0], r[1], r[2].strip()])
    urls = None
    reqs, writes, vis = [], [], {}
    today = serial(now_dxb().strftime("%Y-%m-%d"))
    for op, d in rep.get("trk", []):
        where = {r[3]: r[0] for r in rows}
        rr = where.get(d["ref"])
        if op == "add" and rr:
            op = "upd"
        if op == "upd" and not rr:
            op = "add"
        if op == "add":
            if urls is None:
                urls = url_map(); urls.update(load_links(a.links))
            grp = [r for r in rows if r[2] == d["log"]]
            last = max(r[0] for r in grp) if grp else (max(r[0] for r in rows) + 1 if rows else 6)
            reqs.append({"insertDimension": {"range": {"sheetId": TRACKER_ID, "dimension": "ROWS", "startIndex": last - 1, "endIndex": last}, "inheritFromBefore": True}})
            for r in rows:
                if r[0] >= last: r[0] += 1
            for w in writes:
                if w[0] >= last: w[0] += 1
            vis = {(k + 1 if k >= last else k): v for k, v in vis.items()}
            no = max([int(r[1]) for r in rows if str(r[1]).isdigit()] or [0]) + 1
            rows.append([last, str(no), d["log"], d["ref"]])
            u = urls.get(key(d["ref"]), "")
            link = '=HYPERLINK("%s","Open folder")' % u if u else ""
            writes.append([last, 0, [no, d["log"], d["ref"], d["disc"], d["title"], d["rev"], d["code"], d["status"], d["by"],
                                     serial(d["sub"]) if d.get("sub") else "", '=IF(J%d="","",TODAY()-J%d)' % (last, last), link, "", "", "", "", today]])
            vis[last] = False
        elif op == "upd":
            writes.append([rr, 5, [d["rev"], d["code"], d["status"], d["by"], serial(d["sub"]) if d.get("sub") else ""]]); vis[rr] = False
        elif op in ("rs", "closed") and rr:
            writes.append([rr, 7, [d["status"]]]); vis[rr] = (op == "closed")
    if not reqs and not writes:
        print(json.dumps({"requests": []})); return
    for r, c0, v in writes:
        reqs.append({"updateCells": {"start": {"sheetId": TRACKER_ID, "rowIndex": r - 1, "columnIndex": c0}, "rows": [{"values": [cell(x) for x in v]}], "fields": "userEnteredValue"}})
    for r, hide in sorted(vis.items()):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": TRACKER_ID, "dimension": "ROWS", "startIndex": r - 1, "endIndex": r}, "properties": {"hiddenByUser": hide}, "fields": "hiddenByUser"}})
    lab = label(now_dxb())
    reqs.append({"updateCells": {"start": {"sheetId": TRACKER_ID, "rowIndex": 1, "columnIndex": 0}, "rows": [{"values": [cell(
        "Source: Unifier logs, read %s. Latest revision per reference coded C / D / F, plus RFIs coded C or awaiting response. Rows marked TERM and closed rows are kept but hidden (unhide rows to see them)." % lab)]}], "fields": "userEnteredValue"}})
    reqs.append({"updateCells": {"start": {"sheetId": SUMMARY_ID, "rowIndex": 0, "columnIndex": 0}, "rows": [{"values": [cell("Summary by log and action – " + lab)]}], "fields": "userEnteredValue"}})
    print(json.dumps({"requests": reqs}, ensure_ascii=False, separators=(",", ":")))


def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True)


def cmd_verify(a):
    req = json.load(open(a.request)); rid = req["id"]
    t_end = time.time() + a.wait
    while True:
        git("fetch", "-q", "origin")
        log = git("log", "origin/main", "-5", "--format=%s").stdout
        if ("Publish %s (applied" % rid) in log or time.time() > t_end:
            break
        time.sleep(15)
    if ("Publish %s (applied" % rid) not in log:
        print("FAIL: Action did not apply request %s within %ss. Last commits: %s" % (rid, a.wait, log.strip().splitlines()[:2])); return
    probs = []
    if git("cat-file", "-e", "origin/main:publish/request.json").returncode == 0:
        probs.append("request.json still in repo")
    res = git("show", "origin/main:publish/result.json").stdout
    pages = {p: git("show", "origin/main:" + p).stdout for p in ("index.html", "submittals.html")}
    sdpw, subpw = os.environ["SD_PASSWORD"], os.environ["SUB_PASSWORD"]
    sta_i, sta_s = dec_block(pages["index.html"], "STA", sdpw) or {}, dec_block(pages["submittals.html"], "STA", subpw) or {}
    for k, v in (req.get("status") or {}).items():
        if sta_i.get(k) != v or sta_s.get(k) != v:
            probs.append("status " + k)
    for kk, p, pw in (("updates_index", "index.html", sdpw), ("updates_sub", "submittals.html", subpw)):
        if req.get(kk):
            days = dec_block(pages[p], "UPD", pw) or []
            dd = next((x for x in days if x["d"] == req[kk]["d"]), {"items": []})
            have = {(i["r"], i["k"], i["rev"]) for i in dd["items"]}
            for i in req[kk]["items"]:
                if (i["r"], i["k"], i["rev"]) not in have: probs.append("update " + i["r"])
    if req.get("sub_add"):
        refs = {row["r"] for g in dec_block(pages["submittals.html"], "ENC", subpw) for row in g["items"]}
        for s in req["sub_add"]:
            if s["ref"] not in refs: probs.append("sub_add " + key(s["ref"]))
    git("merge", "-q", "--ff-only", "origin/main")
    r = json.loads(res) if res.strip() else {}
    print(("OK " if not probs else "FAIL ") + "publish %s | result %s%s" % (rid, json.dumps(r), (" | problems: " + ", ".join(probs)) if probs else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build"); b.add_argument("report"); b.add_argument("--links"); b.add_argument("--out")
    t = sp.add_parser("tracker"); t.add_argument("report"); t.add_argument("rows"); t.add_argument("--links")
    v = sp.add_parser("verify"); v.add_argument("request"); v.add_argument("--wait", type=int, default=300)
    a = ap.parse_args()
    {"build": cmd_build, "tracker": cmd_tracker, "verify": cmd_verify}[a.cmd](a)
