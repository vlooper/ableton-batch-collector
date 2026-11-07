#!/usr/bin/env python3
"""
📦 Ableton Batch - Collect All and Save
============================
Batch "Collect All and Save" for Ableton Live projects.
Opens in your browser — zero dependencies!

Usage:
    python3 ableton_batch_collector.py
"""

import gzip
import xml.etree.ElementTree as ET
import os
import sys
import json
import shutil
import subprocess
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from datetime import datetime

APP_VERSION = "1.2.0"
PORT = 7865
COLLECTED_FOLDER_NAME = "Samples/Collected"
MEDIA_EXTENSIONS = {
    '.wav', '.aif', '.aiff', '.mp3', '.flac', '.ogg', '.m4a', '.wma',
    '.rex', '.rx2', '.sd2', '.mp4', '.mov', '.avi', '.m4v',
}
SKIP_PATH_TYPES = {'3', '5'}

state = {
    'running': False, 'cancel': False, 'logs': [], 'progress': 0,
    'progress_text': 'Ready', 'stats': {'sessions': 0, 'collected': 0, 'missing': 0},
    'done': False, 'done_msg': '', 'done_type': 'ok',
}
state_lock = threading.Lock()

def push_log(msg, tag="info"):
    with state_lock: state['logs'].append({'msg': msg, 'tag': tag})

def set_progress(pct, text=""):
    with state_lock:
        state['progress'] = pct
        if text: state['progress_text'] = text

def set_stats(s, c, m):
    with state_lock: state['stats'] = {'sessions': s, 'collected': c, 'missing': m}

# ─── NATIVE FOLDER PICKER ───

def pick_folder():
    """Open the native macOS folder picker dialog."""
    try:
        result = subprocess.run(
            ['osascript', '-e', 'POSIX path of (choose folder with prompt "Select your Ableton projects folder")'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            path = result.stdout.strip().rstrip('/')
            return path
    except:
        pass
    return None

# ─── ENGINE ───

def decompress_als(p):
    with gzip.open(p, 'rb') as f: return f.read()

def compress_als(b, p):
    with gzip.open(p, 'wb') as f: f.write(b)

def backup_als(p):
    bak = p + '.bak'
    if not os.path.exists(bak): shutil.copy2(p, bak)

def is_skip(fr):
    rpt = fr.find('RelativePathType')
    if rpt is not None and rpt.get('Value', '') in SKIP_PATH_TYPES: return True
    lpn = fr.find('LivePackName')
    if lpn is not None and lpn.get('Value', '').strip(): return True
    pe = fr.find('Path')
    if pe is not None:
        pv = pe.get('Value', '')
        if '/Ableton Live' in pv and '/App-Resources/' in pv: return True
    return False

def get_paths(fr, pd):
    ap, fn = None, None
    pe = fr.find('Path')
    if pe is not None:
        pv = pe.get('Value', '').strip()
        if pv and os.path.isabs(pv): ap, fn = pv, os.path.basename(pv)
    if ap is None or not os.path.isfile(ap):
        rpe = fr.find('RelativePath')
        if rpe is not None:
            rv = rpe.get('Value', '').strip()
            if rv:
                c = os.path.normpath(os.path.join(pd, rv))
                if os.path.isfile(c): ap, fn = c, os.path.basename(c)
                elif ap is None:
                    ap = pe.get('Value', '') if pe is not None else rv
                    fn = os.path.basename(rv)
    return ap, fn

def inside_proj(fp, pd):
    try: return os.path.realpath(fp).startswith(os.path.realpath(pd) + os.sep)
    except: return False

def uniq_dest(dd, fn):
    d = os.path.join(dd, fn)
    if not os.path.exists(d): return d
    b, e = os.path.splitext(fn)
    c = 1
    while True:
        d = os.path.join(dd, f"{b}_{c}{e}")
        if not os.path.exists(d): return d
        c += 1

def update_ref(fr, nrp, pd):
    nap = os.path.normpath(os.path.join(pd, nrp))
    pe = fr.find('Path')
    if pe is not None: pe.set('Value', nap)
    rpe = fr.find('RelativePath')
    if rpe is not None: rpe.set('Value', nrp)
    rpt = fr.find('RelativePathType')
    if rpt is not None: rpt.set('Value', '1')

def find_refs(root):
    refs, seen = [], set()
    for fr in root.iter('FileRef'):
        if is_skip(fr): continue
        pe, rpe = fr.find('Path'), fr.find('RelativePath')
        fn, cp = None, None
        if pe is not None:
            pv = pe.get('Value', '')
            if pv: fn, cp = os.path.basename(pv), pv
        if fn is None and rpe is not None:
            rv = rpe.get('Value', '')
            if rv: fn, cp = os.path.basename(rv), rv
        if not fn: continue
        ext = os.path.splitext(fn)[1].lower()
        if ext not in MEDIA_EXTENSIONS: continue
        if cp and cp not in seen:
            seen.add(cp)
            refs.append(fr)
    return refs

def get_proj_folder(ap):
    cur = os.path.dirname(os.path.abspath(ap))
    for _ in range(3):
        if os.path.isdir(os.path.join(cur, 'Ableton Project Info')): return cur
        p = os.path.dirname(cur)
        if p == cur: break
        cur = p
    return os.path.dirname(os.path.abspath(ap))

def find_als(rd):
    als = []
    for dp, dn, fn in os.walk(rd):
        dn[:] = [d for d in dn if d not in ('Backup', 'Trash', '.Trash')]
        for f in fn:
            if f.endswith('.als') and not f.startswith('.'):
                als.append(os.path.join(dp, f))
    return sorted(als)

def fmt_size(b):
    for u in ['B','KB','MB','GB','TB']:
        if b < 1024.0: return f"{b:.1f} {u}"
        b /= 1024.0
    return f"{b:.1f} PB"

def process_als(ap, dry=False):
    st = {'refs': 0, 'collected': 0, 'local': 0, 'missing': 0, 'errors': [], 'bytes': 0}
    pd = os.path.dirname(os.path.abspath(ap))
    cd = os.path.join(pd, COLLECTED_FOLDER_NAME)
    try:
        xd = decompress_als(ap)
        root = ET.fromstring(xd)
    except Exception as e:
        st['errors'].append(str(e)); return st
    frs = find_refs(root)
    st['refs'] = len(frs)
    mod = False
    for fr in frs:
        ap2, fn = get_paths(fr, pd)
        if not ap2 or not fn: st['missing'] += 1; continue
        if os.path.isfile(ap2) and inside_proj(ap2, pd): st['local'] += 1; continue
        if not os.path.isfile(ap2): st['missing'] += 1; continue
        if not dry:
            os.makedirs(cd, exist_ok=True)
            dp = uniq_dest(cd, fn)
            try:
                shutil.copy2(ap2, dp)
                st['bytes'] += os.path.getsize(dp)
            except Exception as e:
                st['errors'].append(str(e)); continue
            update_ref(fr, os.path.relpath(dp, pd), pd)
            mod = True
        st['collected'] += 1
    if mod and not dry:
        backup_als(ap)
        nx = ET.tostring(root, encoding='unicode', xml_declaration=True)
        compress_als(nx.encode('utf-8'), ap)
    return st

# ─── BACKGROUND TASKS ───

def run_scan(source):
    with state_lock:
        state['running'] = True; state['cancel'] = False
        state['logs'] = []; state['done'] = False
    push_log(f"Scanning {source}...", "info")
    try:
        als = find_als(source)
        if not als:
            push_log("No .als files found in this folder.", "warn")
            set_progress(100, "No sessions found")
            with state_lock:
                state['done'] = True; state['done_type'] = 'warn'
                state['done_msg'] = "No Ableton sessions found"
                state['running'] = False
            return
        projs = {}
        for a in als:
            p = get_proj_folder(a)
            if p not in projs: projs[p] = []
            projs[p].append(a)
        total_refs = 0
        for i, a in enumerate(als):
            if state['cancel']: break
            try:
                xd = decompress_als(a)
                rt = ET.fromstring(xd)
                total_refs += len(find_refs(rt))
            except: pass
            set_progress(int((i+1)/len(als)*100), f"Scanning {i+1}/{len(als)}")
        set_stats(len(als), total_refs, 0)
        push_log("", "info")
        push_log(f"Found {len(als)} sessions in {len(projs)} projects", "success")
        push_log(f"{total_refs:,} total media references", "info")
        push_log("", "info")
        push_log("Ready! Uncheck dry run and hit Collect All.", "success")
        set_progress(100, f"Scan complete — {len(als)} sessions, {total_refs:,} refs")
        with state_lock:
            state['done'] = True
            state['done_msg'] = f"{len(als)} sessions · {len(projs)} projects · {total_refs:,} media refs"
            state['done_type'] = 'scan'
    except Exception as e:
        push_log(f"Error: {e}", "error")
    with state_lock: state['running'] = False

def run_collect(source, dry):
    with state_lock:
        state['running'] = True; state['cancel'] = False
        state['logs'] = []; state['done'] = False
    prefix = "DRY RUN — " if dry else ""
    push_log(f"{prefix}Starting...", "header")
    try:
        als = find_als(source)
        pmap = {}
        for a in als:
            p = get_proj_folder(a)
            if p not in pmap: pmap[p] = []
            pmap[p].append(a)
        totals = {'refs':0,'collected':0,'local':0,'missing':0,'errors':0,'bytes':0}
        si = 0
        start = datetime.now()
        for pi, (pd, al) in enumerate(sorted(pmap.items()), 1):
            if state['cancel']:
                push_log("Cancelled.", "warn"); break
            pn = os.path.basename(pd)
            push_log(pn, "header")
            for ap in al:
                if state['cancel']: break
                si += 1
                an = os.path.basename(ap)
                set_progress(int(si/len(als)*100), f"[{si}/{len(als)}] {an}")
                try: st = process_als(ap, dry)
                except Exception as e:
                    push_log(f"  Error: {an}: {e}", "error")
                    totals['errors'] += 1; continue
                totals['refs'] += st['refs']
                totals['collected'] += st['collected']
                totals['local'] += st['local']
                totals['missing'] += st['missing']
                totals['errors'] += len(st['errors'])
                totals['bytes'] += st['bytes']
                if st['collected'] > 0:
                    push_log(f"  {an}: {st['collected']} collected", "success")
                elif st['missing'] > 0:
                    push_log(f"  {an}: {st['missing']} missing", "warn")
                set_stats(si, totals['collected'], totals['missing'])
        elapsed = str(datetime.now() - start).split('.')[0]
        push_log("", "info")
        push_log("━" * 40, "header")
        push_log(f"{'DRY RUN ' if dry else ''}COMPLETE", "header")
        push_log(f"Sessions: {si} | Collected: {totals['collected']} | Missing: {totals['missing']}", "info")
        if not dry: push_log(f"Data copied: {fmt_size(totals['bytes'])}", "success")
        push_log(f"Time: {elapsed}", "info")
        set_progress(100, f"{'Preview' if dry else 'Done'} — {totals['collected']} files")
        with state_lock:
            state['done'] = True
            state['done_type'] = 'dry' if dry else 'ok'
            state['done_msg'] = f"{totals['collected']} files {'to collect' if dry else 'collected'} · {elapsed}"
            if not dry and totals['bytes'] > 0:
                state['done_msg'] += f" · {fmt_size(totals['bytes'])}"
    except Exception as e:
        push_log(f"Error: {e}", "error")
    with state_lock: state['running'] = False

# ─── HTML ───

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Ableton Batch - Collect All and Save</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,500;0,9..40,700;1,9..40,300&family=JetBrains+Mono:wght@400;500&display=swap');

*{margin:0;padding:0;box-sizing:border-box}
:root{
--bg:#faf7f2;--bgw:#f3eee5;--card:#fff;--brd:#e8e0d4;--brlt:#f0ebe3;
--txt:#2d2a26;--txt2:#8a8278;--dim:#b5ada3;
--acc:#ff6b4a;--accg:rgba(255,107,74,.12);
--grn:#34c759;--grnbg:#eafbef;--ylw:#f5a623;--ylwbg:#fef7e8;--red:#ff3b5c;
--rad:16px;--rads:10px;
}
body{font-family:'DM Sans',-apple-system,sans-serif;background:var(--bg);color:var(--txt);-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--brd);border-radius:3px}
.app{max-width:600px;margin:0 auto;padding:32px 28px 20px}

.header{text-align:center;margin-bottom:28px}
.logo{font-size:48px;display:inline-block;animation:bounce 2.5s ease infinite}
@keyframes bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
.header h1{font-size:22px;font-weight:700;letter-spacing:-.3px;margin-top:4px}
.header p{font-size:13.5px;color:var(--txt2);font-weight:300;margin-top:4px}

/* ── Folder picker ── */
.picker{background:var(--card);border:1px solid var(--brlt);border-radius:var(--rad);padding:20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(45,42,38,.04);transition:.2s}
.picker:hover{box-shadow:0 4px 16px rgba(45,42,38,.06);border-color:var(--brd)}
.picker-label{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--dim);margin-bottom:12px}
.picker-row{display:flex;align-items:center;gap:10px}
.picker-path{flex:1;background:var(--bgw);border:1px solid var(--brlt);border-radius:10px;padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--txt);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-height:44px;display:flex;align-items:center;direction:rtl;text-align:left}
.picker-path.empty{color:var(--dim);font-family:'DM Sans',sans-serif;font-style:italic;font-size:13px;direction:ltr}
.btn-browse{background:var(--acc);color:#fff;border:none;border-radius:10px;padding:12px 22px;font:600 13px 'DM Sans',sans-serif;cursor:pointer;transition:.15s;flex-shrink:0;display:flex;align-items:center;gap:6px;box-shadow:0 2px 10px var(--accg)}
.btn-browse:hover{background:#ff5533;box-shadow:0 4px 16px var(--accg)}
.btn-browse:active{transform:scale(.97)}

/* ── Controls ── */
.toggle-row{display:flex;align-items:center;gap:10px;padding:4px 0;margin-bottom:14px}
.toggle{position:relative;width:44px;height:26px;flex-shrink:0}
.toggle input{display:none}
.toggle-track{position:absolute;inset:0;background:var(--brd);border-radius:13px;cursor:pointer;transition:.25s}
.toggle input:checked+.toggle-track{background:var(--acc)}
.toggle-thumb{position:absolute;top:3px;left:3px;width:20px;height:20px;background:#fff;border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,.15);transition:.25s;pointer-events:none}
.toggle input:checked~.toggle-thumb{transform:translateX(18px)}
.toggle-label{font-size:13px;color:var(--txt2);cursor:pointer;user-select:none}
.dry-badge{display:inline-flex;background:var(--ylwbg);color:var(--ylw);font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;margin-left:6px}
.dry-banner{display:none;background:linear-gradient(135deg,#fff3e0,#ffe0b2);border:2px dashed var(--ylw);border-radius:var(--rad);padding:16px 20px;margin-bottom:14px;text-align:center;animation:pulse-border 2s ease infinite}
.dry-banner.active{display:block}
.dry-banner-icon{font-size:28px;margin-bottom:4px}
.dry-banner-title{font-size:15px;font-weight:700;color:#e65100}
.dry-banner-sub{font-size:12px;color:#bf360c;margin-top:2px}
@keyframes pulse-border{0%,100%{border-color:var(--ylw);box-shadow:0 0 0 0 rgba(245,166,35,0.2)}50%{border-color:#e65100;box-shadow:0 0 16px 4px rgba(245,166,35,0.15)}}

.btn-row{display:flex;gap:8px;margin-bottom:16px}
.btn{padding:12px 24px;border-radius:var(--rads);font:700 13px 'DM Sans',sans-serif;border:none;cursor:pointer;transition:.15s;display:flex;align-items:center;gap:6px}
.btn:active{transform:scale(.97)}
.btn:disabled{opacity:.35;cursor:not-allowed;transform:none}
.btn-primary{background:var(--acc);color:#fff;box-shadow:0 2px 10px var(--accg)}
.btn-primary:hover:not(:disabled){background:#ff5533}
.btn-secondary{background:var(--bgw);color:var(--txt);border:1px solid var(--brd)}
.btn-secondary:hover:not(:disabled){background:var(--brlt)}
.btn-cancel{background:#ffecef;color:var(--red)}

.progress-area{margin-bottom:14px}
.progress-info{display:flex;justify-content:space-between;margin-bottom:6px}
.progress-label{font-size:12px;color:var(--txt2);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.progress-pct{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--acc);font-weight:500;margin-left:8px}
.bar-bg{width:100%;height:6px;background:var(--bgw);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--acc),#ff8a6b);border-radius:3px;width:0%;transition:width .3s}

.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}
.stat{background:var(--card);border:1px solid var(--brlt);border-radius:var(--rads);padding:14px;text-align:center;transition:.2s}
.stat:hover{box-shadow:0 4px 16px rgba(45,42,38,.06)}
.stat-val{font-size:24px;font-weight:700;line-height:1.2}
.stat-val.a{color:var(--acc)}.stat-val.g{color:var(--grn)}.stat-val.y{color:var(--ylw)}
.stat-lbl{font-size:10px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-top:2px}

.summary{display:none;border-radius:var(--rad);padding:20px;margin-bottom:14px;text-align:center;animation:su .35s ease}
.summary.active{display:block}
.summary.ok{background:var(--grnbg);border:1px solid #c6f0d1}
.summary.warn{background:var(--ylwbg);border:1px solid #f0deb0}
.summary.scan{background:#eef0ff;border:1px solid #d0d5f0}
.sum-emoji{font-size:32px;margin-bottom:4px}
.sum-title{font-size:16px;font-weight:700;margin-bottom:3px}
.sum-detail{font-size:12px;color:var(--txt2)}
@keyframes su{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

.log-header{font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--dim);margin-bottom:5px}
.log-box{background:var(--card);border:1px solid var(--brlt);border-radius:var(--rads);padding:10px 14px;height:180px;overflow-y:auto;font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.7}
.l-header{color:var(--txt);font-weight:500}
.l-success{color:var(--grn)}.l-warn{color:var(--ylw)}.l-error{color:var(--red)}.l-info{color:var(--txt2)}

.footer{text-align:center;padding:14px 0 2px;font-size:10px;color:var(--dim)}

/* Loading spinner on browse button */
.btn-browse.loading{pointer-events:none;opacity:.7}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="app">
<div class="header">
<div class="logo">📦</div>
<h1>Ableton Batch - Collect All and Save</h1>
<p>Collect all your samples in one click. No broken links, ever.</p>
</div>

<div class="picker">
<div class="picker-label">📁 Projects folder</div>
<div class="picker-row">
<div class="picker-path empty" id="pathDisplay">No folder selected</div>
<button class="btn-browse" id="browseBtn" onclick="browseFolder()">📂 Browse...</button>
</div>
</div>

<div class="toggle-row">
<label class="toggle"><input type="checkbox" id="dryToggle" checked onchange="toggleDry()"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
<span class="toggle-label" onclick="document.getElementById('dryToggle').click()">Dry run <span class="dry-badge" id="dryBadge">👀 PREVIEW</span></span>
</div>

<div class="dry-banner active" id="dryBanner">
<div class="dry-banner-icon">🚧</div>
<div class="dry-banner-title">DRY RUN MODE — No files will be modified</div>
<div class="dry-banner-sub">Turn off the toggle above to collect for real</div>
</div>

<div class="btn-row">
<button class="btn btn-secondary" id="scanBtn" onclick="doScan()">🔍 Scan</button>
<button class="btn btn-primary" id="collectBtn" onclick="doCollect()">✨ Collect All</button>
<button class="btn btn-cancel" id="cancelBtn" onclick="doCancel()" disabled>Stop</button>
</div>

<div class="progress-area">
<div class="progress-info">
<span class="progress-label" id="progLabel">Ready</span>
<span class="progress-pct" id="progPct">0%</span>
</div>
<div class="bar-bg"><div class="bar-fill" id="progFill"></div></div>
</div>

<div class="stats">
<div class="stat"><div class="stat-val a" id="sSess">0</div><div class="stat-lbl">Sessions</div></div>
<div class="stat"><div class="stat-val g" id="sColl">0</div><div class="stat-lbl">Collected</div></div>
<div class="stat"><div class="stat-val y" id="sMiss">0</div><div class="stat-lbl">Missing</div></div>
</div>

<div class="summary" id="summary">
<div class="sum-emoji" id="sumEmoji"></div>
<div class="sum-title" id="sumTitle"></div>
<div class="sum-detail" id="sumDetail"></div>
</div>

<div class="log-header">📋 Activity log</div>
<div class="log-box" id="logBox"></div>
<div class="footer">v""" + APP_VERSION + r""" · by Vlooper</div>
</div>

<script>
let selectedPath='', lastLogLen=0, polling=null;

async function browseFolder(){
    const btn=document.getElementById('browseBtn');
    btn.classList.add('loading');btn.textContent='Opening...';
    try{
        const res=await fetch('/api/pick-folder');
        const data=await res.json();
        if(data.path){
            selectedPath=data.path;
            const el=document.getElementById('pathDisplay');
            el.textContent=data.path;
            el.classList.remove('empty');
        }
    }catch(e){console.error(e)}
    btn.classList.remove('loading');btn.textContent='📂 Browse...';
}

function toggleDry(){
    const on=document.getElementById('dryToggle').checked;
    document.getElementById('dryBadge').style.display=on?'':'none';
    document.getElementById('dryBanner').classList.toggle('active',on);
}
function setRunning(r){
    document.getElementById('scanBtn').disabled=r;
    document.getElementById('collectBtn').disabled=r;
    document.getElementById('cancelBtn').disabled=!r;
}
function startPolling(){
    if(polling)return;
    polling=setInterval(async()=>{
        try{
            const s=await(await fetch('/api/state')).json();
            document.getElementById('progFill').style.width=s.progress+'%';
            document.getElementById('progPct').textContent=s.progress+'%';
            document.getElementById('progLabel').textContent=s.progress_text;
            document.getElementById('sSess').textContent=s.stats.sessions.toLocaleString();
            document.getElementById('sColl').textContent=s.stats.collected.toLocaleString();
            document.getElementById('sMiss').textContent=s.stats.missing.toLocaleString();
            const box=document.getElementById('logBox');
            if(s.logs.length>lastLogLen){
                for(let i=lastLogLen;i<s.logs.length;i++){
                    const d=document.createElement('div');d.className='l-'+s.logs[i].tag;d.textContent=s.logs[i].msg;box.appendChild(d);
                }
                box.scrollTop=box.scrollHeight;lastLogLen=s.logs.length;
            }
            if(s.done&&!document.getElementById('summary').classList.contains('active')){
                const el=document.getElementById('summary'),t=s.done_type;
                el.className='summary active '+(t==='dry'?'warn':t==='scan'?'scan':'ok');
                document.getElementById('sumEmoji').textContent=t==='dry'?'👀':t==='scan'?'🔍':'🎉';
                document.getElementById('sumTitle').textContent=t==='dry'?'Dry Run Complete':t==='scan'?'Scan Complete':'All Done!';
                document.getElementById('sumDetail').textContent=s.done_msg;
            }
            if(!s.running){setRunning(false);clearInterval(polling);polling=null}
        }catch(e){}
    },300);
}

async function doScan(){
    if(!selectedPath){alert('Click Browse to select a folder first!');return}
    lastLogLen=0;document.getElementById('logBox').innerHTML='';document.getElementById('summary').className='summary';
    setRunning(true);await fetch('/api/scan?source='+encodeURIComponent(selectedPath));startPolling();
}
async function doCollect(){
    if(!selectedPath){alert('Click Browse to select a folder first!');return}
    const dry=document.getElementById('dryToggle').checked;
    if(!dry&&!confirm('This will copy samples into each project folder.\nOriginal .als files backed up as .als.bak\n\nContinue?'))return;
    lastLogLen=0;document.getElementById('logBox').innerHTML='';document.getElementById('summary').className='summary';
    setRunning(true);await fetch('/api/collect?source='+encodeURIComponent(selectedPath)+'&dry='+(dry?'1':'0'));startPolling();
}
async function doCancel(){await fetch('/api/cancel')}
</script>
</body>
</html>"""

# ─── HTTP SERVER ───

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def _ok(self, data, ct='application/json'):
        self.send_response(200)
        self.send_header('Content-Type', ct)
        self.end_headers()
        self.wfile.write(data.encode() if isinstance(data, str) else data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/':
            self._ok(HTML, 'text/html')
        elif url.path == '/api/pick-folder':
            path = pick_folder()
            self._ok(json.dumps({'path': path}))
        elif url.path == '/api/state':
            with state_lock: self._ok(json.dumps(state))
        elif url.path == '/api/scan':
            params = parse_qs(url.query)
            source = params.get('source', [''])[0]
            if source and not state['running']:
                threading.Thread(target=run_scan, args=(source,), daemon=True).start()
            self._ok('{"ok":true}')
        elif url.path == '/api/collect':
            params = parse_qs(url.query)
            source = params.get('source', [''])[0]
            dry = params.get('dry', ['1'])[0] == '1'
            if source and not state['running']:
                threading.Thread(target=run_collect, args=(source, dry), daemon=True).start()
            self._ok('{"ok":true}')
        elif url.path == '/api/cancel':
            with state_lock: state['cancel'] = True
            self._ok('{"ok":true}')
        else:
            self.send_response(404); self.end_headers()

def main():
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    url = f'http://127.0.0.1:{PORT}'
    print(f"""
    📦 Ableton Batch - Collect All and Save v{APP_VERSION}
    ─────────────────────────────────
    Running at: {url}

    Opening in your browser...
    Press Ctrl+C to quit.
    """)
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt:
        print("\n    Goodbye! 👋\n")
        server.shutdown()

if __name__ == '__main__':
    main()
