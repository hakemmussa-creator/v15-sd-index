#!/usr/bin/env python3
"""V15 subcontractor submittals - 2-page A4 management report.

Usage:
  python3 tools/subreport.py data.json --out "V15 Subcontractor Submittals Report 08 Nov 2026.pdf"

data.json = {"date": "YYYY-MM-DD",
             "trackers": [{"name": "<registry TRACKER name>", "id": "<sheet id>",
                           "main": <get_values of '<MAIN TAB>'!A1:AH40>,
                           "related": <get_values of '<RELATED TAB>'!A1:F80>}, ...]}
The main tab layout is the /subtracker layout: header row starts with 'No.', the next row is
REF. NO./REV./STATUS/SUB. DATE, then one row per item; columns from C are 4-cell blocks
(ref, rev, status, date) or a merged 'NOT SUBMITTED' / 'N/A' / 'NOT IN REGISTER' block.
Counts are per tracker cell, the same way the trackers' own summaries count.
Prints a JSON summary (counts per tracker) for checking against the sheets.
No project data is stored in this file (the repo is public).
"""
import argparse, json, re, sys
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.platypus import (KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

NAVY = colors.HexColor("#1F3864")
LIGHT = colors.HexColor("#D9E1F2")
C = {"ok": ("#C6EFCE", "#006100"), "re": ("#FFC7CE", "#9C0006"),
     "ur": ("#FFEB9C", "#9C5700"), "ns": ("#E7E6E6", "#595959"), "na": ("#FFFFFF", "#A6A6A6")}
LBL = {"ok": "Approved (A/B)", "re": "Resubmit (C/D/F)", "ur": "Under review", "ns": "Not submitted"}
NS, NA, NIR = "NOT SUBMITTED", "N/A", "NOT IN REGISTER"
LOC_ORDER = ["MAS", "DS", "4BR T01", "4BR T02", "5BR T03", "5BR T04", "Hall", "Changing Rm", "Gym"]
VILLA = {"MAS", "DS", "4BR T01", "4BR T02", "5BR T03", "5BR T04"}

W, H = A4
MARGIN = 14 * mm
TOP = 30 * mm      # header band
BOTTOM = 14 * mm   # footer


def cls(s):
    s = (s or "").strip()
    if re.match(r"^[AB]\s*[–-]", s):
        return "ok"
    if re.match(r"^[CDF]\s*[–-]", s):
        return "re"
    if s.lower() == "under review":
        return "ur"
    if s.upper() == NS:
        return "ns"
    return None


def short_loc(h):
    u = (h or "").upper()
    if "(MAS)" in u or u.startswith("MATERIAL"):
        return "MAS"
    if "(DS)" in u or u.startswith("DOCUMENT"):
        return "DS"
    m = re.search(r"([45])\s*BR\s*TYPE\s*0?(\d)", u)
    if m:
        return "%sBR T0%s" % (m.group(1), m.group(2))
    if "HALL" in u:
        return "Hall"
    if "CHANGING" in u:
        return "Changing Rm"
    if "GYM" in u:
        return "Gym"
    return h.split("–")[-1].strip().title()[:12]


def pdate(s):
    s = (s or "").strip()
    for f in ("%d-%b-%y", "%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def cell(r, i):
    return (r[i] if i < len(r) else "") or ""


def parse(t):
    rows = t["main"]
    h = next(i for i, r in enumerate(rows) if r and str(r[0]).strip() == "No.")
    hdr = rows[h]
    title = " ".join(str(x) for x in (rows[1] if h >= 2 and len(rows) > 1 else []))
    blocks = [(k, short_loc(hdr[k])) for k in range(2, len(hdr), 4) if str(hdr[k]).strip()]
    name = t["name"]
    pkg, sub = (name.split(" – ", 1) + ["—"])[:2] if " – " in name else (name, "—")
    entries = []
    for r in rows[h + 2:]:
        if not r or not str(cell(r, 1)).strip():
            break
        item = str(cell(r, 1)).strip()
        for k, loc in blocks:
            ref = str(cell(r, k)).strip()
            if not ref or ref.upper() in (NA, NIR):
                continue
            if ref.upper() == NS:
                entries.append(dict(item=item, loc=loc, ref="", rev="", st=NS, k="ns", d=None))
                continue
            st = str(cell(r, k + 2)).strip()
            k2 = cls(st)
            if k2:
                entries.append(dict(item=item, loc=loc, ref=ref, rev=str(cell(r, k + 1)).strip(),
                                    st=st, k=k2, d=pdate(cell(r, k + 3))))
    pqn = re.search(r"\b(PQN-[A-Z]+-\d+)", title)
    pqn = pqn.group(1) if pqn else ""
    pst = ""
    rel = t.get("related") or []
    if pqn and rel:
        hi = next((i for i, r in enumerate(rel) if any(str(x).strip().upper() == "STATUS" for x in r)), None)
        if hi is not None:
            sc = [str(x).strip().upper() for x in rel[hi]].index("STATUS")
            for r in rel[hi + 1:]:
                if any(str(x).strip().endswith(pqn) for x in r):
                    pst = cell(r, sc)
                    break
    cnt = {k: sum(1 for e in entries if e["k"] == k) for k in ("ok", "re", "ur", "ns")}
    return dict(pkg=pkg.strip(), sub=sub.strip(), pqn=pqn, pst=pst, e=entries, n=cnt,
                tot=sum(cnt.values()))


def P(txt, st):
    return Paragraph(txt, st)


def bar(n, tot, w=70, h=7):
    d = Drawing(w, h)
    x = 0
    for k in ("ok", "re", "ur", "ns"):
        if tot and n[k]:
            ww = w * n[k] / tot
            d.add(Rect(x, 0, ww, h, fillColor=colors.HexColor(C[k][0] if k != "ok" else "#70AD47"),
                       strokeColor=None))
            x += ww
    d.add(Rect(0, 0, w, h, fillColor=None, strokeColor=colors.HexColor("#808080"), strokeWidth=0.4))
    return d


def build(data, out):
    today = datetime.strptime(data["date"], "%Y-%m-%d").date()
    lab = today.strftime("%d %b %Y")
    T = [parse(t) for t in data["trackers"]]

    ss = dict(
        h1=ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=10.5, textColor=NAVY, spaceBefore=5, spaceAfter=3),
        b=ParagraphStyle("b", fontName="Helvetica", fontSize=8, leading=10),
        s=ParagraphStyle("s", fontName="Helvetica", fontSize=7, leading=8.6),
        sb=ParagraphStyle("sb", fontName="Helvetica-Bold", fontSize=7, leading=8.6),
        sh=ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=7, leading=8.6, textColor=colors.white),
        shc=ParagraphStyle("shc", fontName="Helvetica-Bold", fontSize=7, leading=8.6, textColor=colors.white, alignment=TA_CENTER),
        bul=ParagraphStyle("bul", fontName="Helvetica", fontSize=8, leading=10.4, leftIndent=9, bulletIndent=0, spaceAfter=2),
        note=ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=6.6, leading=8.2, textColor=colors.HexColor("#595959")),
    )
    fw = W - 2 * MARGIN
    base_ts = [("FONT", (0, 0), (-1, -1), "Helvetica", 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#808080")),
               ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7), ("TOPPADDING", (0, 0), (-1, -1), 2.2),
               ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2), ("LEFTPADDING", (0, 0), (-1, -1), 3),
               ("RIGHTPADDING", (0, 0), (-1, -1), 3)]

    tot = {k: sum(t["n"][k] for t in T) for k in ("ok", "re", "ur", "ns")}
    N = sum(tot.values())
    pct = lambda a, b: (100.0 * a / b) if b else 0.0

    # ---------- page 1 ----------
    p1 = []
    p1.append(P("<b>Main Contractor:</b> QUMRA Transport &amp; General Contracting LLC &nbsp;|&nbsp; "
                "<b>Employer:</b> Emaar Development PJSC &nbsp;|&nbsp; <b>Consultant:</b> Mirage Leisure &amp; Development "
                "&nbsp;|&nbsp; Source: Emaar Unifier submittal log", ss["s"]))
    p1.append(Spacer(1, 5))
    tiles = [("Tracked submittals", N, None), ("Approved (A/B)", tot["ok"], "ok"), ("Resubmit (C/D/F)", tot["re"], "re"),
             ("Under review", tot["ur"], "ur"), ("Not submitted", tot["ns"], "ns")]
    big = ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=17, leading=19, alignment=TA_CENTER)
    small = ParagraphStyle("sm", fontName="Helvetica", fontSize=7, leading=8.5, alignment=TA_CENTER)
    row, ts = [], [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                   ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for i, (l, v, k) in enumerate(tiles):
        fg = colors.HexColor(C[k][1]) if k else NAVY
        bg = colors.HexColor(C[k][0]) if k else LIGHT
        sub_txt = l if k is None else "%s<br/>%.0f%% of total" % (l, pct(v, N))
        row.append([Paragraph('<font color="%s">%d</font>' % (fg.hexval().replace("0x", "#"), v), big),
                    Paragraph(sub_txt, small)])
        ts += [("BACKGROUND", (i, 0), (i, 0), bg), ("BOX", (i, 0), (i, 0), 0.6, colors.white)]
    kt = Table([row], colWidths=[fw / 5] * 5)
    kt.setStyle(TableStyle(ts))
    p1.append(kt)

    p1.append(P("1. Portfolio overview", ss["h1"]))
    hdr = ["No.", "Package", "Subcontractor", "Pre-qualification", "A/B", "C/D/F", "Under\nreview",
           "Not\nsub.", "Total", "% Appr.", "Progress"]
    data_rows = [[P(x.replace("\n", "<br/>"), ss["shc"] if i > 3 else ss["sh"]) for i, x in enumerate(hdr)]]
    for i, t in enumerate(T, 1):
        pq = "—"
        if t["pqn"]:
            k = cls(t["pst"])
            pq = "%s<br/><font color='%s'>%s</font>" % (t["pqn"], C[k][1] if k else "#595959", t["pst"] or "—")
        data_rows.append([str(i), P("<b>%s</b>" % t["pkg"], ss["s"]), P(t["sub"], ss["s"]), P(pq, ss["s"]),
                          t["n"]["ok"], t["n"]["re"], t["n"]["ur"], t["n"]["ns"], t["tot"],
                          "%.0f%%" % pct(t["n"]["ok"], t["tot"]), bar(t["n"], t["tot"])])
    data_rows.append(["", P("<b>TOTAL</b>", ss["s"]), "", "", tot["ok"], tot["re"], tot["ur"], tot["ns"], N,
                      "%.0f%%" % pct(tot["ok"], N), bar(tot, N)])
    cw = [20, 92, 92, 92, 26, 28, 30, 26, 26, 32, 0]
    cw[-1] = fw - sum(cw)
    pt = Table(data_rows, colWidths=cw, repeatRows=1)
    st = base_ts + [("ALIGN", (4, 1), (-1, -1), "CENTER"), ("ALIGN", (0, 1), (0, -1), "CENTER"),
                    ("BACKGROUND", (0, -1), (-1, -1), LIGHT), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 7)]
    for col, k in ((4, "ok"), (5, "re"), (6, "ur"), (7, "ns")):
        st += [("TEXTCOLOR", (col, 1), (col, -1), colors.HexColor(C[k][1])),
               ("FONT", (col, 1), (col, -1), "Helvetica-Bold", 7.5)]
    pt.setStyle(TableStyle(st))
    p1.append(pt)

    # status matrix
    p1.append(P("2. Status by location (approved / tracked; colour = most critical open status)", ss["h1"]))
    locs = [l for l in LOC_ORDER if any(e["loc"] == l for t in T for e in t["e"])]
    mrow = [[P("Package", ss["sh"])] + [P(l, ss["shc"]) for l in locs]]
    mst = base_ts + [("ALIGN", (1, 1), (-1, -1), "CENTER")]
    for r, t in enumerate(T, 1):
        line = [P("<b>%s</b>" % t["pkg"], ss["s"])]
        for c, l in enumerate(locs, 1):
            es = [e for e in t["e"] if e["loc"] == l]
            if not es:
                line.append("–")
                mst += [("TEXTCOLOR", (c, r), (c, r), colors.HexColor("#A6A6A6"))]
                continue
            ok = sum(1 for e in es if e["k"] == "ok")
            worst = next(k for k in ("re", "ur", "ns", "ok") if any(e["k"] == k for e in es))
            line.append("%d/%d" % (ok, len(es)))
            mst += [("BACKGROUND", (c, r), (c, r), colors.HexColor(C[worst][0])),
                    ("TEXTCOLOR", (c, r), (c, r), colors.HexColor(C[worst][1])),
                    ("FONT", (c, r), (c, r), "Helvetica-Bold", 7.5)]
        mrow.append(line)
    mw = 120
    mt = Table(mrow, colWidths=[mw] + [(fw - mw) / len(locs)] * len(locs))
    mt.setStyle(TableStyle(mst))
    p1.append(mt)
    leg = " &nbsp; ".join('<font backColor="%s" color="%s">&nbsp;%s&nbsp;</font>' % (C[k][0], C[k][1], LBL[k])
                          for k in ("ok", "ur", "re", "ns"))
    p1.append(Spacer(1, 3))
    p1.append(P(leg + " &nbsp; &nbsp; – = not applicable / not in SD register. "
                "MAS = material submittal, DS = document submittal, Hall / Changing Rm / Gym = Community Center.", ss["note"]))

    # key points
    p1.append(P("3. Key points for management", ss["h1"]))
    kp = []
    kp.append("<b>%d of %d</b> tracked submittals are approved (<b>%.0f%%</b>); <b>%d</b> need resubmission, "
              "<b>%d</b> are with the consultant and <b>%d</b> are not yet submitted."
              % (tot["ok"], N, pct(tot["ok"], N), tot["re"], tot["ur"], tot["ns"]))
    full = [t["pkg"] for t in T if all(e["k"] == "ok" for e in t["e"] if e["loc"] in VILLA)
            and any(e["loc"] in VILLA for e in t["e"])]
    if full:
        kp.append("Villa scope fully approved (materials and villa shop drawings): <b>%s</b>." % ", ".join(full))
    res = []
    for t in T:
        seen = {}
        for e in t["e"]:
            if e["k"] == "re":
                seen.setdefault(e["ref"], []).append(e)
        for ref, es in seen.items():
            code = es[0]["st"][:1]
            res.append("%s (%s, %s, code %s)" % (ref, t["pkg"], ", ".join(x["loc"] for x in es), code))
    if res:
        kp.append("<b>Resubmissions outstanding (%d):</b> %s." % (len(res), "; ".join(res)))
    ur = [(today - e["d"]).days for t in T for e in t["e"] if e["k"] == "ur" and e["d"]]
    if ur:
        old = max(((today - e["d"]).days, e["ref"], t["pkg"]) for t in T for e in t["e"] if e["k"] == "ur" and e["d"])
        kp.append("<b>%d</b> items are under consultant review; the longest pending is <b>%s</b> (%s) at <b>%d days</b>."
                  % (tot["ur"], old[1], old[2], old[0]))
    ns_cc = sum(1 for t in T for e in t["e"] if e["k"] == "ns" and e["loc"] not in VILLA)
    ns_v = tot["ns"] - ns_cc
    if tot["ns"]:
        kp.append("Not yet submitted: <b>%d</b> villa shop drawings and <b>%d</b> Community Center shop drawings "
                  "(see page 2 for the list by package)." % (ns_v, ns_cc))
    pq = ["%s – %s %s" % (t["pkg"], t["pqn"], (t["pst"] or "status not found").split("–")[-1].strip().lower())
          for t in T if t["pqn"] and cls(t["pst"]) != "ok"]
    nopq = [t["pkg"] for t in T if not t["pqn"]]
    if pq:
        kp.append("Subcontractor pre-qualification not yet approved: %s." % "; ".join(pq))
    if nopq:
        kp.append("No subcontractor pre-qualification recorded on the tracker for: %s." % ", ".join(nopq))
    for x in kp:
        p1.append(P(x, ss["bul"], ) if False else Paragraph(x, ss["bul"], bulletText="•"))

    # ---------- page 2 ----------
    p2 = []

    def group(k):
        out = []
        for t in T:
            g = {}
            for e in t["e"]:
                if e["k"] == k:
                    g.setdefault((e["item"], e["ref"]), []).append(e)
            for (item, ref), es in g.items():
                out.append((t["pkg"], item, ", ".join(x["loc"] for x in es), ref, es[0]["rev"], es[0]["st"], es[0]["d"]))
        return out

    def table(rows, k, title, days_lbl):
        p2.append(P(title, ss["h1"]))
        if not rows:
            p2.append(P("None.", ss["b"]))
            return
        hh = ["Package", "Item", "Location", "Ref.", "Rev.", "Status", "Last sub.", days_lbl]
        tr = [[P(x, ss["sh"]) for x in hh]]
        for pkg, item, loc, ref, rev, stt, d in rows:
            dd = d.strftime("%d-%b-%y") if d else "n/a"
            dy = str((today - d).days) if d else "—"
            tr.append([P(pkg, ss["s"]), P(item, ss["s"]), P(loc, ss["s"]), P("<b>%s</b>" % ref, ss["s"]), rev,
                       P(stt, ss["s"]), dd, dy])
        cw2 = [78, 142, 60, 58, 30, 74, 40, 0]
        cw2[-1] = fw - sum(cw2)
        tb = Table(tr, colWidths=cw2, repeatRows=1)
        tb.setStyle(TableStyle(base_ts + [("BACKGROUND", (5, 1), (5, -1), colors.HexColor(C[k][0])),
                                          ("ALIGN", (4, 1), (4, -1), "CENTER"), ("ALIGN", (6, 1), (-1, -1), "CENTER")]))
        p2.append(tb)

    table(group("re"), "re", "4. Resubmission required (consultant code C / D / F)", "Days")
    table(group("ur"), "ur", "5. Under review with the consultant", "Days")

    p2.append(P("6. Not yet submitted (shop drawings registered but not in Unifier)", ss["h1"]))
    ns_rows = []
    for t in T:
        g = {}
        for e in t["e"]:
            if e["k"] == "ns":
                g.setdefault(e["item"], []).append(e["loc"])
        for item, ls in g.items():
            ns_rows.append((t["pkg"], item, ls))
    if ns_rows:
        tr = [[P(x, ss["sh"]) for x in ("Package", "Item", "Locations not submitted", "No.")]]
        for pkg, item, ls in ns_rows:
            tr.append([P(pkg, ss["s"]), P(item, ss["s"]), P(", ".join(ls), ss["s"]), str(len(ls))])
        cw3 = [80, 190, 0, 26]
        cw3[2] = fw - sum(cw3)
        tb = Table(tr, colWidths=cw3, repeatRows=1)
        tb.setStyle(TableStyle(base_ts + [("ALIGN", (3, 1), (3, -1), "CENTER")]))
        p2.append(tb)
    else:
        p2.append(P("None.", ss["b"]))

    p2.append(Spacer(1, 6))
    p2.append(P("Notes: (1) Source is each package tracker in Drive folder 'V15 Subcontractor Trackers', refreshed from the "
                "Emaar Unifier submittal log (latest revision per reference). (2) Counts are per tracker cell: a shop drawing "
                "covering two villa types counts under both. N/A and not-in-register cells are excluded. (3) 'Last sub.' is the "
                "submission date of the latest revision; 'n/a' where Unifier revised the record in place and keeps no date "
                "for the new revision. (4) Shop drawings carry no supplier in Unifier and are attributed to the package by "
                "title.", ss["note"]))

    def deco(c, doc):
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, H - TOP + 4 * mm, W, TOP - 4 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 12.5)
        c.drawString(MARGIN, H - 12 * mm, "GRAND POLO CLUB & RESORT – CLUSTER MONTURA (V15)")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, H - 18 * mm, "SUBCONTRACTOR SUBMITTALS STATUS – MANAGEMENT REPORT")
        c.setFont("Helvetica", 8.5)
        c.drawString(MARGIN, H - 23 * mm, "Status as of %s" % lab)
        c.drawRightString(W - MARGIN, H - 12 * mm, "QUMRA")
        c.setFont("Helvetica", 7)
        c.drawRightString(W - MARGIN, H - 17 * mm, "Technical Department")
        c.setStrokeColor(colors.HexColor("#808080"))
        c.setLineWidth(0.4)
        c.line(MARGIN, 11 * mm, W - MARGIN, 11 * mm)
        c.setFillColor(colors.HexColor("#595959"))
        c.setFont("Helvetica", 6.8)
        c.drawString(MARGIN, 7.5 * mm, "QUMRA Transport & General Contracting LLC – V15 subcontractor submittals report, %s" % lab)
        c.drawRightString(W - MARGIN, 7.5 * mm, "Page %d of 2" % doc.page)
        c.restoreState()

    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=TOP,
                            bottomMargin=BOTTOM, title="V15 Subcontractor Submittals Report – %s" % lab,
                            author="QUMRA – Technical Department")
    fh = H - TOP - BOTTOM - 13  # frame padding
    story = [KeepInFrame(fw, fh, p1, mode="shrink"), PageBreak(), KeepInFrame(fw, fh, p2, mode="shrink")]
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return {t["pkg"]: dict(t["n"], total=t["tot"], pqn=t["pqn"], pqn_status=t["pst"]) for t in T}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = build(json.load(open(a.data)), a.out)
    print(json.dumps(res, ensure_ascii=False))
