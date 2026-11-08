#!/usr/bin/env python3
"""V15 offline index - one self-contained HTML that opens files from the local Drive mirror (no password, no internet).

Normal use (on Mohammed's PC shell, after the daily publish) - fetches the live pages from GitHub, decrypts, scans the
mirror and writes the page:
    SD_PASSWORD=.. SUB_PASSWORD=.. python3 build_offline.py update --mirror "<mirror path>" \
        --win-root "D:/mirrored drive" --out "<mirror path>/V15 Offline Index/V15 Offline Index.html"
Split use: `export --repo . --out data.json` (decrypt local repo pages) then `build data.json --mirror .. --out ..`.
Every link is file:///D:/mirrored drive/... The data and the page hold Drive links - never commit them to the public repo.
"""
import argparse, datetime, json, os, re
from collections import defaultdict

P = "GPD-V15-QTGC-"


# ---------------------------------------------------------------- export
RAW = "https://raw.githubusercontent.com/hakemmussa-creator/v15-sd-index/main/"


def _dec(enc, pw):
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(enc["s"]),
                     iterations=enc["n"]).derive(pw.encode())
    d = Cipher(algorithms.AES(key), modes.CBC(base64.b64decode(enc["i"]))).decryptor()
    raw = d.update(base64.b64decode(enc["c"])) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    txt = (u.update(raw) + u.finalize()).decode("utf-8")
    return json.loads(txt[5:] if txt.startswith("V15OK") else txt)


def page_data(texts):
    """texts: {"index.html": str, "submittals.html": str, "ifc.html": str} -> combined data dict."""
    pw_sd, pw_sub = os.environ["SD_PASSWORD"], os.environ["SUB_PASSWORD"]
    pw_ifc = os.environ.get("IFC_PASSWORD", pw_sd)

    def blocks(t, pw):
        o = {}
        for k in ("ENC", "UPD", "STA"):
            m = re.search(r"const %s = (\{.*?\}|null);" % k, t, re.S)
            if m and m.group(1) != "null":
                o[k] = _dec(json.loads(m.group(1)), pw)
        return o
    sd, sub = blocks(texts["index.html"], pw_sd), blocks(texts["submittals.html"], pw_sub)
    ifc = blocks(texts["ifc.html"], pw_ifc)
    sta = dict(sd.get("STA") or {})
    sta.update(sub.get("STA") or {})
    return {"exported": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "sd": sd["ENC"], "sub": sub["ENC"], "ifc": ifc["ENC"], "sta": sta,
            "upd": {"sd": sd.get("UPD") or [], "sub": sub.get("UPD") or []}}


def export(args):
    texts = {f: open(os.path.join(args.repo, f), encoding="utf-8").read() for f in ("index.html", "submittals.html", "ifc.html")}
    json.dump(page_data(texts), open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print("exported", args.out, os.path.getsize(args.out), "bytes")


def fetch_live():
    import time, urllib.request
    out = {}
    for f in ("index.html", "submittals.html", "ifc.html"):
        req = urllib.request.Request(RAW + f + "?nc=%d" % time.time(), headers={"Cache-Control": "no-cache", "User-Agent": "v15-offline"})
        out[f] = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    return out


# ---------------------------------------------------------------- build
REF_DIR = re.compile(r"^GPD-V1\d?-QTGC-(SD|MAS|PQN|RFI)-[A-Z]+-\d+", re.I)
SKIP_TOP = {"IFC", "executed", "V15-KB", "old", "Job Search – Abu Dhabi", "V15 Offline Index", "Claude"}
REV = re.compile(r"rev[\s.\-_]*(\d+)", re.I)
RESP = re.compile(r"respon|code[\s\-_]*[A-F]\b|[\s\-]+[A-F]\s*$", re.I)


def norm(r):
    r = r.strip().upper()
    return r[len(P):] if r.startswith(P) else r


def file_info(rel, size):
    name = rel.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    m = REV.search(stem)
    return {"p": rel, "n": name, "e": ext, "s": size,
            "r": int(m.group(1)) if m else -1, "x": 1 if RESP.search(stem) else 0}


def scan(mirror):
    folders = {}           # normalised ref -> {"d": rel dir, "f": [files]}
    ifc = defaultdict(list)  # (name lower) -> [(rel, size)]
    for top in sorted(os.listdir(mirror)):
        tp = os.path.join(mirror, top)
        if not os.path.isdir(tp) or top.startswith("."):
            continue
        if top == "IFC":
            for dp, dn, fn in os.walk(tp):
                for f in fn:
                    if f == "desktop.ini":
                        continue
                    full = os.path.join(dp, f)
                    rel = os.path.relpath(full, mirror).replace(os.sep, "/")
                    try:
                        ifc[f.lower()].append((rel, os.path.getsize(full)))
                    except OSError:
                        pass
            continue
        if top in SKIP_TOP:
            continue
        for dp, dn, fn in os.walk(tp):
            base = os.path.basename(dp)
            if not REF_DIR.match(base):
                continue
            dn[:] = []  # files sit directly in (or under) the ref folder
            files = []
            for sdp, sdn, sfn in os.walk(dp):
                for f in sfn:
                    if f == "desktop.ini" or f.endswith(".crswap"):
                        continue
                    full = os.path.join(sdp, f)
                    try:
                        files.append(file_info(os.path.relpath(full, mirror).replace(os.sep, "/"), os.path.getsize(full)))
                    except OSError:
                        pass
            files.sort(key=lambda x: (-x["r"], -x["x"], x["e"] != "pdf", x["n"]))
            key = norm(base)
            key = re.sub(r"^GPD-V1\d?-QTGC-", "", key)
            if key not in folders or len(files) > len(folders[key]["f"]):
                folders[key] = {"d": os.path.relpath(dp, mirror).replace(os.sep, "/"), "f": files}
    return folders, ifc


def primary(files):
    """The file a click should open: latest-rev response PDF, else latest-rev PDF, else latest file."""
    if not files:
        return None
    top = files[0]["r"]
    latest = [f for f in files if f["r"] == top]
    for cond in (lambda f: f["x"] and f["e"] == "pdf", lambda f: f["e"] == "pdf", lambda f: True):
        for f in latest:
            if cond(f):
                return f["p"]
    return files[0]["p"]


def build(args, data=None):
    data = data or json.load(open(args.data, encoding="utf-8"))
    folders, ifc_files = scan(args.mirror)
    used, missing = set(), []

    def ref_entry(ref):
        k = norm(ref)
        for cand in (k, re.sub(r"^GPD-V1\d?-QTGC-", "", k)):
            if cand in folders:
                used.add(cand)
                return cand
        missing.append(k)
        return None

    # SD rows
    for g in data["sd"]:
        for s in g["subs"]:
            for it in s["items"]:
                for c in it["c"]:
                    if c.get("ref"):
                        c["rk"] = ref_entry("SD-" + c["ref"]) or ""
    for g in data["sub"]:
        for it in g["items"]:
            it["rk"] = ref_entry(it["r"]) or ""
    for lst in data["upd"].values():
        for day in lst:
            for it in day.get("items", []):
                k = norm(it.get("r", ""))
                if k in folders:
                    used.add(k)
                    it["rk"] = k

    # IFC: match each Drive file to the mirror by file name (+ size when several)
    ifc_hit = ifc_miss = 0

    def walk(n):
        nonlocal ifc_hit, ifc_miss
        for f in n.get("f", []):
            for ext, v in f.get("x", {}).items():
                cands = ifc_files.get((f["t"] + "." + ext).lower(), [])
                if len(cands) > 1:
                    same = [c for c in cands if c[1] == v.get("s")]
                    cands = same or cands
                if cands:
                    v["p"] = cands[0][0]
                    ifc_hit += 1
                else:
                    ifc_miss += 1
                v.pop("u", None) if cands else None
        for d in n.get("d", []):
            walk(d)
    walk(data["ifc"])

    refs = {k: {"d": folders[k]["d"], "o": primary(folders[k]["f"]),
                "f": [[x["p"][len(folders[k]["d"]) + 1:], x["r"], x["x"], x["s"]] for x in folders[k]["f"]]}
            for k in sorted(used)}
    page = {"built": datetime.datetime.now().strftime("%d %b %Y %H:%M"), "exported": data.get("exported", ""),
            "root": args.win_root.rstrip("/\\").replace("\\", "/"),
            "sd": data["sd"], "sub": data["sub"], "ifc": data["ifc"], "sta": data["sta"],
            "upd": data["upd"], "refs": refs}
    blob = json.dumps(page, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.replace("/*__DATA__*/null", blob)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(html)
    os.replace(tmp, args.out)
    miss = sorted(set(missing))
    print(json.dumps({"out": args.out, "bytes": os.path.getsize(args.out), "refs_linked": len(refs),
                      "refs_not_in_mirror": len(miss), "missing": miss[:60],
                      "ifc_files_linked": ifc_hit, "ifc_files_not_in_mirror": ifc_miss}, ensure_ascii=False))


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V15 Offline Index</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--muted:#6b7684;--line:#e3e7ec;--acc:#1f5fbf;--acc-bg:#e8f0fc;
--A:#1e8a4c;--A-bg:#e3f4ea;--C:#c0392b;--C-bg:#fbe7e5;--U:#a87400;--U-bg:#fdf3d8;--E:#6b7684;--E-bg:#eceff2;--none:#9aa3ad;--none-bg:#f1f3f5}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1a2029;--ink:#e6eaf0;--muted:#97a1ad;--line:#2a323d;--acc:#7fb0ff;--acc-bg:#1e2c42;
--A:#5fd18f;--A-bg:#16352a;--C:#ff8a7c;--C-bg:#3d1f1d;--U:#f1c45b;--U-bg:#3a3018;--E:#a3adb8;--E-bg:#252c35;--none:#6b7684;--none-bg:#1f252d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 "Segoe UI",system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px 0}
h1{font-size:17px;margin:0 0 2px}.meta{color:var(--muted);font-size:12px}
nav{display:flex;gap:4px;margin-top:8px;overflow-x:auto}
nav button{border:0;background:none;color:var(--muted);padding:8px 12px;font:inherit;font-weight:600;border-bottom:3px solid transparent;cursor:pointer;white-space:nowrap}
nav button[aria-selected=true]{color:var(--acc);border-color:var(--acc)}
main{padding:12px 16px 60px;max-width:1300px;margin:0 auto}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:10px}
input[type=search]{flex:1 1 260px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:16px;padding:4px 10px;font:inherit;font-size:12px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--acc-bg);border-color:var(--acc);color:var(--acc)}
.count{color:var(--muted);font-size:12px;margin-left:auto}
details.g{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:10px}
details.g>summary{padding:10px 12px;font-weight:700;cursor:pointer}
.sub{padding:4px 12px 2px;color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
table{width:100%;border-collapse:collapse}td,th{padding:6px 8px;border-top:1px solid var(--line);vertical-align:top;text-align:left}
th{font-size:12px;color:var(--muted);font-weight:600}td.n{width:36px;color:var(--muted)}
.cells{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:6px}.cells.one{grid-template-columns:1fr}
.c{border-radius:8px;padding:5px 7px;font-size:12px;background:var(--none-bg);color:var(--none);display:flex;gap:4px;align-items:center;flex-wrap:wrap}
.c .ty{font-size:10px;opacity:.75;width:100%}
.ref{font-weight:700;color:inherit;text-decoration:none}.ref:hover{text-decoration:underline}
.sA{background:var(--A-bg);color:var(--A)}.sC{background:var(--C-bg);color:var(--C)}.sU{background:var(--U-bg);color:var(--U)}.sE{background:var(--E-bg);color:var(--E)}
.badge{display:inline-block;min-width:20px;text-align:center;border-radius:5px;padding:0 4px;font-size:11px;font-weight:700}
.ib{border:0;background:none;color:inherit;cursor:pointer;padding:0 3px;font-size:13px;opacity:.75}.ib:hover{opacity:1}
.miss{opacity:.6;font-style:italic}
.row{display:flex;gap:8px;align-items:center;padding:7px 10px;border-top:1px solid var(--line)}
.row .t{flex:1;min-width:0}.row .r{font-weight:700;white-space:nowrap}
.tree details{margin-left:14px}.tree summary{cursor:pointer;padding:3px 0}.tree .cnt{color:var(--muted);font-size:12px}
.tf{display:flex;gap:6px;align-items:center;margin-left:18px;padding:2px 0;font-size:13px}.tf .t{flex:1}
.x{font-size:11px;font-weight:700;border:1px solid var(--line);border-radius:5px;padding:1px 6px;text-decoration:none;color:var(--acc)}
#panel{position:fixed;inset:0;background:rgba(0,0,0,.35);display:none;align-items:flex-start;justify-content:center;padding:60px 12px;z-index:9}
#panel.on{display:flex}#pbox{background:var(--card);border-radius:12px;max-width:720px;width:100%;max-height:80vh;overflow:auto;padding:14px 16px}
#pbox h2{font-size:15px;margin:0 0 8px}.pf{display:flex;gap:8px;align-items:center;padding:6px 0;border-top:1px solid var(--line);font-size:13px}
.pf .t{flex:1;word-break:break-all}.pf.lt .t{font-weight:600}.btn{border:1px solid var(--line);background:var(--acc-bg);color:var(--acc);border-radius:7px;padding:4px 9px;font:inherit;font-size:12px;cursor:pointer;text-decoration:none;white-space:nowrap}
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:8px 14px;border-radius:8px;font-size:13px;display:none;z-index:10}
.upd td{font-size:13px}.k-new{color:var(--U)}.k-reply{color:var(--A)}
@media (max-width:700px){.cells{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header><h1>V15 Offline Index</h1><div class="meta" id="meta"></div>
<nav role="tablist"><button data-tab="sd" aria-selected="true">Shop Drawings</button><button data-tab="sub" aria-selected="false">MAS · PQN · RFI</button><button data-tab="ifc" aria-selected="false">IFC</button><button data-tab="upd" aria-selected="false">Updates</button></nav></header>
<main id="main"></main>
<div id="panel"><div id="pbox"></div></div><div id="toast"></div>
<script>
const D=/*__DATA__*/null;
const TYPES=["4BR T01","4BR T02","5BR T03","5BR T04"];
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const url=p=>"file:///"+(D.root+"/"+p).split("/").map((s,i)=>i===0?s:encodeURIComponent(s)).join("/");
const winPath=p=>(D.root+"/"+p).replace(/\//g,"\\");
const st=k=>{const v=D.sta[k];if(!v)return["",""];const c=v[0];const cl="AB".includes(c)?"sA":"CDF".includes(c)?"sC":c==="E"?"sE":"U W R".includes(c)?(c==="R"?"sA":"sU"):"";return[cl,c];};
const mb=s=>s>=1048576?(s/1048576).toFixed(1)+" MB":Math.max(1,Math.round(s/1024))+" KB";
document.getElementById("meta").textContent="Built "+D.built+" · opens files from "+D.root.replace(/\//g,"\\")+" · works offline";
function toast(t){const e=document.getElementById("toast");e.textContent=t;e.style.display="block";clearTimeout(toast.h);toast.h=setTimeout(()=>e.style.display="none",1800);}
async function copy(t){try{await navigator.clipboard.writeText(t);}catch(e){const a=document.createElement("textarea");a.value=t;document.body.appendChild(a);a.select();document.execCommand("copy");a.remove();}toast("Path copied – paste it in the attach/Open dialog");}
document.addEventListener("click",e=>{const b=e.target.closest("[data-copy]");if(b){e.preventDefault();copy(b.dataset.copy);}
 const p=e.target.closest("[data-panel]");if(p){e.preventDefault();openPanel(p.dataset.panel);}
 if(e.target.id==="panel")closePanel();});
document.addEventListener("keydown",e=>{if(e.key==="Escape")closePanel();});
function closePanel(){document.getElementById("panel").classList.remove("on");}
function openPanel(k){const r=D.refs[k];if(!r)return;const [cl,c]=st(k);const top=r.f.length?r.f[0][1]:-1;
 let h=`<h2>${esc("GPD-V15-QTGC-"+k)} ${c?`<span class="badge ${cl}">${esc(c)}</span>`:""}</h2>
 <div class="pf"><span class="t">📁 ${esc(winPath(r.d))}</span><a class="btn" href="${url(r.d)}" target="_blank">Open folder</a><button class="btn" data-copy="${esc(winPath(r.d))}">Copy path</button></div>`;
 for(const f of r.f){const p=r.d+"/"+f[0];h+=`<div class="pf${f[1]===top?" lt":""}"><span class="t">${f[2]?"📄 ":"🗂 "}${esc(f[0])} <span class="meta">${mb(f[3])}</span></span><a class="btn" href="${url(p)}" target="_blank">Open</a><button class="btn" data-copy="${esc(winPath(p))}">Copy path</button></div>`;}
 if(!r.f.length)h+=`<div class="pf"><span class="t meta">Folder is empty in the mirror.</span></div>`;
 document.getElementById("pbox").innerHTML=h+`<div style="text-align:right;margin-top:10px"><button class="btn" onclick="closePanel()">Close</button></div>`;
 document.getElementById("panel").classList.add("on");}
function refLink(k,label,drive){const r=k&&D.refs[k];const [cl,c]=st(k||"");
 if(!r)return `<span class="${cl} miss" title="Not found in the mirror">${esc(label)}</span>${drive?` <a class="ib" href="${esc(drive)}" target="_blank" title="Drive (needs internet)">☁</a>`:""}`;
 const o=r.o?url(r.o):url(r.d);
 return `<a class="ref" href="${o}" target="_blank" title="${esc(r.o?r.o.split("/").pop():"Open folder")}">${esc(label)}</a>${c?`<span class="badge ${cl}">${esc(c)}</span>`:""}`+
 `<button class="ib" data-panel="${k}" title="All files / copy path">⋯</button>`+(r.o?`<button class="ib" data-copy="${esc(winPath(r.o))}" title="Copy file path">📋</button>`:"");}
// ---------------- SD
const S={sd:{q:"",t:-1},sub:{q:"",ty:""},ifc:{q:""},tab:"sd"};
function viewSD(){const q=S.sd.q.toLowerCase();let n=0,h=`<div class="bar"><input type="search" id="q" placeholder="Search description or ref (e.g. ARC-019)" value="${esc(S.sd.q)}">`+
 TYPES.map((t,i)=>`<button class="chip" data-t="${i}" aria-pressed="${S.sd.t===i}">${t}</button>`).join("")+`<span class="count" id="cnt"></span></div>`;
 for(const g of D.sd){let gb="";for(const s of g.subs){let rows="";for(const it of s.items){
  const hay=(it.d+" "+s.s+" "+g.g+" "+it.c.map(c=>c.ref?c.ref+" SD-"+c.ref:c.txt||"").join(" ")).toLowerCase();
  if(q&&!hay.includes(q))continue;
  const one=it.c.length===1;const cells=it.c.map((c,i)=>{if(!one&&S.sd.t>=0&&i!==S.sd.t)return"";
   const ty=one?"All types":TYPES[i];
   if(c.ref){const k=c.rk;const [cl]=st("SD-"+c.ref);return `<div class="c ${cl}"><span class="ty">${ty}</span>${refLink(k,c.ref,c.url)}</div>`;}
   const tx=c.txt==="NOT IN REGISTER"?"Not in register":c.txt==="NOT SUBMITTED"?"Not submitted":(c.txt||"—");
   return `<div class="c"><span class="ty">${ty}</span>${esc(tx)}</div>`;}).join("");
  n++;rows+=`<tr><td class="n">${it.n}</td><td>${esc(it.d)}<div class="cells${one||S.sd.t>=0?" one":""}" style="margin-top:4px">${cells}</div></td></tr>`;}
  if(rows)gb+=`<div class="sub">${esc(s.s)}</div><table>${rows}</table>`;}
  if(gb)h+=`<details class="g" ${q||S.sd.t>=0?"open":""} open><summary>${esc(g.g)}</summary>${gb}</details>`;}
 return [h,n+" items"];}
// ---------------- MAS/PQN/RFI
function viewSub(){const q=S.sub.q.toLowerCase();let n=0,h=`<div class="bar"><input type="search" id="q" placeholder="Search title or ref" value="${esc(S.sub.q)}">`+
 ["MAS","PQN","RFI"].map(t=>`<button class="chip" data-ty="${t}" aria-pressed="${S.sub.ty===t}">${t}</button>`).join("")+`<span class="count" id="cnt"></span></div>`;
 for(const g of D.sub){let rows="";for(const it of g.items){if(S.sub.ty&&it.ty!==S.sub.ty)continue;
  if(q&&!(it.r+" "+it.t).toLowerCase().includes(q))continue;n++;const [cl]=st(it.rk||it.r.replace(/^GPD-V1\d?-QTGC-/,""));
  rows+=`<div class="row"><span class="r ${cl}" style="border-radius:6px;padding:1px 6px">${refLink(it.rk,it.r.replace(/^GPD-V15-QTGC-/,""),it.u)}</span><span class="t">${esc(it.t)}</span><span class="meta">${it.ty}</span></div>`;}
  if(rows)h+=`<details class="g" open><summary>${esc(g.g)}</summary>${rows}</details>`;}
 return [h,n+" refs"];}
// ---------------- IFC
function cntF(n){return (n.f||[]).length+(n.d||[]).reduce((a,d)=>a+cntF(d),0);}
function viewIFC(){const q=S.ifc.q.toLowerCase();let n=0;
 function node(x,depth){let fs="";for(const f of x.f||[]){if(q&&!f.t.toLowerCase().includes(q))continue;n++;
   fs+=`<div class="tf"><span class="t">${esc(f.t)}</span>`+Object.entries(f.x).map(([e,v])=>v.p?`<a class="x" href="${url(v.p)}" target="_blank">${e.toUpperCase()}</a><button class="ib" data-copy="${esc(winPath(v.p))}" title="Copy path">📋</button>`:`<span class="x miss" title="Not in mirror">${e.toUpperCase()}</span>`).join("")+`</div>`;}
  let ds="";for(const d of x.d||[]){const c=node(d,depth+1);if(c)ds+=c;}
  if(!fs&&!ds)return"";if(depth===0)return ds+fs;
  return `<details ${q?"open":""}><summary>${esc(x.n)} <span class="cnt">(${cntF(x)})</span></summary>${ds}${fs}</details>`;}
 const body=node(D.ifc,0);
 return [`<div class="bar"><input type="search" id="q" placeholder="Search drawing number or title" value="${esc(S.ifc.q)}"><span class="count" id="cnt"></span></div><div class="tree g" style="padding:8px 12px;background:var(--card);border:1px solid var(--line);border-radius:10px">${body||'<span class="meta">No match.</span>'}</div>`,n+" files"];}
// ---------------- Updates
function viewUpd(){const days={};for(const [src,l] of Object.entries(D.upd))for(const d of l){(days[d.d]=days[d.d]||{label:d.label,items:[]}).items.push(...d.items);}
 let h="",n=0;for(const k of Object.keys(days).sort().reverse()){const d=days[k];n+=d.items.length;
  h+=`<details class="g upd" ${n===d.items.length?"open":""}><summary>${esc(d.label)} <span class="meta">(${d.items.length})</span></summary><table>`+d.items.map(it=>
  `<tr><td style="white-space:nowrap">${refLink(it.rk,it.r,it.u)}</td><td>${esc(it.rev||"")}</td><td>${esc(it.t||"")}</td><td class="k-${esc(it.k||"")}">${esc(it.n||"")}</td></tr>`).join("")+`</table></details>`;}
 return ['<div class="bar"><span class="meta">Latest Unifier changes from the daily check</span><span class="count" id="cnt"></span></div>'+(h||'<span class="meta">No updates.</span>'),n+" updates"];}
const VIEWS={sd:viewSD,sub:viewSub,ifc:viewIFC,upd:viewUpd};
function render(keepFocus){const [h,c]=VIEWS[S.tab]();const m=document.getElementById("main");m.innerHTML=h;
 const cnt=document.getElementById("cnt");if(cnt)cnt.textContent=c;const q=document.getElementById("q");
 if(q){q.oninput=()=>{(S[S.tab]).q=q.value;clearTimeout(render.h);render.h=setTimeout(()=>render(true),150);};if(keepFocus){q.focus();q.setSelectionRange(q.value.length,q.value.length);}}
 m.querySelectorAll(".chip[data-t]").forEach(b=>b.onclick=()=>{const i=+b.dataset.t;S.sd.t=S.sd.t===i?-1:i;render();});
 m.querySelectorAll(".chip[data-ty]").forEach(b=>b.onclick=()=>{S.sub.ty=S.sub.ty===b.dataset.ty?"":b.dataset.ty;render();});}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{S.tab=b.dataset.tab;document.querySelectorAll("nav button").forEach(x=>x.setAttribute("aria-selected",x===b));
 try{localStorage.setItem("v15off.tab",S.tab);}catch(e){}render();window.scrollTo(0,0);});
try{const t=localStorage.getItem("v15off.tab");if(t&&VIEWS[t]){S.tab=t;document.querySelectorAll("nav button").forEach(x=>x.setAttribute("aria-selected",x.dataset.tab===t));}}catch(e){}
render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("export")
    e.add_argument("--repo", default=".")
    e.add_argument("--out", required=True)
    for name in ("build", "update"):
        b = sp.add_parser(name)
        if name == "build":
            b.add_argument("data")
        b.add_argument("--mirror", required=True)
        b.add_argument("--win-root", default="D:/mirrored drive")
        b.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "export":
        export(a)
    elif a.cmd == "build":
        build(a)
    else:
        build(a, page_data(fetch_live()))


if __name__ == "__main__":
    main()
