"""Build tree.json for tools/build_ifc.py from a listing of the IFC folder plus Drive id maps
(drive_folders.json: path->folder id, drive_files.json: id->{t,p,s}). Run once; the IFC set is fixed."""
import re,json,collections,sys
SRC=sys.argv[1] if len(sys.argv)>1 else 'ifc_files.tsv'  # size<TAB>relative path, one line per file
JUNK=re.compile(r'\.(bak|dwl2?|db|log|pcp|exe|dib)$',re.I)
FMT={'DWG','PDF','CAD'}
def key(s):  # merge "2- ELEVATION" / "2-ELEVATION", "0015 - X" / "0015-X"
    return re.sub(r'\s+',' ',re.sub(r'\s*-\s*','-',s)).strip().upper()
def label(s):
    s=re.sub(r'^\d{2}\.\s*','',s)               # "01. Architecture"
    s=re.sub(r'\s*-\s*',' – ',s,count=1) if re.match(r'^\d+\s*-',s) else s
    s=re.sub(r'\s+',' ',s).strip()
    return s
def stem(fn): return fn.rsplit('.',1)[0].strip()
root={'n':'IFC Package','k':'','c':{},'f':{},'rp':['']}
DF=json.load(open('drive_folders.json')); DFI=json.load(open('drive_files.json'))
FID={}
for k,v in DFI.items(): FID[(v['p'],v['t'])]=k
ROOTID='1Z8WQvpyOY9JgDDhKexO2ag2ujKcGv08e'
order=[]
for line in open(SRC,encoding='utf-8'):
    size,path=line.rstrip('\n').split('\t',1)
    parts=path.split('/'); fn=parts[-1]
    if JUNK.search(fn) or fn.startswith('._'): continue
    if re.search(r'\.(jpe?g|png)$',fn,re.I) and any(p.upper() in ('DWG','CAD') for p in parts[:-1]): continue
    node=root
    for j,p in enumerate(parts[:-1]):
        if p.upper() in FMT: continue
        k=key(p)
        if k not in node['c']: node['c'][k]={'n':label(p),'raw':p,'c':{},'f':{},'rp':[]}
        node=node['c'][k]
        rp='/'.join(parts[:j+1])
        if rp not in node['rp']: node['rp'].append(rp)
    ext=fn.rsplit('.',1)[-1].lower() if '.' in fn else ''
    st=stem(fn)
    d='/'.join(parts[:-1]); pid=DF[d] if d else ROOTID
    fid=FID[(pid,fn)]
    node['f'].setdefault(st,{})[ext]={'p':path,'s':int(size),'u':'https://drive.google.com/file/d/'+fid+'/view'}
def conv(node):
    kids=sorted(node['c'].values(),key=lambda x:x['raw'].upper())
    files=[]
    for st in sorted(node['f']):
        v=node['f'][st]; files.append({'t':st,'x':{e:{'p':d['p'],'s':d['s'],'u':d['u']} for e,d in sorted(v.items())}})
    out={'n':node['n'],'d':[conv(k) for k in kids],'f':files}
    rps=node.get('rp',[])
    pick=next((r for r in rps if '/PDF/' in '/'+r+'/' or r.upper().endswith('/PDF')), rps[0] if rps else '')
    fid=DF.get(pick) if pick else ROOTID
    if fid: out['u']='https://drive.google.com/drive/folders/'+fid
    return out
T=conv(root)
def stats(n):
    c=collections.Counter()
    for f in n['f']:
        for e in f['x']: c[e]+=1
    for d in n['d']:
        c+=stats(d)
    n['cnt']=dict(c); return c
stats(T)
json.dump(T,open('tree.json','w'),ensure_ascii=False)
def pr(n,d=0,maxd=4):
    if d>maxd: return
    print('  '*d+f"{n['n']}  [{len(n['f'])} drawings] {n['cnt']}")
    for k in n['d']: pr(k,d+1,maxd)
pr(T,0,1)
nodes=0;leafs=0
def walk(n):
    global nodes,leafs
    nodes+=1; leafs+=len(n['f'])
    for k in n['d']: walk(k)
walk(T); print('folders',nodes,'drawing rows',leafs)
