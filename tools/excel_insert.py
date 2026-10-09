#!/usr/bin/env python3
"""Insert rows into 'SD Index V15 - Drive Links RevNN.xlsx' at XML level (keeps logos, styles, hidden sheets).

Usage:
  python3 tools/excel_insert.py RevNN.xlsx RevNN+1.xlsx plan.json

plan.json:
{
  "folders": {"SD-ARC-090": "<drive folder id>", ...},          # every ref used below
  "uses":    {"SD-ARC-090": "Row text for Drive Links sheet", ...}, # optional
  "set":     [{"cell": "E84", "ref": "SD-ARC-042"}],              # change existing cells (row numbers BEFORE inserts)
  "insert":  [                                                     # 'before' = row number in the ORIGINAL file
    {"before": 34, "rows": [
        {"heading": "GENERAL (CLUSTER) DRAWINGS"},
        {"like": 35, "desc": "Master Plan at Ground Floor", "cells": ["ref:SD-ARC-003", "ref:SD-ARC-003", "ref:SD-ARC-003", "ref:SD-ARC-003"]}
    ]}
  ]
}
cells = the 4 villa-type columns D..G (4BR T01, 4BR T02, 5BR T03, 5BR T04):
  "ref:SD-XXX-NNN" link to its folder | "NA" | "NS" (NOT SUBMITTED) | "NIR" (NOT IN REGISTER) | "" empty.
'like' = an existing row (original numbering) whose A/B/C/H cell styles are copied; pick a row in the same section.

Afterwards: S.I. (column A) renumbered, all formulas/conditional formats/print area shifted, ARCH summary
ranges re-fitted to the ARCHITECTURAL section, 'Ref Matching Notes' Index Row + S.I. remapped,
'Drive Links' "Row N" texts remapped and one row appended per new folder. calcChain dropped (Excel rebuilds).
"""
import json, os, re, shutil, sys, tempfile, zipfile
from xml.sax.saxutils import escape

SRC, DST, PLAN = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3], encoding="utf-8"))
X = tempfile.mkdtemp()
zipfile.ZipFile(SRC).extractall(X)
P = lambda p: os.path.join(X, p)
rd = lambda p: open(P(p), encoding="utf-8").read()
wr = lambda p, t: open(P(p), "w", encoding="utf-8").write(t)
DRV, PRE = "https://drive.google.com/drive/folders/", "GPD-V15-QTGC-"
F = PLAN["folders"]
LINK_S, STATUS_S = 54, 27

SST = [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<si>(.*?)</si>", rd("xl/sharedStrings.xml"), re.S)]
def sidx(text):
    return SST.index(text)
NA, NS, NIR = sidx("N/A"), sidx("NOT SUBMITTED"), sidx("NOT IN REGISTER")
REF = re.compile(r"(\$?)([A-Z]{1,3})(\$?)(\d+)\b")


def shift_ref_text(s, n, k):
    parts = s.split('"')
    for i in range(0, len(parts), 2):
        parts[i] = REF.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + str(int(m.group(4)) + k if int(m.group(4)) >= n else int(m.group(4))), parts[i])
    return '"'.join(parts)


def cell(col, r, spec, s=None):
    if spec.startswith("ref:"):
        ref = spec[4:]
        f = f'HYPERLINK("{DRV}{F[ref]}","{PRE}{ref}")'
        return f'<c r="{col}{r}" s="{LINK_S}" t="str"><f>{escape(f)}</f><v>{PRE}{ref}</v></c>'
    if spec in ("NA", "NS", "NIR"):
        return f'<c r="{col}{r}" s="{s or STATUS_S}" t="s"><v>{dict(NA=NA, NS=NS, NIR=NIR)[spec]}</v></c>'
    return f'<c r="{col}{r}" s="{s or STATUS_S}"/>'


s1 = rd("xl/worksheets/sheet1.xml")
orig = {int(m.group(1)): m.group(0) for m in re.finditer(r'<row r="(\d+)".*?</row>', s1, re.S)}


def style_of(r, col):
    m = re.search(rf'<c r="{col}{r}" s="(\d+)"', orig[r])
    return m.group(1) if m else "13"


def row_xml(r, spec):
    if "heading" in spec:
        return (f'<row r="{r}" spans="1:8" s="8" customFormat="1" ht="17.45" customHeight="1" x14ac:dyDescent="0.25">'
                f'<c r="A{r}" s="21" t="inlineStr"><is><t>{escape(spec["heading"])}</t></is></c><c r="B{r}" s="22"/><c r="C{r}" s="23"/>'
                + "".join(f'<c r="{c}{r}" s="24"/>' for c in "DEFG") + f'<c r="H{r}" s="25"/></row>')
    L = spec["like"]
    out = [f'<row r="{r}" spans="1:8" x14ac:dyDescent="0.25">', f'<c r="A{r}" s="{style_of(L, "A")}"><v>0</v></c>',
           f'<c r="B{r}" s="{style_of(L, "B")}" t="inlineStr"><is><t>{escape(spec["desc"])}</t></is></c>',
           f'<c r="C{r}" s="{style_of(L, "C")}" t="s"><v>{NA}</v></c>']
    out += [cell(c, r, v) for c, v in zip("DEFG", spec["cells"])]
    out.append(f'<c r="H{r}" s="{style_of(L, "H")}"/></row>')
    return "".join(out)


for st in PLAN.get("set", []):
    col, rr = re.match(r"([A-Z]+)(\d+)", st["cell"]).groups()
    m = re.search(rf'<c r="{st["cell"]}"[^>]*?(/>|>.*?</c>)', s1, re.S)
    s1 = s1[:m.start()] + cell(col, int(rr), "ref:" + st["ref"]) + s1[m.end():]

row_map = {o: o for o in orig}
for blk in sorted(PLAN["insert"], key=lambda b: -b["before"]):
    n, specs = blk["before"], blk["rows"]
    k = len(specs)
    s1 = re.sub(r'<row r="(\d+)"[^>]*>', lambda m: m.group(0) if int(m.group(1)) < n else m.group(0).replace(f'r="{m.group(1)}"', f'r="{int(m.group(1)) + k}"', 1), s1)
    s1 = re.sub(r'<c r="([A-Z]+)(\d+)"', lambda m: m.group(0) if int(m.group(2)) < n else f'<c r="{m.group(1)}{int(m.group(2)) + k}"', s1)
    s1 = re.sub(r"<f>(.*?)</f>", lambda m: "<f>" + shift_ref_text(m.group(1), n, k) + "</f>", s1, flags=re.S)
    s1 = re.sub(r'sqref="([^"]+)"', lambda m: 'sqref="' + re.sub(r"(?<=[A-Z])(\d{7,})", lambda q: str(min(int(q.group(1)), 1048576)), shift_ref_text(m.group(1), n, k)) + '"', s1)
    s1 = re.sub(r'<dimension ref="([^"]+)"', lambda m: '<dimension ref="' + shift_ref_text(m.group(1), n, k) + '"', s1)
    m = re.search(rf'<row r="{n + k}"', s1)
    s1 = s1[:m.start()] + "".join(row_xml(n + i, sp) for i, sp in enumerate(specs)) + s1[m.start():]
    row_map = {o: (r + k if r >= n else r) for o, r in row_map.items()}

# renumber S.I.
old_si, counter = {}, [0]
def renum(m):
    row = m.group(0)
    a = re.search(r'<c r="A(\d+)"( s="\d+")?><v>(\d+)</v></c>', row)
    if not a or '<c r="B' not in row:
        return row
    counter[0] += 1
    if int(a.group(3)):
        old_si[int(a.group(3))] = counter[0]
    return row.replace(a.group(0), f'<c r="A{a.group(1)}"{a.group(2) or ""}><v>{counter[0]}</v></c>', 1)
s1 = re.sub(r'<row r="(\d+)"[^>]*>.*?</row>', renum, s1, flags=re.S)

# ARCH summary range = first row after 'ARCHITECTURAL / ID' heading .. last numbered row before the summary block
arch = None
for rr, body in re.findall(r'<row r="(\d+)"[^>]*>(.*?)</row>', s1, re.S):
    m = re.search(r'<c r="A\d+" s="\d+" t="(s|inlineStr)">(?:<v>(\d+)</v>|<is><t>([^<]*)</t></is>)', body)
    if m:
        txt = SST[int(m.group(2))] if m.group(1) == "s" else m.group(3)
        if txt.strip().upper().startswith("ARCHITECTURAL"):
            arch = int(rr)
            break
for a1, a2 in set(re.findall(r"C(\d+):G(\d+)", s1)):
    if arch and arch + 1 < int(a1) <= arch + 12:
        s1 = s1.replace(f"C{a1}:G{a2}", f"C{arch + 1}:G{a2}")
# CIVIL summary range (starts at the first structure row, 7) must end just above the ARCHITECTURAL heading
for a1, a2 in set(re.findall(r"C(\d+):G(\d+)", s1)):
    if arch and int(a1) == 7 and int(a2) != arch - 1:
        s1 = s1.replace(f"C7:G{a2}", f"C7:G{arch - 1}")
wr("xl/worksheets/sheet1.xml", s1)

wb = rd("xl/workbook.xml")
wb = re.sub(r"(Print_Area[^>]*>[^<]*\$H\$)(\d+)", lambda m: m.group(1) + str(row_map.get(int(m.group(2)), int(m.group(2)))), wb)
wb = re.sub(r"<calcPr([^>]*)/>", lambda m: "<calcPr" + m.group(1).replace(' fullCalcOnLoad="1"', "") + ' fullCalcOnLoad="1"/>', wb)
wr("xl/workbook.xml", wb)
if os.path.exists(P("xl/calcChain.xml")):
    os.remove(P("xl/calcChain.xml"))
wr("[Content_Types].xml", re.sub(r"<Override[^>]*calcChain[^>]*/>", "", rd("[Content_Types].xml")))
wr("xl/_rels/workbook.xml.rels", re.sub(r"<Relationship[^>]*calcChain[^>]*/>", "", rd("xl/_rels/workbook.xml.rels")))

sst = rd("xl/sharedStrings.xml")
wr("xl/sharedStrings.xml", re.sub(r"\bRow (\d+)( - )", lambda m: f"Row {row_map.get(int(m.group(1)), int(m.group(1)))}{m.group(2)}", sst))

s2 = rd("xl/worksheets/sheet2.xml")
def remap(col, r, v):
    if r == 1 or not v.isdigit():
        return None
    return row_map.get(int(v), int(v)) if col == "A" else old_si.get(int(v), int(v))
s2 = re.sub(r'<c r="([AB])(\d+)"((?: s="\d+")?) t="s"><v>(\d+)</v></c>',
            lambda m: (lambda nv: m.group(0) if nv is None else f'<c r="{m.group(1)}{m.group(2)}"{m.group(3)} t="inlineStr"><is><t>{nv}</t></is></c>')(remap(m.group(1), int(m.group(2)), SST[int(m.group(4))].strip())), s2)
s2 = re.sub(r'<c r="([AB])(\d+)"((?: s="\d+")?) t="inlineStr"><is><t>(\d+)</t></is></c>',
            lambda m: (lambda nv: m.group(0) if nv is None else f'<c r="{m.group(1)}{m.group(2)}"{m.group(3)} t="inlineStr"><is><t>{nv}</t></is></c>')(remap(m.group(1), int(m.group(2)), m.group(4))), s2)
s2 = re.sub(r'<c r="([AB])(\d+)"((?: s="\d+")?)><v>(\d+)</v></c>',
            lambda m: (lambda nv: m.group(0) if nv is None else f'<c r="{m.group(1)}{m.group(2)}"{m.group(3)}><v>{nv}</v></c>')(remap(m.group(1), int(m.group(2)), m.group(4))), s2)
wr("xl/worksheets/sheet2.xml", s2)

s3 = rd("xl/worksheets/sheet3.xml")
existing = set(re.findall(r"QTGC-(SD-[A-Z]+-\d+)\"\)</f>", s3))
last = max(int(x) for x in re.findall(r'<row r="(\d+)"', s3))
num = len(re.findall(r'<row r="\d+"', s3)) - 1
rows, r = [], last
for ref, fid in F.items():
    if ref in existing:
        continue
    r += 1; num += 1
    url = DRV + fid
    use = PLAN.get("uses", {}).get(ref, "")
    rows.append(f'<row r="{r}" spans="1:6" ht="30" x14ac:dyDescent="0.25"><c r="A{r}" s="51"><v>{num}</v></c>'
                f'<c r="B{r}" s="51" t="str"><f>{escape(f"HYPERLINK(\"{url}\",\"{PRE}{ref}\")")}</f><v>{PRE}{ref}</v></c>'
                f'<c r="C{r}" s="51" t="inlineStr"><is><t>{ref.split("-")[1]}</t></is></c>'
                f'<c r="D{r}" s="51" t="str"><f>{escape(f"HYPERLINK(\"{url}\",\"Open folder\")")}</f><v>Open folder</v></c>'
                f'<c r="E{r}" s="51" t="inlineStr"><is><t>{url}</t></is></c>'
                f'<c r="F{r}" s="51" t="inlineStr"><is><t>{escape(use)}</t></is></c></row>')
s3 = s3.replace("</sheetData>", "".join(rows) + "</sheetData>", 1)
s3 = re.sub(r'<autoFilter ref="A1:F\d+"', f'<autoFilter ref="A1:F{r}"', s3)
s3 = re.sub(r'<dimension ref="A1:F\d+"', f'<dimension ref="A1:F{r}"', s3)
wr("xl/worksheets/sheet3.xml", s3)

with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(P("[Content_Types].xml"), "[Content_Types].xml")
    for root, _, files in os.walk(X):
        for f in files:
            full = os.path.join(root, f)
            arc = os.path.relpath(full, X)
            if arc != "[Content_Types].xml":
                z.write(full, arc)
shutil.rmtree(X, ignore_errors=True)
print(json.dumps({"rows_added": sum(len(b["rows"]) for b in PLAN["insert"]), "si_count": counter[0],
                  "drive_links_added": len(rows), "arch_heading_row": arch}))
