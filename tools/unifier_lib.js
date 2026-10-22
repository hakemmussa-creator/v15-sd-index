/* V15 Unifier daily helper - loaded into the logged-in Unifier tab (unifier.emaar.ae) by the Claude routine:
     eval(await (await fetch('https://raw.githubusercontent.com/hakemmussa-creator/v15-sd-index/main/tools/unifier_lib.js?'+Date.now(),{cache:'no-store'})).text())
   Read-only in Unifier: it only reads the logs/attachments and downloads files. No secrets in this file: the
   session token is read from the page at run time and never returned.
   State (localStorage on unifier.emaar.ae): claude_v15_unifier_state / claude_v15_rfi_state (baselines),
   claude_v15_sta (status map as last published), claude_v15_filed (file names already filed in Drive),
   claude_v15_trk (Rejected Tracker rows). Download folder handle: IndexedDB claude_v15/kv 'dir'.
   API (all return small JSON):
     await V15.init()        -> {loggedIn}
     await V15.check()       -> report (events, status diff, new refs, downloads, tracker ops, counts)
     await V15.dl()          -> starts downloads into the remembered folder, or shows the red button if a click is needed
     V15.prog()              -> download progress
     V15.commit()            -> saves baselines/status/filed/tracker after filing + publishing were verified
     V15.pack(obj) / V15.part(i) -> move a big result out in 950-char slices (tool output limits)
     await V15.hashM(), await V15.seed(trk) -> one-time seeding after check() (status map, tracker map, filed list)
*/
(function () {
  const PRJ = '5224', UID = '11877';
  const K = { base: 'claude_v15_unifier_state', rfi: 'claude_v15_rfi_state', sta: 'claude_v15_sta', filed: 'claude_v15_filed', trk: 'claude_v15_trk' };
  const H = { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' };
  const inScope = r => /^GPD-V15-QTGC-(PQN-|MAS-|SD-(ARC|ID|STR|RCP|EL)-)/.test(r);
  const key = r => r.replace(/^GPD-V1?5?-QTGC-/, '');
  const ref0 = x => (x.ugenReferenceNoTB128 || '').trim();
  const rn = s => +((String(s || '').match(/\d+/) || [0])[0]);
  const L = s => { const c = String(s || '').trim().charAt(0).toUpperCase(); return c && 'ABCDEF'.includes(c) ? c : null; };
  const frev = (n, ref) => { const x = n.replace(ref, ''); const m = x.match(/Rev\s*[.\-_ ]*\s*0*(\d+)/i) || x.match(/\bR\s*0*(\d{1,2})\b/i); return m ? +m[1] : null; };
  const ld = k => { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } };
  const sv = (k, v) => localStorage.setItem(k, JSON.stringify(v));
  const day = d => (d || '').slice(0, 10);
  const szB = s => { const m = String(s || '').match(/([\d.]+)\s*(KB|MB|GB|B)?/i); if (!m) return 0; const v = +m[1], u = (m[2] || 'B').toUpperCase(); return u === 'GB' ? v * 1073741824 : u === 'MB' ? v * 1048576 : u === 'KB' ? v * 1024 : v; };
  const okSize = (a, b) => !b || Math.abs(a - b) <= Math.max(b * 0.01, 2048);
  const MEAN = { C: 'C – Not approved, resubmit', D: 'D – Incomplete, resubmit', F: 'F – Approved w/ comments, resubmit', W: 'Awaiting consultant response', RC: 'C – RFI response not accepted', RS: 'Resubmitted – under review', CL: 'Closed – approved' };
  const cleanT = t => String(t || '').replace(/^\s*(SHOP DRAWING FOR|MATERIAL SUBMITTAL FOR|PRE[ -]?QUALIFICATION FOR)\s*/i, '').replace(/\s+/g, ' ').trim();
  const logOf = k => k.startsWith('SD-') ? 'SD' : k.split('-')[0];
  const V = { ver: '2026-10-22a' };

  V.init = async function () {
    for (let i = 0; i < 12; i++) {
      const f = [...document.querySelectorAll('iframe')].find(f => { try { return /"token":"/.test(f.contentDocument.documentElement.innerHTML); } catch (e) { return false; } });
      if (f) { const h = f.contentDocument.documentElement.innerHTML; V.TOK = h.match(/"token":"([^"]+)"/)[1]; V.UREF = h.match(/"uref":"([^"]+)"/)[1]; return { loggedIn: true, ver: V.ver }; }
      await new Promise(r => setTimeout(r, 2000));
    }
    return { loggedIn: false, ver: V.ver };
  };
  V.q = async (model, vid) => {
    const p = new URLSearchParams({ statusRecSet: 'All', statusRecSet_operator: 'eq', statuswfstatus: 'All', statuswfstatus_operator: 'eq', logtype: 'bplog', src_model: model, isPlanningSheet: 'null', model, bulk: '', admin_updates: '', hidden_view_id: String(vid), hidden_view_type: 'filter', hidden_sortby: '[{"dataIndex":"record_no","order":"dsc"}]', hidden_groupby: '[]', page: '1', size: '9000', __token: V.TOK, __uref: V.UREF });
    return (await (await fetch('/bp/mod/bp/log_query', { method: 'POST', headers: H, body: p })).json()).data || [];
  };
  V.att = async (model, id) => {
    const r = await fetch('/bp/mod/wf/tasks/attachlog_query', { method: 'POST', headers: H, body: new URLSearchParams({ log_type: 'bplog', project_id: PRJ, user_id: UID, modelname: model, sourceid: String(id), hiddentabs_attachments: '', hiddenUpper: 'false', __token: V.TOK, __uref: V.UREF }) });
    return ((await r.json()).data || []).filter(d => d.itemType === 'FILE').map(d => ({ n: d.file_name, fid: d.fileid, rl: d.recordline_id, sig: d.signature, sz: d.file_size }));
  };
  V.pool = async (items, fn, n = 6) => { const out = new Array(items.length); let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) { const j = i++; try { out[j] = await fn(items[j]); } catch (e) { out[j] = null; } } })); return out; };
  const latest = (arr, f) => { const m = {}; for (const x of arr) { const r = ref0(x); if (!f(r)) continue; const c = m[r]; if (!c || rn(x.uuu_revision_no) > rn(c.uuu_revision_no) || (rn(x.uuu_revision_no) === rn(c.uuu_revision_no) && x.record_no > c.record_no)) m[r] = x; } return m; };
  const subL = x => x.status === 'Pending_By_Engineer' ? 'U' : (L(x.employer_status) || L(x.Consustatuts) || (x.status === 'Approved' ? 'A' : 'U'));
  // latest-rev files of one record: originals, consultant responses, 'for EMEP review' copies
  const want = (files, ref, rev) => {
    const lat = (files || []).filter(f => { const r = frev(f.n, ref); return r === rev || (r === null && /Respon/i.test(f.n)); });
    const resp = lat.filter(f => /Respon/i.test(f.n)), emep = lat.filter(f => !/Respon/i.test(f.n) && /EMEP/i.test(f.n));
    return { orig: lat.filter(f => !/Respon|EMEP/i.test(f.n)), resp, reply: resp.length ? resp : emep };
  };
  const rfiC = w => w.resp.some(f => /-\s*C\s*\.[a-z0-9]+$/i.test(f.n));

  V.check = async function () {
    if (!V.TOK) { const i = await V.init(); if (!i.loggedIn) return { loggedIn: false }; }
    let S, R;
    try { S = await V.q('uxsubsmc', 2687); R = await V.q('urfi', 340); } catch (e) { return { loggedIn: false, err: 'log_query failed' }; }
    const BS = ld(K.base) || { records: {} }, BR = ld(K.rfi) || { records: {} };
    const STA = (ld(K.sta) || { map: {} }).map, FILED = new Set(ld(K.filed) || []), TRK = (ld(K.trk) || { map: {} }).map;
    const LS = latest(S, inScope), LR = latest(R, () => true);
    const cut = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
    // 1) what changed in the logs since the last committed baseline
    const chg = new Set();
    for (const x of S) {
      const r = ref0(x); if (!inScope(r)) continue;
      const b = (BS.records[key(r)] || {})[x.record_no];
      if (!b) { chg.add(r); continue; }
      const [rev, st, bcs, bed] = b;
      if (rev !== x.uuu_revision_no || st !== x.status || (bcs && bcs !== (x.Consustatuts || '')) || (bed || '') !== day(x.end_date)) chg.add(r);
    }
    for (const x of R) {
      const r = ref0(x), b = (BR.records[r] || {})[x.record_no];
      if (!b || b[0] !== x.uuu_revision_no || b[1] !== x.status || (b[2] || '') !== day(x.end_date)) chg.add(r);
    }
    // 2) attachments: every RFI (status R/W needs them) + submittals that changed or moved in the last 30 days
    const cand = [];
    for (const [r, x] of Object.entries(LS)) if (chg.has(r) || (x.status !== 'Pending_By_Engineer' && (day(x.uuu_creation_date) >= cut || day(x.end_date) >= cut))) cand.push(['uxsubsmc', r, x]);
    for (const [r, x] of Object.entries(LR)) cand.push(['urfi', r, x]);
    const files = await V.pool(cand, c => V.att(c[0], c[2].id));
    const A = {}; cand.forEach((c, i) => A[c[1]] = files[i]);
    const attErr = cand.filter((c, i) => files[i] === null).map(c => key(c[1]));
    // 3) status map (what the pages show)
    const M = {};
    for (const [r, x] of Object.entries(LS)) M[key(r)] = [subL(x), rn(x.uuu_revision_no)];
    const RW = {};
    for (const [r, x] of Object.entries(LR)) {
      const rev = rn(x.uuu_revision_no);
      let has;
      if (A[r]) { const w = want(A[r], r, rev); has = w.resp.length > 0; RW[r] = w; } else has = !!((BR.records[r] || {})[x.record_no] || [])[3];
      M[key(r)] = [has ? 'R' : 'W', rev];
    }
    const st = {}; for (const [k, v] of Object.entries(M)) { const o = STA[k]; if (!o || o[0] !== v[0] || o[1] !== v[1]) st[k] = v; }
    // 4) downloads = latest-rev originals + replies not yet filed
    const jobs = [];
    for (const [model, r, x] of cand) {
      if (!A[r]) continue;
      const w = want(A[r], r, rn(x.uuu_revision_no));
      for (const f of [...w.orig, ...w.reply]) if (!FILED.has(f.n)) jobs.push({ ref: r, model, name: f.n, recId: x.id, fid: f.fid, rl: f.rl, sig: f.sig, sz: f.sz });
    }
    V.jobs = jobs;
    // 5) Updates-panel events (one per ref whose shown status/rev changed or that got new files)
    const jobRefs = new Set(jobs.map(j => j.ref));
    const ev = [], newSub = [], newSD = [];
    const all = [...Object.entries(LS).map(([r, x]) => ['S', r, x]), ...Object.entries(LR).map(([r, x]) => ['R', r, x])];
    for (const [t, r, x] of all) {
      const k = key(r), now = M[k], old = STA[k];
      if (!jobRefs.has(r) && old && old[0] === now[0] && old[1] === now[1]) continue;
      if (!jobRefs.has(r) && !chg.has(r)) continue;
      const rev = rn(x.uuu_revision_no), title = t === 'S' ? cleanT(x.record_title) : (String(x.site_inst_subj || '').trim() || 'RFI – no subject entered in Unifier');
      const fs = jobs.filter(j => j.ref === r).map(j => j.name);
      let kd, n;
      if (t === 'S') {
        if (now[0] === 'U') { kd = 'new'; n = rev > 0 ? 'Rev.' + String(rev).padStart(2, '0') + ' submitted – under consultant review' : 'New submission – under consultant review'; }
        else { kd = 'reply'; n = (x.employer_status && L(x.employer_status) ? 'Employer (ER) response – code ' : 'Consultant response received – code ') + now[0]; }
      } else {
        if (now[0] === 'W') { kd = 'new'; n = 'New RFI – awaiting consultant response'; }
        else { kd = 'reply'; n = 'Consultant response received' + (RW[r] && rfiC(RW[r]) ? ' – code C' : ''); }
      }
      ev.push({ r: k, rev: x.uuu_revision_no, t: title, k: kd, n, f: fs, log: logOf(k) });
      if (!old) { if (k.startsWith('SD-')) newSD.push({ r: k, rev: x.uuu_revision_no, t: title }); else newSub.push({ ref: r, rev: x.uuu_revision_no, title: t === 'S' ? String(x.record_title || '').trim() : title }); }
    }
    // 6) Rejected Tracker operations
    const open = {};
    for (const [r, x] of Object.entries(LS)) { const c = subL(x); if ('CDF'.includes(c)) open[r] = { code: c, x, log: logOf(key(r)) }; }
    for (const [r, x] of Object.entries(LR)) { const w = RW[r]; const has = M[key(r)][0] === 'R'; if (!has) open[r] = { code: 'W', x, log: 'RFI' }; else if (w && rfiC(w)) open[r] = { code: 'C', x, log: 'RFI' }; }
    const trk = [], T2 = Object.assign({}, TRK);
    const rowOf = (r, o) => { const x = o.x; return { log: { SD: 'SD (Drawing)' }[o.log] || o.log, ref: r, disc: x.ugenDiscipline || '', title: o.log === 'RFI' ? (String(x.site_inst_subj || '').trim() || 'RFI – no subject entered in Unifier') : cleanT(x.record_title), rev: x.uuu_revision_no, code: o.code, status: o.log === 'RFI' && o.code === 'C' ? MEAN.RC : MEAN[o.code], by: (x.employer_status && L(x.employer_status)) ? 'Employer (ER)' : 'Consultant', sub: day(x.uuu_creation_date) }; };
    for (const [r, o] of Object.entries(open)) {
      const t = TRK[r], v = [o.x.uuu_revision_no, o.code, 'open'];
      if (!t) { trk.push(['add', rowOf(r, o)]); T2[r] = v; }
      else if (t[2] !== 'open' || t[0] !== v[0] || t[1] !== v[1]) { trk.push(['upd', rowOf(r, o)]); T2[r] = v; }
    }
    for (const [r, t] of Object.entries(TRK)) {
      if (open[r] || t[2] === 'closed') continue;
      const x = LS[r] || LR[r]; if (!x) continue;
      const kind = (M[key(r)][0] === 'U') ? 'rs' : 'closed';
      if (kind !== t[2]) { trk.push([kind, { ref: r, status: kind === 'rs' ? MEAN.RS : MEAN.CL }]); T2[r] = [t[0], t[1], kind]; }
    }
    V.last = { S, R, M, T2, files: A, at: new Date().toISOString() };
    const mb = jobs.reduce((a, j) => a + szB(j.sz), 0) / 1048576;
    return {
      loggedIn: true, ver: V.ver, n: [S.length, R.length], ev, st, newSD, newSub,
      dl: jobs.map(j => key(j.ref) + ' | ' + j.name.replace(j.ref, '~')), mb: Math.round(mb * 10) / 10,
      trk, pe: Object.values(LS).filter(x => x.status === 'Pending_By_Engineer').length,
      rw: Object.entries(LR).filter(([r]) => M[key(r)][0] === 'W').map(([r]) => key(r)),
      openN: Object.keys(open).length, attErr, seeded: !!ld(K.sta) && !!ld(K.filed) && !!ld(K.trk)
    };
  };

  // ---- download folder (remembered handle; no click once Chrome has 'Allow on every visit') ----
  const idb = (mode, fn) => new Promise((res, rej) => { const o = indexedDB.open('claude_v15', 1); o.onupgradeneeded = () => o.result.createObjectStore('kv'); o.onerror = () => rej(o.error); o.onsuccess = () => { const tx = o.result.transaction('kv', mode); const st = tx.objectStore('kv'); const rq = fn(st); tx.oncomplete = () => res(rq && rq.result); tx.onerror = () => rej(tx.error); }; });
  V.dirState = async () => { const h = await idb('readonly', s => s.get('dir')); if (!h) return { state: 'none' }; return { state: await h.queryPermission({ mode: 'readwrite' }), name: h.name }; };
  V.prog = () => { const p = V.P || {}; return { state: p.state || 'idle', done: p.done || 0, total: p.total || 0, ok: (p.ok || []).length, skip: (p.skip || []).length, fail: (p.fail || []).map(n => n.replace(/^GPD-V1?5?-QTGC-/, '')), dir: p.dir || '' }; };
  async function dl1(j, dir) {
    const exp = szB(j.sz), sub = await dir.getDirectoryHandle(j.ref, { create: true });
    try { const f = await (await sub.getFileHandle(j.name)).getFile(); if (f.size > 0 && okSize(f.size, exp)) return 'skip'; } catch (e) { }
    for (let a = 0; a < 8; a++) {
      try {
        const it = (await V.att(j.model, j.recId)).find(d => d.fid == j.fid) || {};
        const p = new URLSearchParams({ __token: V.TOK, __uref: V.UREF, from: 'attachment', fileids: String(j.fid), isLineitem: 'true', recordIds: String(it.rl || j.rl), model: j.model, signs: it.sig || j.sig, ids: String(j.fid) });
        const res = await fetch('/bp/sys/dm/new/download', { method: 'POST', headers: H, body: p });
        if (res.status !== 200 || /html|json/i.test(res.headers.get('content-type') || '')) throw new Error('bad');
        const fh = await sub.getFileHandle(j.name, { create: true }), w = await fh.createWritable();
        await res.body.pipeTo(w);
        if (!okSize((await fh.getFile()).size, exp)) throw new Error('size');
        return 'ok';
      } catch (e) { await new Promise(r => setTimeout(r, 1500)); }
    }
    return 'fail';
  }
  async function runJobs(dir) {
    const P = V.P = { state: 'running', done: 0, total: V.jobs.length, ok: [], skip: [], fail: [], dir: dir.name };
    for (const j of V.jobs) { const r = await dl1(j, dir); P[r === 'ok' ? 'ok' : r === 'skip' ? 'skip' : 'fail'].push(j.name); P.done++; btnText(); }
    P.state = 'done'; btnText();
  }
  function btnText() { const b = document.getElementById('__v15dl'); if (!b || !V.P) return; const p = V.P; b.textContent = p.state === 'done' ? (p.fail.length ? 'Done – ' + p.fail.length + ' failed' : 'All ' + p.total + ' downloaded') : p.done + '/' + p.total; if (p.state === 'done') { b.style.background = p.fail.length ? '#e80' : '#090'; setTimeout(() => b.remove(), 8000); } }
  V.dl = async function () {
    if (!V.jobs || !V.jobs.length) return { state: 'nothing' };
    const h = await idb('readonly', s => s.get('dir'));
    if (h && await h.queryPermission({ mode: 'readwrite' }) === 'granted') { runJobs(h); return { state: 'running', dir: h.name, total: V.jobs.length }; }
    document.getElementById('__v15dl')?.remove();
    const b = document.createElement('button'); b.id = '__v15dl';
    b.style.cssText = 'position:fixed;top:12px;right:12px;z-index:2147483647;background:#d00;color:#fff;font:bold 16px sans-serif;padding:14px 20px;border:0;border-radius:8px;box-shadow:0 2px 8px #0006;cursor:pointer';
    b.textContent = h ? 'Click once – then choose "Allow on every visit"' : 'Choose the V15 download folder (one time)';
    b.onclick = async () => {
      try {
        let d = h;
        if (!d) { d = await showDirectoryPicker({ mode: 'readwrite', id: 'v15dl', startIn: 'desktop' }); await idb('readwrite', s => s.put(d, 'dir')); }
        if (await d.requestPermission({ mode: 'readwrite' }) !== 'granted') { b.textContent = 'Permission refused – click again'; return; }
        runJobs(d);
      } catch (e) { b.textContent = 'Click again – choose the folder'; }
    };
    document.body.appendChild(b);
    return { state: 'needsClick', why: h ? 'permission' : 'nofolder', total: V.jobs.length };
  };

  // ---- save state (call only after filing in Drive + publishing are verified) ----
  V.commit = function (extraFiled, exclude) {
    const l = V.last; if (!l) return { saved: false, why: 'run check() first' };
    const now = new Date().toISOString();
    const s = { saved: now, records: {} }, r = { saved: now, records: {} };
    for (const x of l.S) { const rf = ref0(x); if (!inScope(rf)) continue; (s.records[key(rf)] = s.records[key(rf)] || {})[x.record_no] = [x.uuu_revision_no, x.status, x.Consustatuts || '', day(x.end_date)]; }
    const BR = ld(K.rfi) || { records: {} };
    for (const x of l.R) { const rf = ref0(x), old = (BR.records[rf] || {})[x.record_no]; const has = l.M[key(rf)][0] === 'R' ? 1 : 0; (r.records[rf] = r.records[rf] || {})[x.record_no] = [x.uuu_revision_no, x.status, day(x.end_date), old ? Math.max(old[3], has) : has]; }
    const F = new Set(ld(K.filed) || []); const ex = new Set(exclude || []); (V.jobs || []).forEach(j => { if (!ex.has(j.name)) F.add(j.name); }); (extraFiled || []).forEach(n => F.add(n));
    sv(K.base, s); sv(K.rfi, r); sv(K.sta, { saved: now, map: l.M }); sv(K.filed, [...F]); sv(K.trk, { saved: now, map: l.T2 });
    return { saved: true, subs: Object.keys(s.records).length, rfis: Object.keys(r.records).length, filed: F.size };
  };

  // ---- one-time seeding: run check() first, compare V15.hashM() with the published status map, then seed(trk) ----
  V.hashM = async function () {
    const M = V.last.M, s = JSON.stringify(Object.keys(M).sort().map(k => [k, M[k]]));
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
  };
  V.seed = async function (trk) {
    if (!V.last) return { started: false, why: 'run check() first' };
    sv(K.sta, { saved: new Date().toISOString(), map: V.last.M });
    if (trk) sv(K.trk, { saved: new Date().toISOString(), map: trk });
    V.SP = { done: 0, total: 0, state: 'running' };
    (async () => {
      const recs = [...Object.entries(latest(V.last.S, inScope)).map(([r, x]) => ['uxsubsmc', r, x]), ...Object.entries(latest(V.last.R, () => true)).map(([r, x]) => ['urfi', r, x])];
      V.SP.total = recs.length; const F = new Set(ld(K.filed) || []);
      await V.pool(recs, async c => { const w = want(await V.att(c[0], c[2].id), c[1], rn(c[2].uuu_revision_no)); [...w.orig, ...w.reply].forEach(f => F.add(f.n)); V.SP.done++; });
      sv(K.filed, [...F]); V.SP.state = 'done'; V.SP.filed = F.size;
    })();
    return { started: true };
  };
  V.seedProg = () => V.SP || {};
  // report transport: the browser tool blocks '=', '?', '&' and cuts output near 1000 chars
  V.pack = o => { V.C = JSON.stringify(o).replace(/&/g, '\\u0026').replace(/=/g, '\\u003d').replace(/\?/g, '\\u003f'); return Math.ceil(V.C.length / 950); };
  V.part = i => V.C.slice(i * 950, (i + 1) * 950);
  window.V15 = V;
})();
'V15 ' + V15.ver;
