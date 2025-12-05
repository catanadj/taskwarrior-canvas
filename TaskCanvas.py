#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import json, os, re, subprocess, sys, shlex
from pathlib import Path

ENERGY_ARROW_CSS = r"""
<style id="__ENERGY_ARROW_CSS__">
  /* Flow animation down the staged edge */
  @keyframes energyFlow {
    from { stroke-dashoffset: 48; }
    to   { stroke-dashoffset: 0;  }
  }

  /* Generic staged edge look (we'll add this class via JS) */
  .staged-energy-edge {
    stroke: #60a5fa;
    stroke-width: 2.25px;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-dasharray: 6 6;
    animation: energyFlow 900ms linear infinite;
    filter: drop-shadow(0 0 3px rgba(96,165,250,.7));
  }

  /* Optional on-hover emphasis (if your app enables hover on paths) */
  .staged-energy-edge:hover {
    stroke-width: 2.75px;
    filter: drop-shadow(0 0 5px rgba(96,165,250,.9));
  }

  /* Hide old dots inside the staging layer */
  #builderStage circle, #builderStage .energy-dot, #builderStage .pulse-dot {
    display: none !important;
  }
</style>
"""

ENERGY_ARROW_JS = r"""
<script id="__ENERGY_ARROW_JS__">
(function(){
  if (window.__ENERGY_ARROWS__) return; window.__ENERGY_ARROWS__ = true;

  // Apply animation to staged edges and hide dots (no arrowheads)
  function restyleStaging(){
    var svg = document.querySelector('#builderStage svg, svg');
    if (!svg) return;

    // Hide any dots that might have been recreated
    document.querySelectorAll('#builderStage circle, #builderStage .energy-dot, #builderStage .pulse-dot')
      .forEach(function(dot){ dot.style.display = 'none'; });

    // Heuristics: most builds draw staged links as <path> or <line> within #builderStage
    var stagedLines = document.querySelectorAll('#builderStage path, #builderStage line');
    stagedLines.forEach(function(el){
      // Only touch geometric edges (skip hidden/zero-length)
      // Also avoid re-marking same element
      if (!el.__energyArrowsApplied){
        // No arrowhead marker applied
        el.classList.add('staged-energy-edge');
        el.__energyArrowsApplied = true;
      }
    });
  }

  // Run often enough to catch newly drawn staged edges
  var t = setInterval(restyleStaging, 250);

  // Also react to DOM changes inside the staging layer
  try{
    var root = document.getElementById('builderStage') || document.body;
    var mo = new MutationObserver(function(){ restyleStaging(); });
    mo.observe(root, {subtree:true, childList:true, attributes:true});
  }catch(_){}

  // First paints
  setTimeout(restyleStaging, 60);
  setTimeout(restyleStaging, 300);
  setTimeout(restyleStaging, 1200);
})();
</script>
"""

CSS_WIRE_DEPS_AS_MAIN = r"""
<!-- injected by generator: wire deps as main -->
<style id="__ONLY_DEPS_CONSOLE_CSS__">
  #consolePanel, .console-panel { display: none !important; visibility: hidden !important; pointer-events: none !important; }
  #depCmdOverlay {
    position: fixed !important;
    right: 80px !important;
    bottom: 20px !important;
    top: auto !important;
    max-width: 50vw; max-height: 44vh;
    z-index: 100000 !important;
  }
  #depCmdOverlay.hidden { display: none !important; }
  #depCmdOverlay .hdr{display:flex;align-items:center;gap:8px;padding:6px 8px;background:#0e1626;border-bottom:1px solid #243247}
  #depCmdOverlay pre{margin:0;padding:10px;white-space:pre;max-height:36vh;overflow:auto;font:12px ui-monospace,monospace}
</style>
"""

JS_WIRE_DEPS_AS_MAIN = r"""
<script id="__ONLY_DEPS_CONSOLE_JS__">
(function(){
  if (window.__ONLY_DEPS_CONSOLE__) return; window.__ONLY_DEPS_CONSOLE__ = true;

  function $(sel, root){ return (root||document).querySelector(sel); }
  function $all(sel, root){ return Array.prototype.slice.call((root||document).querySelectorAll(sel)); }

  // Guard: only allow programmatic console toggles right after pressing the Console button or 'D'
  var ALLOW_TOGGLE_UNTIL = 0;
  function allowToggleBriefly(){
    ALLOW_TOGGLE_UNTIL = Date.now() + 600; // 600ms window
  }
  function toggleAllowed(){
    return Date.now() <= ALLOW_TOGGLE_UNTIL;
  }

  function ensureOverlay(){
    var ol = document.getElementById('depCmdOverlay');
    if (!ol){
      var wrap = document.createElement('div');
      wrap.innerHTML =
        '<div id="depCmdOverlay" class="" style="position:fixed;right:18px;bottom:18px;z-index:100000;max-width:50vw;max-height:44vh;background:#0b1220;color:#e6eef9;border:1px solid #243247;border-radius:10px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.35)">' +
        '  <div class="hdr" style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:#0e1626;border-bottom:1px solid #243247">' +
        '    <b style="font:12px ui-monospace,monospace">Console</b><div style="flex:1"></div>' +
        '    <button id="depCmdHideBtn" style="all:unset;border:1px solid #2a3a54;padding:2px 6px;border-radius:6px;cursor:pointer;color:#9cc2ff">Hide</button>' +
        '  </div>' +
        '  <pre id="depCmdPre" style="margin:0;padding:10px;white-space:pre;max-height:36vh;overflow:auto;font:12px ui-monospace,monospace"></pre>' +
        '</div>';
      document.body.appendChild(wrap.firstChild);
      ol = document.getElementById('depCmdOverlay');
      var hideBtn = document.getElementById('depCmdHideBtn');
      if (hideBtn) hideBtn.addEventListener('click', function(e){ e.preventDefault(); e.stopPropagation(); hideOverlay(); }, true);
    }else{
      ol.classList.remove('hidden');
      ol.style.display = 'block';
    }
    return ol;
  }
  function overlayVisible(){
    var ol = $('#depCmdOverlay'); if (!ol) return false;
    return !(ol.classList.contains('hidden') || ol.style.display === 'none');
  }
  function showOverlay(){ var ol = ensureOverlay(); ol.classList.remove('hidden'); ol.style.display = 'block'; refreshOverlayText(); }
  function hideOverlay(){ var ol = ensureOverlay(); ol.classList.add('hidden'); ol.style.display = 'none'; }
  function toggleOverlay(){ if (overlayVisible()) hideOverlay(); else showOverlay(); }

  // Strict Console button matching: only specific selectors
  var CONSOLE_BTN_SELECTOR = '#consoleBtn, [data-action="toggle-console"], .toggle-console, .console-btn, button[aria-label="Console"]';

  // Intercept ONLY clicks on actual Console buttons (via closest on strict selector)
  document.addEventListener('click', function(e){
    var btn = (e.target && e.target.closest) ? e.target.closest(CONSOLE_BTN_SELECTOR) : null;
    if (!btn) return;
    try{ e.preventDefault(); e.stopImmediatePropagation(); e.stopPropagation(); }catch(_){}
    allowToggleBriefly();
    toggleOverlay();
  }, true); // capture

  // Redirect common global toggles, but obey the guard
  function overrideIfFunc(name){
    try{
      var f = window[name];
      if (typeof f === 'function'){
        window[name] = function(){
          if (!toggleAllowed()) return; // ignore stray programmatic toggles
          try{ return toggleOverlay(); }catch(_){}
        };
      }
    }catch(_){}
  }
  ['toggleConsole','toggleMainConsole','toggleCommands','showConsolePanel','hideConsolePanel'].forEach(overrideIfFunc);

  // 'D' key toggles deps overlay and opens guard window
  document.addEventListener('keydown', function(e){
    var k = (e.key||'').toLowerCase();
    if (k==='d' && !e.metaKey && !e.ctrlKey && !e.altKey){
      e.preventDefault(); e.stopPropagation();
      allowToggleBriefly();
      toggleOverlay();
    }
  }, true);

  // Keep overlay text in sync with buildCommands()
  function getAllCommands(){
    var txt = '';
    try{ if (typeof window.buildCommands==='function') txt = String(window.buildCommands()||''); }catch(_){}
    return shortenUUIDs(txt); // change this to return "txt" if you want the full UUID of the tasks in the commands.
  }
  function setText(el, text){
    if (!el) return;
    if ('value' in el) el.value = text;
    else if ('textContent' in el) el.textContent = text;
    else el.innerText = text;
  }
  function refreshOverlayText(){
    var pre = document.getElementById('depCmdPre');
    if (!pre) return;
    var txt = getAllCommands();
    if (txt!=null) setText(pre, txt);
  }
  (function hookUpdateConsole(){
    var _upd = window.updateConsole;
    window.updateConsole = function(){
      try{ if (typeof _upd==='function') _upd.apply(this, arguments); }catch(_){}
      try{ refreshOverlayText(); }catch(_){}
    };
  })();

  // Initial state
  ensureOverlay();
  showOverlay();
  setTimeout(refreshOverlayText, 60);
  setTimeout(refreshOverlayText, 300);
  setTimeout(refreshOverlayText, 1200);
})();
</script>
"""
REMOVE_MODE_JS = """(() => {
  const $  = (s,r=document)=>r.querySelector(s);
  const $$ = (s,r=document)=>Array.from(r.querySelectorAll(s));
  const getCB = ()=> $('#removeMode') || $('#remove-mode') || $('input[type="checkbox"][name="removeMode"]') || $('#depRemoveMode');
  const isOn  = ()=> !!(window.__forceRemoveMode || (getCB() && getCB().checked));

  // Clickable strokes only in Remove mode
  if (!document.getElementById('depRemovePE')){
    const s=document.createElement('style'); s.id='depRemovePE';
    s.textContent = `
      body.dep-remove-mode #builderLinks, body.dep-remove-mode #builderLinks * { pointer-events:auto !important; }
      body.dep-remove-mode #builderLinks path, body.dep-remove-mode #builderLinks line { pointer-events:stroke !important; }
      body.dep-remove-mode svg path:hover, body.dep-remove-mode svg line:hover { 
        filter: drop-shadow(0 0 6px rgba(181,58,58,.9)); 
        stroke-width: 3.8px; 
        cursor: pointer;
        stroke: #ff4444 !important;
        opacity: 0.9;
        transition: all 0.2s ease;
      }
      /* Also highlight removable lines even outside remove mode for better UX */
      svg path[data-from][data-to]:hover, svg line[data-from][data-to]:hover {
        stroke: #ff4444 !important;
        stroke-width: 2.5px;
        cursor: pointer;
        opacity: 0.8;
        filter: drop-shadow(0 0 4px rgba(255,68,68,0.6));
        transition: all 0.2s ease;
      }
    `;
    document.head.appendChild(s);
  }
  if (isOn()) document.body.classList.add('dep-remove-mode');

  // Command Console extender: append extra lines to buildCommands()
  if (!window.__depExtraCmds) window.__depExtraCmds = [];
  if (!window.__depWrapBuild && typeof window.buildCommands === 'function'){
    window.__depWrapBuild = true;
    const origBuild = window.buildCommands;
    window.buildCommands = function(){
      const base  = origBuild.call(this) || '';
      const extra = (window.__depExtraCmds||[]).join('\\n');
      return extra ? (base ? base+'\\n'+extra : extra) : base;
    };
  }

  // Keep removed SOLID edges hidden on redraw
  if (!window.__REMOVED_DEPS) window.__REMOVED_DEPS = Object.create(null);
  const markHidden = (f,t)=> (window.__REMOVED_DEPS[f+'>'+t]=true);
  ['gatherEdgesShort','gatherEdgesShorts'].forEach(name=>{
    const orig = window[name];
    if (typeof orig==='function' && !orig.__wrapped){
      const wrap=function(){
        const arr = orig.apply(this, arguments) || [];
        return arr.filter(e => !window.__REMOVED_DEPS[e.from+'>'+e.to]);
      };
      wrap.__wrapped=true; window[name]=wrap;
    }
  });

  // Helpers
  function uuidForShort(short){
    try{
      const el = window.nodeElByShort ? window.nodeElByShort(short) : null;
      const uuid = el && el.getAttribute && el.getAttribute('data-uuid');
      return uuid || short;
    }catch{ return short; }
  }

  // Core mutation for SOLID edges
  window.__removeEverywhere = function(from,to){
    let changed=false;
    try{
      const SA=window.stagedAdd||[];
      for (let i=SA.length-1;i>=0;i--){ const e=SA[i]; if(e&&String(e.from)===String(from)&&String(e.to)===String(to)){ SA.splice(i,1); changed=true; } }
    }catch{}
    try{
      const EX=window.EXIST_EDGES||[];
      for (let i=EX.length-1;i>=0;i--){ const e=EX[i]; if(e&&String(e.from)===String(from)&&String(e.to)===String(to)){ EX.splice(i,1); changed=true; } }
    }catch{}
    try{
      const T=window.TASK_BY_SHORT||{};
      const deps=T[from] && (T[from].depends||T[from].dependencies);
      if (Array.isArray(deps)){
        const idx=deps.findIndex(x=>String(x)===String(to)); if (idx>=0){ deps.splice(idx,1); changed=true; }
      } else if (typeof deps==='string'){
        const out = deps.split(/[\\s,]+/).filter(Boolean).filter(x=>String(x)!==String(to)).join(',');
        if (T[from]){ if (T[from].depends!=null) T[from].depends=out; if (T[from].dependencies!=null) T[from].dependencies=out; changed=true; }
      }
    }catch{}
    try{
      $$('#builderLinks path,#builderLinks line').forEach(n=>{
        if (n.getAttribute('data-from')===from && n.getAttribute('data-to')===to) n.remove();
      });
    }catch{}
    markHidden(from,to);
    try{ window.drawLinks && window.drawLinks(); }catch{}
    try{ window.refreshDepHandleLetters && window.refreshDepHandleLetters(); }catch{}
    return changed;
  };

  // Make previews deterministic: tag overlay paths with data-from/to + data-staged-index
  (function wrapRenderStagedOverlay(){
    const fn = window.renderStagedOverlay;
    if (typeof fn !== 'function' || fn.__wrappedV61) return;
    const wrap = function(){
      const out = fn.apply(this, arguments);
      try{
        const over = document.getElementById('depStagedOverlay');
        const SA = window.stagedAdd || [];
        if (over){
          const paths = Array.from(over.querySelectorAll('path.staged-energy-edge, line.staged-energy-edge'));
          for (let i=0; i<paths.length; i++){
            const p = paths[i], e = SA[i];
            if (!p) continue;
            if (e && e.from && e.to){
              p.setAttribute('data-from', e.from);
              p.setAttribute('data-to', e.to);
            }
            p.setAttribute('data-staged-index', i);
          }
        }
      }catch{}
      return out;
    };
    wrap.__wrappedV61 = true;
    window.renderStagedOverlay = wrap;
  })();

  // Click wiring (capture) with container-based detection
  const links = document.getElementById('builderLinks') || document.querySelector('svg');
  if (!links || links.__rmV61) { console.log('[FixPack V6.1] already bound'); return; }
  links.__rmV61 = true;

  function isPreviewNode(node){
    // A preview is anything inside #depStagedOverlay (group-based), regardless of classes
    try { return !!(node && node.closest && node.closest('#depStagedOverlay')); } catch { return false; }
  }

  function removePreviewNode(node){
    // Prefer data-from/to if present (after wrapper)
    const from = node.getAttribute && node.getAttribute('data-from');
    const to   = node.getAttribute && node.getAttribute('data-to');
    if (from && to){
      try{
        const SA = window.stagedAdd || [];
        for (let i=SA.length-1;i>=0;i--){
          const e = SA[i]; if (e && e.from===from && e.to===to){ SA.splice(i,1); break; }
        }
      }catch{}
    } else {
      // Fallback by index alignment
      try{
        const over = document.getElementById('depStagedOverlay');
        if (over){
          const paths = Array.from(over.querySelectorAll('path.staged-energy-edge, line.staged-energy-edge'));
          const idx = paths.indexOf(node);
          if (idx >= 0 && Array.isArray(window.stagedAdd) && idx < window.stagedAdd.length){
            window.stagedAdd.splice(idx,1);
          }
        }
      }catch{}
    }
    try{ node.remove(); }catch{}
    try{ window.renderStagedOverlay && window.renderStagedOverlay(); }catch{}
    try{ window.drawLinks && window.drawLinks(); }catch{}
    try{ window.updateConsole && window.updateConsole(); }catch{}
    console.log('[dep-preview-cancel] removed');
  }

  links.addEventListener('click', (e)=>{
    if (!(window.__forceRemoveMode || isOn())) return;
    const t = e.target;
    if (!(t && (t.tagName==='path' || t.tagName==='line'))) return;
    e.preventDefault(); e.stopPropagation();

    const fromShort = t.getAttribute('data-from');
    const toShort   = t.getAttribute('data-to');

    if (isPreviewNode(t)){
      // PREVIEW (staging) edge – always cancel it
      return removePreviewNode(t);
    }

    // SOLID (staged) edge – even if it has 'staged-energy-edge' class
    if (fromShort && toShort){
      window.__removeEverywhere(fromShort,toShort);

      const fromUUID = uuidForShort(fromShort);
      const toUUID   = uuidForShort(toShort);
      const cmd = "task "+fromUUID+" modify depends:-"+toUUID;

      window.__depExtraCmds.push(cmd);
      try{ window.updateConsole && window.updateConsole(); }catch{}
      console.log('[dep-remove]', cmd);
      if (typeof toastMsg==='function') toastMsg('Removed: '+fromShort+' !depends '+toShort);
      return;
    }
  }, true);

  // Re-tag previews when overlay mutates (safety net)
  try{
    const mo = new MutationObserver(() => {
      const over = document.getElementById('depStagedOverlay');
      const SA = window.stagedAdd || [];
      if (!over) return;
      const paths = Array.from(over.querySelectorAll('path.staged-energy-edge, line.staged-energy-edge'));
      for (let i=0; i<paths.length; i++){
        const p = paths[i], e = SA[i];
        if (!p) continue;
        if (e && e.from && e.to){
          p.setAttribute('data-from', e.from);
          p.setAttribute('data-to', e.to);
        }
        p.setAttribute('data-staged-index', i);
      }
    });
    mo.observe(document.body, {childList:true, subtree:true});
  }catch{}
})();
"""

def inject_hover_console_features(html: str, *, log=True) -> str:
    """
    Injects:
      - Modify injector (short IDs)
      - Toggle-aware Done/Delete observer
      - Shortify-at-render (textarea + deps overlay)
      - Merge wrapper (ensures STAGED_CMDS lines show in console & overlay)
    Prints generator-side logs.
    """
    def logp(*a):
        if log: print(*a, file=sys.stderr)

    # ============= OBSERVER (toggle-aware ✓/🗑) =============
    SNIP_OBS = r"""
<script id="FEATURE_HOVER_STAGE_OBSERVER_V1">(function(){
  if (window.__HOVER_STAGE_OBSERVER_V1__) return;
  window.__HOVER_STAGE_OBSERVER_V1__ = true;

  function resolveUUID(node){
    if (!node) return "";
    var uid = node.getAttribute && (node.getAttribute('data-uuid') || node.getAttribute('data-short')) || "";
    if (!uid){
      try{ var s = node.querySelector('.short'); if (s && s.textContent) uid = s.textContent.trim(); }catch(_){}
    }
    return uid || "";
  }
  function toShort(uid){
    if (!uid) return "";
    if (/^[0-9a-f]{6,8}$/i.test(uid)) return uid.slice(0,8);
    try{
      if (window.TASKS) for (var i=0;i<TASKS.length;i++) if (TASKS[i]?.uuid===uid) return TASKS[i].short || uid.slice(0,8);
      if (window.TASK_BY_SHORT){ for (var k in TASK_BY_SHORT) if (TASK_BY_SHORT[k]?.uuid===uid) return k; }
    }catch(_){}
    return uid.slice(0,8);
  }
  function ensureArray(){ return (window.STAGED_CMDS = Array.isArray(window.STAGED_CMDS) ? window.STAGED_CMDS : []); }
  function stage(kind, node){
    var uid = resolveUUID(node); if (!uid) return;
    var sid = toShort(uid);
    var cmd = 'task '+sid+' '+(kind==='modify'?'modify':kind);
    var A = ensureArray();
    var opp = cmd.replace(/\b(done|delete)\b/, kind==='done'?'delete':'done');
    for (var i=A.length-1;i>=0;i--){
      var s = String(A[i]||'');
      if (s === opp) A.splice(i,1);
      if (s === cmd) return;
    }
    A.push(cmd);
    try{ if (typeof updateConsole==='function') setTimeout(updateConsole,0); }catch(_){}
    try{ if (typeof __depsOverlayRender==='function') setTimeout(__depsOverlayRender,0); }catch(_){}
  }
  function unstage(kind, node){
    var uid = resolveUUID(node); if (!uid) return;
    var sid = toShort(uid);
    var cmd = 'task '+sid+' '+(kind==='modify'?'modify':kind);
    var A = ensureArray();
    for (var i=A.length-1;i>=0;i--){
      if (String(A[i]||'') === cmd) A.splice(i,1);
    }
    try{ if (typeof updateConsole==='function') setTimeout(updateConsole,0); }catch(_){}
    try{ if (typeof __depsOverlayRender==='function') setTimeout(__depsOverlayRender,0); }catch(_){}
  }
  function startObserver(){
    var root = document.getElementById('builderStage') || document.body;
    if (!root || root.__hoverObserver) return;
    var obs = new MutationObserver(function(records){
      for (var r of records){
        if (r.type === 'attributes' && r.attributeName === 'class'){
          var el = r.target; if (!el || !el.classList) continue;
          // additions
          if (el.classList.contains('stagedDone'))  stage('done',   el);
          if (el.classList.contains('stagedDel'))   stage('delete', el);
          // removals (using oldValue)
          var ov = r.oldValue || "";
          var hadDone = /\bstagedDone\b/.test(ov), hasDone = el.classList.contains('stagedDone');
          var hadDel  = /\bstagedDel\b/.test(ov),  hasDel  = el.classList.contains('stagedDel');
          if (hadDone && !hasDone) unstage('done', el);
          if (hadDel  && !hasDel ) unstage('delete', el);
        } else if (r.type === 'childList'){
          r.removedNodes && r.removedNodes.forEach(function(n){
            try{
              if (n.nodeType !== 1) return;
              if (n.classList && (n.classList.contains('stagedDone') || n.classList.contains('stagedDel'))){
                unstage(n.classList.contains('stagedDone') ? 'done' : 'delete', n);
              }
              var marked = n.querySelectorAll && n.querySelectorAll('.stagedDone, .stagedDel');
              if (marked && marked.length){ marked.forEach(function(m){
                unstage(m.classList.contains('stagedDone') ? 'done' : 'delete', m);
              });}
            }catch(_){}
          });
        }
      }
    });
    obs.observe(root, { subtree:true, attributes:true, attributeFilter:['class'], attributeOldValue:true, childList:true });
    root.__hoverObserver = obs;
  }
  startObserver();
  document.addEventListener('twdata', function(){ setTimeout(startObserver, 0); });
  window.addEventListener('load', function(){ setTimeout(startObserver, 60); });
  console.log('[observer] hover stage observer active (toggle-aware)');
})();</script>
""".strip("\n")

    # ============= SHORTIFY (render-time) =============
    SNIP_SHORTIFY = r"""
<script id="FEATURE_SHORTIFY_RENDER_V1">(function(){
  if (window.__SHORTIFY_RENDER__) return; window.__SHORTIFY_RENDER__=true;
  function uuidToShort(uuid){
    try{
      if (!uuid) return "";
      if (window.TASKS) for (var i=0;i<TASKS.length;i++) if (TASKS[i]?.uuid===uuid) return TASKS[i].short||uuid;
      if (window.TASK_BY_SHORT){ for (var k in TASK_BY_SHORT) if (TASK_BY_SHORT[k]?.uuid===uuid) return k; }
    }catch(_){}
    return uuid;
  }
  function shortifyText(txt){
    if (!txt) return txt;
    return String(txt).replace(/\b([0-9a-f]{8}-[0-9a-f-]{13,})\b/ig, function(m){ return uuidToShort(m) || m; });
  }
  if (typeof window.updateConsole === 'function' && !window.updateConsole.__shortifyWrap){
    var _u = window.updateConsole;
    window.updateConsole = function(){
      var rv = _u.apply(this, arguments);
      try{ var el = document.getElementById('consoleText'); if (el && typeof el.value === 'string') el.value = shortifyText(el.value); }catch(_){}
      return rv;
    };
    window.updateConsole.__shortifyWrap = true;
  }
  ['__depsOverlayRender','renderStagedOverlay'].forEach(function(fn){
    if (typeof window[fn] === 'function' && !window[fn].__shortifyWrap){
      var orig = window[fn];
      window[fn] = function(){
        var rv = orig.apply(this, arguments);
        try{ var pre = document.getElementById('depCmdPre'); if (pre && typeof pre.textContent === 'string') pre.textContent = shortifyText(pre.textContent); }catch(_){}
        return rv;
      };
      window[fn].__shortifyWrap = true;
    }
  });
  try{ if (typeof updateConsole==='function') updateConsole(); }catch(_){}
  try{ if (typeof __depsOverlayRender==='function') __depsOverlayRender(); }catch(_){}
})();</script>
""".strip("\n")

  # ============= MERGE (textarea + Deps overlay) — V3 silent/efficient =============
    SNIP_MERGE = r"""
  <script id="FEATURE_CONSOLE_MERGE_V3">(function(){
    if (window.__CONSOLE_MERGE_V3__) return; window.__CONSOLE_MERGE_V3__=true;

    // --- util ---
    function uuidToShort(uuid){
      try{
        if (!uuid) return "";
        if (window.TASKS) for (var i=0;i<TASKS.length;i++) if (TASKS[i] && TASKS[i].uuid===uuid) return TASKS[i].short||uuid;
        if (window.TASK_BY_SHORT) for (var k in TASK_BY_SHORT) if (TASK_BY_SHORT[k] && TASK_BY_SHORT[k].uuid===uuid) return k;
      }catch(_){}
      return uuid;
    }
    var UUID_RE = /\b([0-9a-f]{8}-[0-9a-f-]{13,})\b/ig;
    function shortifyText(txt){
      if (!txt || !UUID_RE.test(txt)) return txt||"";
      UUID_RE.lastIndex = 0;
      return String(txt).replace(UUID_RE, function(m){ return uuidToShort(m) || m; });
    }
    function lines(s){
      if (!s) return [];
      return String(s).replace(/\r\n/g,"\n").split("\n").map(function(x){return x.trim();}).filter(Boolean);
    }
    function uniqueMerge(baseText, stagedArr){
      var base = lines(baseText);
      var staged = Array.isArray(stagedArr) ? stagedArr : [];
      var out=[], seen=Object.create(null);
      for (var i=0;i<base.length;i++){ var s=base[i]; if (!s||seen[s]) continue; seen[s]=1; out.push(s); }
      for (var j=0;j<staged.length;j++){ var t=staged[j]; if (!t||seen[t]) continue; seen[t]=1; out.push(t); }
      return out.join("\n");
    }

    // --- writers with change detection ---
    var _lastTextarea = null, _lastPre = null;
    function mergeIntoTextarea(){
      var el = document.getElementById("consoleText");
      if (!el) return;
      var merged = shortifyText(uniqueMerge(el.value, window.STAGED_CMDS||[]));
      if (merged !== _lastTextarea){
        el.value = merged;
        _lastTextarea = merged;
      }
    }
    function mergeIntoDepsOverlay(){
      var pre = document.getElementById("depCmdPre");
      if (!pre) return;
      var merged = shortifyText(uniqueMerge(pre.textContent||"", window.STAGED_CMDS||[]));
      if (merged !== _lastPre){
        pre.textContent = merged;
        _lastPre = merged;
      }
    }

    // --- debounced runner ---
    var _t = null, _queued = false;
    function scheduleMerge(delay){
      if (_queued) return;
      _queued = true;
      if (_t) clearTimeout(_t);
      _t = setTimeout(function(){
        _queued = false;
        try{ mergeIntoTextarea(); mergeIntoDepsOverlay(); }catch(_){}
      }, Math.max(50, delay|0)); // ~20fps
    }

    // --- wrap updateConsole once (after any other wrappers) ---
    if (!window.updateConsole){
      window.updateConsole = function(){ scheduleMerge(50); };
    }else if (!window.updateConsole.__mergeV3){
      var orig = window.updateConsole;
      window.updateConsole = function(){ var rv = orig.apply(this, arguments); scheduleMerge(50); return rv; };
      window.updateConsole.__mergeV3 = true;
    }

    // initial paint
    scheduleMerge(0);
  })();</script>
  """.strip("\n")


    # ============= MODIFY injector (normalize + short IDs; robust anchor) =============
    MODIFY_MARK = "/* __PATCH_MODIFY_STAGE_TO_CONSOLE__ */"
    SNIP_MODIFY = r"""
          /* __PATCH_MODIFY_STAGE_TO_CONSOLE__ */
          try{
            (function(){
              console.log("[hover/console] modify injector active");
              function normalizeMods(arr){
                var out = [], lastIdx = Object.create(null);
                for (var i=0;i<arr.length;i++){
                  var tok = String(arr[i]||'').trim(); if (!tok) continue;
                  var m = tok.match(/^([^:\s]+):(.*)$/);
                  if (m){
                    var key = m[1].toLowerCase();
                    if (lastIdx[key] != null){ out[lastIdx[key]] = tok; }
                    else { lastIdx[key] = out.length; out.push(tok); }
                  }else{
                    out.push(tok);
                  }
                }
                return out;
              }
              function toShortId(x){
                try{
                  var n = document.querySelector('#builderStage [data-uuid="'+x+'"]');
                  if (n) return n.getAttribute('data-short') || String(x).slice(0,8);
                }catch(_){}
                var s = String(x||''); return s.length>8 ? s.slice(0,8) : s;
              }
              var sid = toShortId(id);
              var modsArr = (Array.isArray(merged) ? merged.slice() : []);
              if (!sid || !modsArr.length) return;
              modsArr = normalizeMods(modsArr);
              var line = 'task '+sid+' modify '+modsArr.join(' ');
              var A = (window.STAGED_CMDS = window.STAGED_CMDS || []);
              for (var i=A.length-1;i>=0;i--){
                var s = String(A[i]||'');
                if (s.indexOf('task '+sid+' modify ') === 0){ A.splice(i,1); }
              }
              A.push(line);
              try{ if (typeof window.updateConsole==='function') setTimeout(window.updateConsole, 0); }catch(_){}
              try{ if (typeof window.__depsOverlayRender==='function') setTimeout(window.__depsOverlayRender, 0); }catch(_){}
            })();
          }catch(_){}
""".strip("\n")

    # Robust anchor for: ops.mods = merged;  (allows dot or ["mods"])
    pattern = r"(ops\s*(?:\.\s*|\[\s*['\"]\s*)mods(?:\s*['\"]\s*\])?\s*=\s*merged\s*;\s*)"

    if MODIFY_MARK in html:
        logp("[gen] modify injector: already present (marker).")
    else:
        hit_count = [0]
        def _repl(m):
            hit_count[0] += 1
            return m.group(1) + "\n" + SNIP_MODIFY + "\n"
        new_html = re.sub(pattern, _repl, html)
        if hit_count[0] > 0:
            logp(f"[gen] modify injector: anchored ({hit_count[0]} site(s)).")
            html = new_html
        else:
            # Fallback: append at </body> so it still works if the anchor shifts/minifies away
            html = html.replace("</body>", "<script>"+SNIP_MODIFY+"</script>\n</body>")
            logp("[gen] modify injector: fallback appended at </body>.")

    # Ensure observer present
    if "FEATURE_HOVER_STAGE_OBSERVER_V1" not in html:
        html = html.replace("</body>", SNIP_OBS + "\n</body>")
        logp("[gen] observer: appended.")
    else:
        logp("[gen] observer: already present.")

    # Ensure shortify present
    if "FEATURE_SHORTIFY_RENDER_V1" not in html:
        html = html.replace("</body>", SNIP_SHORTIFY + "\n</body>")
        logp("[gen] shortify: appended.")
    else:
        logp("[gen] shortify: already present.")

    # Ensure merge wrapper present
    if "FEATURE_CONSOLE_MERGE_V2" not in html:
        html = html.replace("</body>", SNIP_MERGE + "\n</body>")
        logp("[gen] merge wrapper: appended.")
    else:
        logp("[gen] merge wrapper: already present.")

    return html



def inject_multiline_add(html: str) -> str:
    """
    Multiline task creation:
      - Intercepts per-tag '+' (.tagAddBtn) and FAB (#fabAddNew)
      - Shows textarea; each non-empty line -> one task
      - Generates UUID as 'new-<hex>' (so app emits 'task add …')
      - Generates independent 8-hex short for DnD acceptance
      - Uses app internals to render/place + refresh console
      - Rebinds interactions (twdata + per-node attachers)
    """
    JS_ID = "FEATURE_MULTILINE_ADD_V1"

    js = r"""
<script id="FEATURE_MULTILINE_ADD_V1">(function(){
  if (window.__ML_ADD_V1__) return; window.__ML_ADD_V1__ = true;

  // -------- UI: multiline textarea modal --------
  function multilineDialog(title, placeholder){
    return new Promise((resolve)=>{
      const wrap = document.createElement('div');
      wrap.style.cssText = 'position:fixed;inset:0;display:flex;align-items:center;justify-content:center;z-index:999999;';
      wrap.innerHTML = `
        <div style="position:absolute;inset:0;background:rgba(0,0,0,.36)"></div>
        <div style="position:relative;max-width:720px;width:92%;background:#111;color:#eee;border-radius:12px;padding:16px;box-shadow:0 10px 30px rgba(0,0,0,.4)">
          <div style="font-weight:700;margin-bottom:8px">${title||'Add tasks (one per line)'}</div>
          <textarea id="mlAddTa" rows="8" autofocus
            style="width:100%;background:#0c0f16;color:#e7e7ee;border:1px solid #2a3344;border-radius:10px;padding:10px;resize:vertical;line-height:1.3;"
            placeholder="${placeholder||'One task per line…'}"></textarea>
          <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px">
            <button id="mlAddCancel" style="padding:6px 12px;border:1px solid #333;background:#1a1f2b;color:#bbb;border-radius:8px;cursor:pointer">Cancel</button>
            <button id="mlAddOk" style="padding:6px 12px;border:1px solid #3b82f6;background:#2563eb;color:#fff;border-radius:8px;cursor:pointer">Add</button>
          </div>
          <div style="font-size:12px;opacity:.7;margin-top:6px">Tip: Ctrl/⌘+Enter to submit</div>
        </div>`;
      document.body.appendChild(wrap);
      const ta = wrap.querySelector('#mlAddTa');
      const done = (ok)=>{ const v = ta.value; wrap.remove(); resolve(ok ? v : null); };
      wrap.querySelector('#mlAddOk').onclick = ()=>done(true);
      wrap.querySelector('#mlAddCancel').onclick = ()=>done(false);
      wrap.addEventListener('keydown', (ev)=>{
        if (ev.key==='Escape') { ev.preventDefault(); done(false); }
        if ((ev.ctrlKey||ev.metaKey) && ev.key==='Enter') { ev.preventDefault(); done(true); }
      });
      setTimeout(()=>ta.focus(),0);
    });
  }

  // -------- IDs: 'new-' UUID + independent 8-hex short --------
  function randHex(n){
    if (window.crypto && crypto.getRandomValues){
      const arr = new Uint8Array(n/2); crypto.getRandomValues(arr);
      return Array.from(arr, b=>b.toString(16).padStart(2,'0')).join('');
    }
    return Array.from({length:n},()=>Math.floor(Math.random()*16).toString(16)).join('');
  }
  function genNewIds(){
    // uuid prefix signals "new task" to your app's staging; short remains classic 8-hex for DnD
    const uuid = 'new-' + randHex(16);      // e.g., new-a1b2c3d4e5f67890
    const short = 'n-' + randHex(6);               // e.g., 7f9e02
    return { uuid, short };
  }
  function makeNewTask(desc, project, tagsArr){
    const ids = genNewIds();
    return { uuid: ids.uuid, short: ids.short, desc, project, tags: tagsArr, has_depends:false };
  }
  function firstTag(t){ return (t.tags && t.tags.length) ? t.tags[0] : "(no tag)"; }

  // -------- Rebinding: per-node + global --------
  function rebindForNode(nodeEl){
    try{
      if (typeof attachDepHandleToNode === 'function') attachDepHandleToNode(nodeEl);
      if (typeof __depHandleAuthorV6 === 'function') __depHandleAuthorV6(nodeEl);
      if (typeof __depHandleAuthorDedupV6b === 'function') __depHandleAuthorDedupV6b(nodeEl);
      nodeEl.setAttribute('draggable', 'true');    // harmless hint
      nodeEl.classList.add('draggable-node');      // benign class for delegated DnD
    }catch(_){}
  }
  function fireGlobalRebind(){
    try{ document.dispatchEvent(new Event('twdata')); }catch(_){}
  }

  // -------- Place one task using app internals --------
  function pushAndPlaceTask(t){
    // model
    window.TASKS.push(t);
    try{ window.TASK_BY_SHORT[t.short] = t; }catch(_){}
    // list
    try{ renderList(); }catch(_){}
    // builder + node enforcement
    try{
      const proj = t.project || "(no project)";
      const tag  = firstTag(t);
      if (typeof ensureTagArea==='function') ensureTagArea(proj, tag);
      let el = null;
      if (typeof addToBuilder==='function'){
        el = addToBuilder(t, null, null);
      }
      // ensure DOM carries correct identifiers (some paths may skip data-short)
      try{
        if (!el || el.nodeType !== 1){
          el = document.querySelector(`[data-uuid="${t.uuid}"]`) ||
               document.querySelector(`#builderStage .node[data-short="${t.short}"]`);
        }
        if (el && el.nodeType === 1){
          el.setAttribute('data-uuid', t.uuid);
          el.setAttribute('data-short', t.short);  // keep 8-hex for DnD logic
          rebindForNode(el);
        }
      }catch(_){}
    }catch(_){}
    try{ if (typeof updateConsole==='function') updateConsole(); }catch(_){}
  }

  // -------- 1) Intercept per-tag ＋ (.tagAddBtn) --------
  document.addEventListener('click', async function(ev){
    const btn = ev.target && ev.target.closest && ev.target.closest('.tagAddBtn');
    if (!btn) return;

    ev.preventDefault(); ev.stopImmediatePropagation();

    const area  = btn.closest('.tagArea');
    const project = area?.getAttribute('data-proj') || "(no project)";
    const tag     = area?.getAttribute('data-tag')  || "(no tag)";

    const val = await multilineDialog(`Add tasks to “${tag}” in ${project}`, 'One task per line…');
    if (val==null) return;
    const lines = String(val).split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    if (!lines.length) return;

    const tagsArr = (tag && tag !== "(no tag)") ? [tag] : [];
    for (let i=0;i<lines.length;i++){
      pushAndPlaceTask(makeNewTask(lines[i], project, tagsArr));
      if (i && i%25===0) await new Promise(r=>setTimeout(r,0)); // yield on large batches
    }
    fireGlobalRebind(); // ensure DnD/hover binders include new nodes
    console.log('[ml-add] added', lines.length, 'tasks to', project, '/', tag);
  }, true);

  // -------- 2) Intercept FAB (#fabAddNew) --------
  (function(){
    const fabBtn = document.getElementById('fabAddNew');
    if (!fabBtn) return;
    fabBtn.addEventListener('click', async function(ev){
      ev.preventDefault(); ev.stopImmediatePropagation();

      const descs = await multilineDialog('Add new tasks (one per line)', 'One task per line…');
      if (descs==null) return;
      const lines = String(descs).split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
      if (!lines.length) return;

      // Ask once for project/tags (mirrors original flow)
      const projs = (function(){
        const set={}, arr=[];
        try{
          for (let i=0;i<(window.TASKS||[]).length;i++){
            const p=(window.TASKS[i].project||"(no project)");
            if(!set[p]){ set[p]=1; arr.push(p); }
          }
        }catch(_){}
        arr.sort(); return arr;
      })();

      const defProj = projs[0] || "(no project)";
      const project = prompt("Project (existing or new):", defProj) || "(no project)";
      const tagsIn  = prompt("Tags (comma-separated):", "") || "";
      const tagsArr = tagsIn.split(",").map(s=>s.trim()).filter(Boolean);

      const onCanvas = (function(){
        try{ return (window.projectAreas && typeof projectAreas.has==='function') ? projectAreas.has(project) : false; }catch(_){ return false; }
      })();

      for (let i=0;i<lines.length;i++){
        const t = makeNewTask(lines[i], project, tagsArr);
        window.TASKS.push(t);
        try{ window.TASK_BY_SHORT[t.short] = t; }catch(_){}
        try{ renderList(); }catch(_){}
        if (onCanvas){
          try{
            if (typeof ensureTagArea==='function') ensureTagArea(project, firstTag(t));
            if (typeof addToBuilder==='function'){
              let el = addToBuilder(t, null, null) || null;
              if (!el || el.nodeType !== 1){
                el = document.querySelector(`[data-uuid="${t.uuid}"]`) ||
                     document.querySelector(`#builderStage .node[data-short="${t.short}"]`);
              }
              if (el && el.nodeType === 1){
                el.setAttribute('data-uuid', t.uuid);
                el.setAttribute('data-short', t.short);
                rebindForNode(el);
              }
            }
          }catch(_){}
        }
        if (i && i%25===0) await new Promise(r=>setTimeout(r,0));
      }

      if (!onCanvas){
        try{ alert(`Created ${lines.length} task(s). Add the project (“${project}”) to the canvas to place them.`); }catch(_){}
      }
      try{ if (typeof updateConsole==='function') updateConsole(); }catch(_){}
      fireGlobalRebind();

      console.log('[ml-add] added', lines.length, 'new task(s) to project', project);
    }, true);
  })();

  console.log('[ml-add] multiline add enabled (new-uuid + 8hex short + rebind)');
})();</script>
""".strip("\n")

    if JS_ID not in html:
        html = html.replace("</body>", js + "\n</body>")
    return html


def inject_newtask_console_sync(html: str) -> str:
    """
    Ensures new tasks (uuid 'new-*' or short 'n-<6hex>') render as:
      - 'task add …' normally
      - 'task log …' when hover-done
      - removed when hover-delete
    Also merges +tag / project:/ due: changes into that one line.
    Idempotent via <script id="FEATURE_NEW_TASK_CONSOLE_SYNC_V2">.
    """
    JS_ID = "FEATURE_NEW_TASK_CONSOLE_SYNC_V2"
    js = r"""
<script id="FEATURE_NEW_TASK_CONSOLE_SYNC_V2">(function(){
  if (window.__NEW_TASK_SYNC_V2__) return; window.__NEW_TASK_SYNC_V2__ = true;

  // --- 1) New-ID detection: uuid 'new-*' or short 'n-<6hex>'
  window.isNewId = window.isNewId || function(x){
    if (!x) return false;
    var s = String(x);
    return /^new-/.test(s) || /^n-[0-9a-f]{6}$/i.test(s);
  };

  // --- 2) Fold holder for per-new-task state (mods, tags, done/deleted)
  function ensureFOLD(){ if (!window.FOLD) window.FOLD = Object.create(null); return window.FOLD; }
  function ensureFold(id){
    var F = ensureFOLD();
    var f = F[id] || (F[id]={});
    if (!f.tags) f.tags = Object.create(null);
    if (!Array.isArray(f.extra)) f.extra = [];
    return f;
  }
  function parseModsToFold(f, modsTokens){
    if (!Array.isArray(modsTokens)) return;
    var seenIdx = Object.create(null), extra = [];
    for (var i=0;i<modsTokens.length;i++){
      var tok = String(modsTokens[i]||'').trim(); if (!tok) continue;
      if (tok[0]==='+' && tok.length>1){ f.tags[tok.slice(1)] = true; continue; }
      if (tok[0]==='-' && tok.length>1){ delete f.tags[tok.slice(1)]; continue; }
      var m = tok.match(/^([^:\s]+):(.*)$/);
      if (m){
        var k = m[1].toLowerCase(), v = m[2];
        if (k==='project'){ f.project = v || "(no project)"; continue; }
        if (k==='due'){ f.due = v; continue; }
        if (seenIdx[k]!=null){ extra[seenIdx[k]] = tok; } else { seenIdx[k]=extra.length; extra.push(tok); }
      } else {
        extra.push(tok);
      }
    }
    f.extra = extra;
  }

  // --- 3) Pull staged lines that (accidentally) target new IDs into FOLD and remove them
  function reconcileNewStaged(){
    var A = Array.isArray(window.STAGED_CMDS) ? window.STAGED_CMDS : (window.STAGED_CMDS = []);
    for (var i=A.length-1;i>=0;i--){
      var s = String(A[i]||'').trim();
      var m = s.match(/^task\s+(\S+)\s+(done|delete|modify)\b(?:\s+(.*))?$/i);
      if (!m) continue;
      var id = m[1], verb = (m[2]||'').toLowerCase(), rest = (m[3]||'').trim();
      if (!window.isNewId(id)) continue;
      var f = ensureFold(id);
      if (verb==='done'){ f.done = true; }
      else if (verb==='delete'){ f.deleted = true; }
      else if (verb==='modify'){ parseModsToFold(f, rest ? rest.split(/\s+/) : []); }
      A.splice(i,1);
    }
  }

  // --- 4) Build canonical lines for all NEW tasks (one line each; add OR log)
  function newTaskConsoleLines(){
    var out = [];
    var T = Array.isArray(window.TASKS) ? window.TASKS : [];
    for (var i=0;i<T.length;i++){
      var t = T[i]; if (!t) continue;
      var id = t.uuid || t.short; if (!window.isNewId(id)) continue;

      // read current hover state from DOM
      var nd = document.querySelector('.node[data-uuid="'+id+'"], .node[data-short="'+id+'"]');
      var done = false, deleted = false;
      if (nd){
        done    = nd.classList.contains('stagedDone') || nd.classList.contains('completed') || nd.getAttribute('data-done')==='1';
        deleted = nd.classList.contains('stagedDel')  || nd.getAttribute('data-deleted')==='1';
      }

      // merge with FOLD (which also tracks staged ops we absorbed)
      var f = (ensureFOLD()[t.uuid] || ensureFOLD()[t.short] || {});
      if (f.done) done = true;
      if (f.deleted) deleted = true;
      if (deleted) continue; // delete removes any new-task line

      var parts = [ done ? "task log" : "task add", (t.desc||"(no description)") ];

      var proj = (typeof f.project!=='undefined') ? f.project : (t.project || "(no project)");
      if (proj && proj!=="(no project)") parts.push("project:"+proj);

      var tagset = Object.create(null);
      if (Array.isArray(t.tags)) for (var k=0;k<t.tags.length;k++){ var tg=t.tags[k]; if (tg && tg!=="(no tag)") tagset[tg]=true; }
      if (f.tags) for (var tg in f.tags){ if (f.tags[tg]) tagset[tg]=true; else delete tagset[tg]; }
      Object.keys(tagset).forEach(function(tg){ parts.push("+"+tg); });

      var due = (typeof f.due!=='undefined') ? f.due : t.due;
      if (due) parts.push("due:"+due);

      if (Array.isArray(f.extra)) for (var q=0;q<f.extra.length;q++){ parts.push(f.extra[q]); }

      out.push(parts.join(" "));
    }
    return out;
  }

  // --- 5) Helpers for merging & filtering
  function splitLines(s){
    if (!s) return [];
    return String(s).replace(/\r\n/g,"\n").split("\n").map(function(x){return x.trim();}).filter(Boolean);
  }
  function writeConsole(lines){
    try{
      var txt = (lines||[]).join("\n");
      var ta = document.getElementById('consoleText');
      if (ta && typeof ta.value==='string') ta.value = txt;
      var pre = document.getElementById('depCmdPre');
      if (pre) pre.textContent = txt;
    }catch(_){}
  }
  function newTaskDescriptors(){
    var set = Object.create(null);
    var T = Array.isArray(window.TASKS) ? window.TASKS : [];
    for (var i=0;i<T.length;i++){
      var t=T[i]; if (!t) continue;
      var id = t.uuid || t.short; if (!window.isNewId(id)) continue;
      var d = (t.desc||"").trim();
      if (d) set[d]=1;
    }
    return set;
  }
  // Remove any “task add …” or “task log …” lines that appear to belong to NEW tasks (by description match)
  function stripCurrentNewTaskLines(currentLines){
    var descs = newTaskDescriptors();
    return currentLines.filter(function(line){
      var m = line.match(/^(task\s+(?:add|log)\s+)(.*)$/i);
      if (!m) return true;
      var rest = m[2]||"";
      // basic containment check on the description token
      for (var d in descs){ if (descs[d] && rest.indexOf(d) !== -1) return false; }
      return true;
    });
  }
  // If both "task add X" and "task log X" exist, keep only log
  function preferLogOverAdd(lines){
    var bestByRest = Object.create(null), order=[];
    for (var i=0;i<lines.length;i++){
      var s = lines[i], m = s.match(/^(task\s+(add|log)\s+)(.*)$/i);
      if (!m){ if (!bestByRest["__misc__"]) { bestByRest["__misc__"]=[]; order.push("__misc__"); } bestByRest["__misc__"].push(s); continue; }
      var verb = (m[2]||"").toLowerCase();
      var rest = m[3]||"";
      var key = "REST::"+rest;
      if (!(key in bestByRest)){ bestByRest[key] = s; order.push(key); }
      else {
        var prev = bestByRest[key];
        if (/^task\s+add\s+/i.test(prev) && verb === "log"){ bestByRest[key] = s; } // upgrade to log
      }
    }
    var out=[];
    for (var j=0;j<order.length;j++){
      var k = order[j], v = bestByRest[k];
      if (Array.isArray(v)) out = out.concat(v);
      else out.push(v);
    }
    return out;
  }

  // --- 6) Wrap updateConsole: rebuild with strict new-task policy + dedupe
  (function(){
    var _u = window.updateConsole;
    window.updateConsole = function(){
      try{ reconcileNewStaged(); }catch(_){}
      var rv = (typeof _u==='function') ? _u.apply(this, arguments) : undefined;

      try{
        var ta = document.getElementById('consoleText');
        var currentText = (ta && typeof ta.value==='string') ? ta.value : '';
        var current = splitLines(currentText);

        // Strip any old add/log lines for NEW tasks first
        var currentSansNew = stripCurrentNewTaskLines(current);

        // Recompute canonical NEW lines + add any non-new staged lines (if any)
        var newLines = newTaskConsoleLines();
        var staged  = Array.isArray(window.STAGED_CMDS) ? window.STAGED_CMDS.slice() : [];

        // Merge: (current minus old new-lines) + new-lines + staged; then prefer log over add
        var merged = currentSansNew.concat(newLines).concat(staged);

        var finalLines = preferLogOverAdd(merged);
        var finalText  = finalLines.join("\n");
        if (finalText !== currentText){
          writeConsole(finalLines);
        }
      }catch(_){}

      return rv;
    };
    window.updateConsole.__newTaskSyncWrap = true;
  })();

  // --- 7) Track hover class flips to keep FOLD up to date → refresh console
  (function(){
    var root = document.getElementById('builderStage') || document.body;
    if (!root) return;
    var obs = new MutationObserver(function(recs){
      var touch = false;
      for (var r of recs){
        if (r.type!=='attributes' || r.attributeName!=='class') continue;
        var el = r.target; if (!el || !el.classList) continue;
        var id = el.getAttribute('data-uuid') || el.getAttribute('data-short'); if (!window.isNewId(id)) continue;
        var f = ensureFold(id);
        var hadDone = /\bstagedDone\b/.test(r.oldValue||''), hasDone = el.classList.contains('stagedDone');
        var hadDel  = /\bstagedDel\b/.test(r.oldValue||''),  hasDel  = el.classList.contains('stagedDel');
        if (hasDone) f.done = true;  if (hadDone && !hasDone) f.done = false;
        if (hasDel)  f.deleted = true; if (hadDel && !hasDel)  f.deleted = false;
        touch = true;
      }
      if (touch){ try{ setTimeout(updateConsole, 0); }catch(_){} }
    });
    obs.observe(root, {subtree:true, attributes:true, attributeFilter:['class'], attributeOldValue:true});
  })();

  // --- 8) First paint
  try{ reconcileNewStaged(); }catch(_){}
  try{ setTimeout(function(){ if (typeof updateConsole==='function') updateConsole(); }, 0); }catch(_){}
  console.log('[new-task-console-sync] v2.2 active');
})();</script>

""".strip("\n")

    if JS_ID not in html:
        html = html.replace("</body>", js + "\n</body>")
    return html


def inject_console_hotkey_patch(html: str) -> str:
    JS_ID = "FEATURE_CONSOLE_HOTKEY_PATCH_V4"
    js = r"""
<script id="FEATURE_CONSOLE_HOTKEY_PATCH_V4">(function(){
  if (window.__HOTKEY_PATCH_V4__) return; window.__HOTKEY_PATCH_V4__ = true;

  var BYPASS = false; // let our synthetic events through

  function isKeyD(ev){
    return (ev.key||'').toLowerCase() === 'd';
  }
  function isAllowedCombo(ev){
    // ONLY Ctrl+Shift+D (or Cmd+Shift+D); Alt must NOT be pressed
    return isKeyD(ev) && ev.shiftKey && (ev.ctrlKey || ev.metaKey) && !ev.altKey;
  }

  // Block any 'd' / 'D' that is NOT the allowed combo.
  function makeBlocker(){
    return function(ev){
      if (BYPASS) return;              // let our synthetic press pass
      if (!isKeyD(ev)) return;         // not D/d
      if (isAllowedCombo(ev)) return;  // allow the combo (we’ll remap below)
      // Stop reaching legacy handlers everywhere (capture), but don't preventDefault,
      // so typing still inserts the character in inputs/textareas.
      ev.stopImmediatePropagation();
    };
  }

  var blocker = makeBlocker();

  // Install capture blockers on all key roots and all phases
  var targets = [window, document];
  try { targets.push(document.documentElement); } catch(_) {}
  try { targets.push(document.body); } catch(_) {}
  ['keydown','keypress','keyup'].forEach(function(type){
    targets.forEach(function(t){
      try { t.addEventListener(type, blocker, true); } catch(_) {}
    });
  });

  // Remap Ctrl/Cmd+Shift+D → synthesize one 'd' sequence so the old toggle still works
  function onRemap(ev){
    if (!isAllowedCombo(ev)) return;
    ev.preventDefault();
    ev.stopImmediatePropagation();
    BYPASS = true;
    try{
      var opts = {bubbles:true};
      document.dispatchEvent(new KeyboardEvent('keydown',  Object.assign({key:'d', code:'KeyD'}, opts)));
      document.dispatchEvent(new KeyboardEvent('keypress', Object.assign({key:'d', code:'KeyD'}, opts)));
      document.dispatchEvent(new KeyboardEvent('keyup',    Object.assign({key:'d', code:'KeyD'}, opts)));
    } finally {
      setTimeout(function(){ BYPASS = false; }, 0);
    }
  }
  // Listen early so we own the combo
  window.addEventListener('keydown', onRemap, true);

  console.log('[hotkey] ONLY Ctrl+Shift+D toggles console; plain/Shift D suppressed');
})();</script>
""".strip("\n")

    if JS_ID not in html:
        html = html.replace("</body>", js + "\n</body>")
    return html

# --- Color-split preview vs staged (blue vs red) + animation, no arrows ---
def inject_staged_deps_color_split(html: str) -> str:
    CSS = r"""
<style id="PATCH_STAGED_LINE_ANIM_V1">
/* Animate staged dependency lines in red and remove arrows */
@keyframes energyFlow {
  from { stroke-dashoffset: 48; }
  to   { stroke-dashoffset: 0; }
}

/* EXISTING/STAGED edges (completed dependencies) - RED */
#builderLinks path.dep-edge.existing,
#builderLinks line.dep-edge.existing,
#builderLinks path.link-existing,
#builderLinks line.link-existing,
#depExistingEdges path,
#depExistingEdges line,
path.dep-edge.staged,
line.dep-edge.staged,
path.existing[class*="dep"],
line.existing[class*="dep"] {
  stroke: #ec4899 !important;  /* Pink */
  filter: drop-shadow(0 0 3px rgba(236,72,153,.70)) !important;
  stroke-width: 2.25px !important;
  fill: none !important;
  stroke-linecap: round !important;
  stroke-linejoin: round !important;
  stroke-dasharray: 6 6 !important;
  animation: energyFlow 900ms linear infinite !important;
  marker-end: none !important;
  filter: drop-shadow(0 0 3px rgba(239,68,68,.70)) !important;
}

/* STAGING edges (preview while dragging) - BLUE - keep existing system */
#builderStage path.staged-energy-edge,
#builderStage line.staged-energy-edge {
  stroke: #60a5fa !important;
  stroke-width: 2.25px !important;
  fill: none !important;
  stroke-linecap: round !important;
  stroke-linejoin: round !important;
  stroke-dasharray: 6 6 !important;
  animation: energyFlow 900ms linear infinite !important;
  marker-end: none !important;
  filter: drop-shadow(0 0 3px rgba(96,165,250,.70)) !important;
}

/* Hide dots in staging area */
#builderStage circle,
#builderStage .energy-dot,
#builderStage .pulse-dot {
  display: none !important;
}
</style>
""".strip()

    JS = r"""
<script id="PATCH_STAGED_LINE_ANIM_JS_V1">(function(){
  if (window.__PATCH_STAGED_LINE_ANIM__) return; window.__PATCH_STAGED_LINE_ANIM__ = true;

  // Process EXISTING/STAGED edges (RED) - completed dependencies
  function restyleExistingEdges(root){
    var r = root || document;
    var existingSelectors = [
      '#builderLinks path.dep-edge.existing',
      '#builderLinks line.dep-edge.existing',
      '#builderLinks path.link-existing',
      '#builderLinks line.link-existing',
      '#depExistingEdges path',
      '#depExistingEdges line',
      'path.dep-edge.staged',
      'line.dep-edge.staged',
      'path.existing[class*="dep"]',
      'line.existing[class*="dep"]'
    ];
    
    existingSelectors.forEach(function(sel){
      r.querySelectorAll(sel).forEach(function(el){
        // Skip if this is in the staging area (preview)
        if (el.closest('#builderStage')) return;
        
        // Remove arrow marker
        if (el.getAttribute('marker-end')) el.removeAttribute('marker-end');
        
        // Ensure fill is none for proper stroke rendering
        if (el.getAttribute('fill') !== 'none') el.setAttribute('fill','none');
        
        // Force RED stroke-dasharray
        el.style.strokeDasharray = '6 6';
        el.style.animation = 'energyFlow 900ms linear infinite';
        
        // Mark as processed
        el.setAttribute('data-existing-animated', 'true');
      });
    });
  }

  // DON'T touch staging edges - let the existing __ENERGY_ARROW_JS__ handle them
  // Just ensure their marker-end is removed if present
  function ensureStagingNoArrows(root){
    var r = root || document;
    r.querySelectorAll('#builderStage path, #builderStage line').forEach(function(el){
      if (el.getAttribute('marker-end')) el.removeAttribute('marker-end');
    });
  }

  function restyleAll(){
    try{ 
      restyleExistingEdges(document);
      ensureStagingNoArrows(document);
    }catch(_){}
  }

  // Hook common renderers
  ['drawLinks','renderStagedOverlay','renderDepsOverlay','__depsOverlayRender','updateLinks','redrawLinks'].forEach(function(name){
    var fn = window[name];
    if (typeof fn === 'function' && !fn.__stagedAnimWrap){
      var orig = fn;
      window[name] = function(){
        var rv = orig.apply(this, arguments);
        setTimeout(function(){ restyleAll(); }, 10);
        return rv;
      };
      window[name].__stagedAnimWrap = true;
    }
  });

  // Periodic sweep
  setInterval(function(){ restyleAll(); }, 300);

  // Watch for DOM changes
  try {
    var observer = new MutationObserver(function(mutations){
      var shouldRestyle = false;
      mutations.forEach(function(mut){
        if (mut.type === 'childList' && mut.addedNodes.length > 0) {
          shouldRestyle = true;
        }
      });
      if (shouldRestyle) {
        setTimeout(function(){ restyleAll(); }, 10);
      }
    });
    observer.observe(document.body, {childList: true, subtree: true});
  } catch(_){}

  // Initial passes
  setTimeout(function(){ restyleAll(); }, 10);
  setTimeout(function(){ restyleAll(); }, 100);
  setTimeout(function(){ restyleAll(); }, 500);
  setTimeout(function(){ restyleAll(); }, 1000);
})();</script>
""".strip()

    if 'id="STAGED_DEPS_COLOR_SPLIT"' not in html:
        html = re.sub(r'</head>', CSS + '\n</head>', html, count=1, flags=re.I)
    if 'id="STAGED_DEPS_COLOR_SPLIT_JS"' not in html:
        html = re.sub(r'</body>', JS + '\n</body>', html, count=1, flags=re.I)
    return html


# --- Make edges follow nodes on move / reflow ---
def inject_follow_edges_on_move(html: str) -> str:
    JS = r"""
<script id="PATCH_FOLLOW_EDGES_ON_MOVE_V1">(function(){
  if (window.__FOLLOW_EDGES_ON_MOVE_V1__) return; window.__FOLLOW_EDGES_ON_MOVE_V1__ = true;

  function stageRoot(){ return document.getElementById('builderStage') || document.body; }
  function linksRoot(){ return document.getElementById('builderLinks') || document; }
  function px(n){ return (typeof n==='number' && isFinite(n)) ? n : 0; }

  function nodeCenter(node){
    var st = stageRoot();
    var nb = node.getBoundingClientRect();
    var sb = st.getBoundingClientRect ? st.getBoundingClientRect() : {left:0,top:0};
    var x = nb.left - sb.left + nb.width/2;
    var y = nb.top  - sb.top  + nb.height/2;
    return {x: px(x), y: px(y)};
  }
  function findNodeById(id){
    if (!id) return null;
    var sel = `[data-short="${CSS.escape(id)}"], [data-uuid="${CSS.escape(id)}"]`;
    return stageRoot().querySelector(sel);
  }
  function cubicPath(p1, p2){
    var dx = Math.max(40, Math.abs(p2.x - p1.x) * 0.5);
    var c1 = {x: p1.x + dx, y: p1.y};
    var c2 = {x: p2.x - dx, y: p2.y};
    return `M ${p1.x} ${p1.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${p2.x} ${p2.y}`;
  }

  function recomputeEdge(el){
    try{
      var from = el.getAttribute('data-from');
      var to   = el.getAttribute('data-to');
      if (!from || !to) return;
      var n1 = findNodeById(from), n2 = findNodeById(to);
      if (!n1 || !n2) return;

      var p1 = nodeCenter(n1), p2 = nodeCenter(n2);

      if (el.tagName.toLowerCase() === 'line'){
        el.setAttribute('x1', p1.x); el.setAttribute('y1', p1.y);
        el.setAttribute('x2', p2.x); el.setAttribute('y2', p2.y);
      } else {
        el.setAttribute('d', cubicPath(p1,p2));
        el.setAttribute('fill','none');
      }
      // No arrows on staged/animated dashes
      el.removeAttribute('marker-end');
    }catch(_){}
  }

  function recomputeAll(){
    var root = linksRoot();
    var sel = [
      '#builderLinks path[data-from][data-to]',
      '#builderLinks line[data-from][data-to]',
      'svg path[data-from][data-to]',
      'svg line[data-from][data-to]'
    ].join(',');
    root.querySelectorAll(sel).forEach(recomputeEdge);
  }

  var raf = 0, queued = false;
  function scheduleRecompute(){
    if (queued) return;
    queued = true;
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function(){ queued = false; recomputeAll(); });
  }

  // Hook your common render/link functions
  ;['drawLinks','renderStagedOverlay','renderDepsOverlay','__depsOverlayRender',
    'updateLinks','redrawLinks'].forEach(function(name){
    var fn = window[name];
    if (typeof fn === 'function' && !fn.__followEdgesWrap){
      var orig = fn;
      window[name] = function(){ var rv = orig.apply(this, arguments); scheduleRecompute(); return rv; };
      window[name].__followEdgesWrap = true;
    }
  });

  // Observe node pos/cls changes
  try{
    var mo = new MutationObserver(function(list){
      for (var m of list){
        if (m.type === 'attributes' && m.target && m.target.classList && m.target.classList.contains('node')){
          scheduleRecompute(); break;
        }
      }
    });
    mo.observe(stageRoot(), {subtree:true, attributes:true, attributeFilter:['style','transform','class']});
  }catch(_){}

  // Drag feedback
  var dragging = false;
  document.addEventListener('mousedown', function(ev){
    if (ev.target && (ev.target.closest('.node') || ev.target.classList.contains('node'))){ dragging = true; }
  }, true);
  document.addEventListener('mouseup', function(){ dragging = false; scheduleRecompute(); }, true);
  document.addEventListener('mousemove', function(){ if (dragging) scheduleRecompute(); }, true);

  // App refresh signal
  document.addEventListener('twdata', function(){ scheduleRecompute(); });

  // Initial passes
  scheduleRecompute();
  setTimeout(scheduleRecompute, 80);
  setTimeout(scheduleRecompute, 300);
})();</script>
""".strip()

    if 'id="PATCH_FOLLOW_EDGES_ON_MOVE_V1"' not in html:
        html = re.sub(r'</body>', JS + '\n</body>', html, count=1, flags=re.I)
    return html



def inject_actionable_beacon(html: str) -> str:
    CSS = r"""
<style id="FEATURE_ACTIONABLE_BEACON_V7B_CSS">
@keyframes beaconPulseV7B {
  0%   { transform: scale(0.9);  opacity: .35; filter: drop-shadow(0 0 0px rgba(34,211,238,.00)); }
  45%  { transform: scale(1.05); opacity: .95; filter: drop-shadow(0 0 6px rgba(34,211,238,.50)); }
  100% { transform: scale(0.9);  opacity: .35; filter: drop-shadow(0 0 0px rgba(34,211,238,.00)); }
}
/* 6px beacon in top-right */
.node .act-beacon-wrap {
  position: absolute;
  top: 6px; right: 6px;
  width: 6px; height: 6px;
  pointer-events: none; z-index: 2;
}
.node .act-beacon {
  width: 100%; height: 100%;
  border-radius: 999px;
  /* lively cyan/teal core with soft falloff */
  background: radial-gradient(closest-side,
              rgba(224, 255, 255, .95),
              rgba(34, 211, 238, .70) 55%,
              rgba(34, 211, 238, 0) 100%);
  animation: beaconPulseV7B 2.2s ease-in-out infinite;
  will-change: transform, opacity, filter;
}
/* ambient halo (very soft) */
.node .act-beacon::after {
  content: "";
  position: absolute; inset: -3px;
  border-radius: 999px;
  background: radial-gradient(closest-side,
              rgba(34,211,238,.22),
              rgba(34,211,238,0) 70%);
}
@media (prefers-reduced-motion: reduce) {
  .node .act-beacon { animation: none; }
}
</style>
""".strip()

    JS = r"""
<script id="FEATURE_ACTIONABLE_BEACON_V7B_JS">
(function(){
  if (window.__ACT_BEACON_V7B__) return; window.__ACT_BEACON_V7B__ = true;

  function collectEdgeSets(){
    var havePrereq = Object.create(null), inChain = Object.create(null);
    function add(e){ if(!e) return; var f=e.from, t=e.to; if(f){havePrereq[f]=1; inChain[f]=1;} if(t){inChain[t]=1;} }
    try{ (window.EXIST_EDGES||[]).forEach(add); }catch(_){}
    try{ (window.stagedAdd  ||[]).forEach(add); }catch(_){}
    return {havePrereq,inChain};
  }
  function isCompletedOrDeleted(n){
    return !!(n && (n.classList.contains('completed') ||
                    n.classList.contains('stagedDel') ||
                    n.getAttribute('data-deleted')==='1'));
  }
  function ensureBeacon(node){
    var wrap = node.querySelector(':scope > .act-beacon-wrap');
    if (!wrap){
      wrap = document.createElement('div');
      wrap.className = 'act-beacon-wrap';
      var dot = document.createElement('div');
      dot.className = 'act-beacon';
      wrap.appendChild(dot);
      try{ var pos = getComputedStyle(node).position; if (pos==='static') node.style.position='relative'; }catch(_){}
      node.appendChild(wrap);
    }
  }
  function removeBeacon(node){
    var wrap = node.querySelector(':scope > .act-beacon-wrap');
    if (wrap) wrap.remove();
  }

  function recompute(){
    var {havePrereq,inChain} = collectEdgeSets();
    (document.querySelectorAll('#builderStage .node')||[]).forEach(function(nd){
      var short = nd.getAttribute('data-short')||'';
      var uuid  = nd.getAttribute('data-uuid') ||'';
      if (isCompletedOrDeleted(nd)){ removeBeacon(nd); return; }
      var hasReq   = !!(havePrereq[short] || havePrereq[uuid]);
      var involved = !!(inChain[short]    || inChain[uuid]);
      if (!hasReq && involved) ensureBeacon(nd); else removeBeacon(nd);
    });
  }
  function schedule(){ if (schedule._raf) cancelAnimationFrame(schedule._raf); schedule._raf = requestAnimationFrame(recompute); }

  ['drawLinks','renderStagedOverlay','renderDepsOverlay','__depsOverlayRender','renderList','updateConsole']
    .forEach(function(n){ var fn=window[n]; if(typeof fn==='function' && !fn.__actBeaconV7B){ var o=fn; window[n]=function(){var r=o.apply(this,arguments); schedule(); return r;}; window[n].__actBeaconV7B=true; }});

  try{ var root = document.getElementById('builderStage') || document.body;
       new MutationObserver(function(){ schedule(); })
       .observe(root, {subtree:true, childList:true, attributes:true, attributeFilter:['class','style']}); }catch(_){}
  document.addEventListener('twdata', schedule);

  schedule(); setTimeout(schedule,140); setTimeout(schedule,420);
})();
</script>
""".strip()

    if 'id="FEATURE_ACTIONABLE_BEACON_V7B_CSS"' not in html:
        html = re.sub(r'</head>', CSS + '\n</head>', html, count=1, flags=re.I)
    if 'id="FEATURE_ACTIONABLE_BEACON_V7B_JS"' not in html:
        html = re.sub(r'</body>', JS + '\n</body>', html, count=1, flags=re.I)
    return html




OUT_HTML = Path.cwd() / "TaskCanvas.html"

def eprint(*args):
    sys.stderr.write(" ".join(str(a) for a in args) + "\n"); sys.stderr.flush()

def run_quiet(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False, text=True)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 1, "", str(e)

def _parse_task_export(raw: str):
    if not raw: return []
    lines=[]
    for ln in raw.splitlines():
        s=ln.strip()
        if not s or s.startswith("Configuration override "): continue
        lines.append(ln)
    txt="\n".join(lines).strip()
    if not txt: return []
    try:
        obj=json.loads(txt)
        if isinstance(obj, list): return obj
        if isinstance(obj, dict):
            if isinstance(obj.get("data"), list): return obj["data"]
            if isinstance(obj.get("rows"), list): return obj["rows"]
    except Exception: pass
    rows=[]
    for ln in txt.splitlines():
        s=ln.strip()
        if not s or not (s.startswith("{") and s.endswith("}")): continue
        try: rows.append(json.loads(s))
        except Exception: pass
    return rows

def fetch_tasks(filter_str=None, timeout=30):
    """
    If filter_str is None → equivalent to 'task status:pending export'
    Else → runs 'task <filter_str> export'
    Returns list of dicts with fields: uuid, short, desc, project, tags, depends, due
    """
    base = ["task",
            "rc.confirmation=off",
            "rc.dependency.confirmation=off",
            "rc.verbose=nothing",
            "rc.json.array=on"]

    if filter_str:
        base += shlex.split(filter_str)
    else:
        base += ["status:pending"]

    base += ["export"]

    # Try with rc flags first; fall back to a plain export if needed
    try:
        rc, out, err = run_quiet(base, timeout)
    except NameError:
        # If run_quiet isn't available in this scope, fallback to subprocess
        import subprocess
        try:
            out = subprocess.check_output(base, stderr=subprocess.STDOUT, timeout=timeout).decode("utf-8", "replace")
        except Exception:
            out = ""
        rc = 0
        err = ""

    rows = _parse_task_export(out)
    if not rows:
        # fallback to default task export (older Taskwarrior / rc mismatch)
        try:
            rc2, out2, err2 = run_quiet(["task", "export"], timeout)
            rows = _parse_task_export(out2)
        except NameError:
            import subprocess
            try:
                out2 = subprocess.check_output(["task", "export"], stderr=subprocess.STDOUT, timeout=timeout).decode("utf-8","replace")
            except Exception:
                out2 = ""
            rows = _parse_task_export(out2)

    tasks = []
    for r in rows or []:
        uuid = r.get("uuid") or r.get("id") or ""
        if not uuid:
            continue
        desc = r.get("description") or r.get("desc") or "(no description)"
        project = r.get("project") or "(no project)"
        tags = r.get("tags") or []
        if isinstance(tags, str):
            tags = [t for t in re.split(r"[,\s]+", tags) if t]
        depends = r.get("depends") or r.get("dependencies") or []
        if isinstance(depends, str):
            depends = [d for d in re.split(r"[,\s]+", depends) if d]
        due = r.get("due")
        tasks.append({
            "uuid": uuid,
            "short": uuid.replace("-", "")[:8],
            "desc": desc,
            "project": project,
            "tags": tags,
            "depends": depends,
            "due": due,
        })

    tasks.sort(key=lambda t: (t["project"], t["desc"]))

    try:
        eprint(f"[TaskCanvas] Loaded tasks: {len(tasks)} (filter: {filter_str!r})")
    except NameError:
        print(f"[TaskCanvas] Loaded tasks: {len(tasks)} (filter: {filter_str!r})")

    return tasks


def build_payload(tasks):
    short_by_uuid={t["uuid"]:t["short"] for t in tasks}
    edges=[]; parent_current_deps={}; children_map={}
    for t in tasks:
        p=short_by_uuid[t["uuid"]]
        for d in (t.get("depends") or []):
            if d in short_by_uuid:
                c=short_by_uuid[d]; edges.append({"from":p,"to":c})
                parent_current_deps.setdefault(p,set()).add(c)
                children_map.setdefault(c,set()).add(p)
    return {
        "tasks":[{"uuid":t["uuid"],"short":t["short"],"desc":t["desc"],"project":t["project"],"tags":t["tags"],"has_depends":bool(t["depends"]),"due":t.get("due")} for t in tasks],
        "graph":{
            "edges":edges,
            "parent_current_deps":{k:sorted(v) for k,v in parent_current_deps.items()},
            "child_to_parents":{k:sorted(v) for k,v in children_map.items()},
        }
    }


# ======================= Better project selector (curses) =====================

def _unique_projects(tasks):
    """Return (projects_list, counts_dict). '(no project)' last."""
    counts = {}
    for t in tasks:
        p = t.get("project") or "(no project)"
        counts[p] = counts.get(p, 0) + 1
    names = sorted([p for p in counts if p != "(no project)"])
    if "(no project)" in counts:
        names.append("(no project)")
    return names, counts


def _run_selector_curses(projects, counts):
    """
    Curses TUI multi-select:
      ↑/↓ : move      PgUp/PgDn : page       Home/End : jump
      Space: toggle   a : select all (visible)    n : none (visible)
      / : filter      Esc : clear filter          q : cancel (return [])
      Enter: confirm
    """
    import curses
    sel = set()            # selected project names
    cursor = 0             # index in filtered list
    query = ""             # filter string (case-insensitive)
    show_counts = True

    def filtered():
        if not query:
            return projects
        q = query.lower()
        return [p for p in projects if q in p.lower()]

    def clamp(i, L):
        return max(0, min(i, max(0, L - 1)))

    def draw(stdscr):
        stdscr.erase()
        H, W = stdscr.getmaxyx()

        header = " Select projects (Enter=confirm, space=toggle, /=filter, a=all, n=none, q=cancel) "
        _safe_addnstr(stdscr, 0, 0, header.ljust(W), W, curses.A_REVERSE)

        # If we have at least 2 rows, show filter line
        if H >= 2:
            _safe_addnstr(stdscr, 1, 0, f"Filter: {query}", W)

        # Compute list window geometry
        # top row for list starts at 2 only if we have room for header+filter
        top = 2 if H >= 3 else (1 if H >= 2 else 0)
        # leave one footer row only if we have ≥3 rows total
        footer_reserved = 1 if H >= 3 else 0
        rows = max(0, H - top - footer_reserved)

        vis = filtered()

        # paginate: center cursor when possible; always keep visible
        start = 0
        if rows > 0 and len(vis) > rows:
            start = min(max(cursor - rows // 2, 0), len(vis) - rows)

        # Paint list
        for i in range(start, min(len(vis), start + rows)):
            p = vis[i]
            mark = "[x]" if p in sel else "[ ]"
            cnt = f"  ({counts.get(p, 0)})" if show_counts else ""
            line = f"{mark} {p}{cnt}"
            attr = curses.A_REVERSE if i == cursor else curses.A_NORMAL
            _safe_addnstr(stdscr, top + (i - start), 0, line.ljust(W), W, attr)

        # Footer (only if we have room)
        if H >= 3:
            foot = f"{len(sel)} selected · {len(vis)} shown / {len(projects)} total"
            _safe_addnstr(stdscr, H - 1, 0, foot.ljust(W), W, curses.A_DIM)

        stdscr.refresh()


    def loop(stdscr):
        nonlocal cursor, query, show_counts, sel
        curses.curs_set(0)
        stdscr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        while True:
            vis = filtered()
            cursor = clamp(cursor, len(vis))
            draw(stdscr)
            ch = stdscr.getch()

            if ch in (ord('q'), 27) and not query:       # q or Esc (when not editing filter)
                if ch == 27 and query:  # handled below if we ever allow inline edit w/ Esc
                    pass
                return []               # cancel = start empty

            if ch in (10, 13, curses.KEY_ENTER):         # Enter
                return [p for p in projects if p in sel] # preserve original order

            if ch == ord('/'):                           # start/continue filter
                # simple in-line editing: typing appends; Backspace removes; Enter commits
                while True:
                    draw(stdscr)
                    c = stdscr.getch()
                    if c in (10, 13, curses.KEY_ENTER):  # finish filter
                        break
                    if c in (27,):                       # Esc clears filter
                        query = ""
                        break
                    if c in (curses.KEY_BACKSPACE, 127, 8):
                        query = query[:-1]
                    elif c == curses.KEY_RESIZE:
                        pass
                    elif 32 <= c <= 126:  # printable ASCII
                        query += chr(c)

                # clamp cursor after filter change
                cursor = clamp(cursor, len(filtered()))
                continue

            if ch == ord('a'):                           # select all (visible)
                for p in filtered():
                    sel.add(p)
                continue

            if ch == ord('n'):                           # clear all (visible)
                for p in filtered():
                    if p in sel:
                        sel.remove(p)
                continue


            if ch == ord('c'):                           # toggle counts display (optional)
                show_counts = not show_counts
                continue

            if ch in (curses.KEY_UP, ord('k')):
                cursor = clamp(cursor - 1, len(filtered()))
            elif ch in (curses.KEY_DOWN, ord('j')):
                cursor = clamp(cursor + 1, len(filtered()))
            elif ch == curses.KEY_PPAGE:  # PageUp
                cursor = clamp(cursor - max(5, curses.LINES - 4), len(filtered()))
            elif ch == curses.KEY_NPAGE:  # PageDown
                cursor = clamp(cursor + max(5, curses.LINES - 4), len(filtered()))
            elif ch == curses.KEY_HOME:
                cursor = 0
            elif ch == curses.KEY_RESIZE:
              # Let draw() re-read H,W and recalc layout on next iteration
              continue
            elif ch == curses.KEY_END:
                cursor = max(0, len(filtered()) - 1)
            elif ch in (ord(' '),):  # toggle selection
                if filtered():
                    p = filtered()[cursor]
                    if p in sel:
                        sel.remove(p)
                    else:
                        sel.add(p)

    import curses
    return curses.wrapper(loop)

def _safe_addnstr(scr, y, x, s, max_cols, attr=0):
    """Write safely, avoiding curses ERR on small/resize terminals."""
    try:
        H, W = scr.getmaxyx()
        if y < 0 or y >= H or x < 0 or x >= W:
            return
        width = max(0, min(max_cols, W - x))
        if width <= 0:
            return
        scr.addnstr(y, x, s, width, attr)
    except Exception:
        pass

def run_project_selector(tasks):
    """High-level entry: build list, launch curses UI, return chosen names."""
    projects, counts = _unique_projects(tasks)
    if not projects:
        print("[selector] No projects found.")
        return []
    try:
        return _run_selector_curses(projects, counts)
    except Exception as e:
        # Graceful fallback to a minimal prompt if curses fails
        import traceback
        print("[selector] curses failed, falling back to simple prompt.")
        traceback.print_exc()
        # Minimal fallback: show numbered list and accept space-separated indices
        width = max(len(p) for p in projects)
        for i, p in enumerate(projects, 1):
            print(f"{i:>3}. {p:<{width}} ({counts.get(p,0)})")
        raw = input("Pick numbers (e.g. 1 2 5-7) or leave empty: ").strip()
        if not raw:
            return []
        picked = set()
        for chunk in raw.replace(",", " ").split():
            if "-" in chunk:
                a, b = chunk.split("-", 1)
                try: a = int(a); b = int(b)
                except: continue
                if a > b: a, b = b, a
                for k in range(a, b+1):
                    if 1 <= k <= len(projects): picked.add(k-1)
            else:
                try:
                    k = int(chunk)
                    if 1 <= k <= len(projects): picked.add(k-1)
                except: pass
        return [projects[i] for i in sorted(picked)]

def _append_remove_mode(html):
    """Inject the working JavaScript directly into the HTML"""
    try:
        if not isinstance(html, str):
            return html
            
        low = html.lower()
        
        # Check if already injected
        if '__FIXPACK_V61__' in html:
            return html
        
        # Inject before closing body tag if it exists
        if '</body>' in low:
            idx = low.rfind('</body>')
            return (html[:idx] + 
                   '\n<script id="__FIXPACK_V61__">\n' + 
                   REMOVE_MODE_JS + 
                   '\n</script>\n' + 
                   html[idx:])
        else:
            # If no body tag, append at the end
            return html + '\n<script id="__FIXPACK_V61__">\n' + REMOVE_MODE_JS + '\n</script>\n'
            
    except Exception as e:
        # Log error but don't break the build
        print(f"Warning: Failed to inject working JS for remove mode: {e}")
        return html




def _json_text(d:dict)->str: return json.dumps(d, ensure_ascii=False)

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Taskwarrior — Master Life... One Task At A Time</title>
<style>
  :root{
    --bg:#0f1116; --fg:#e6edf3; --muted:#9aa4b2; --card:#161b22; --paper-bg:#121722;
    --accent:#7aa2f7; --accent-2:#98c379; --warn:#f59e0b; --danger:#ef4444;
    --proj-border:#3b4660; --tag-border:#355062; --select:#2563eb88;
    --leftW:360px;

    /* label colors */
    --proj-label-bg:#0a2a52; --proj-label-fg:#e8f1ff;
    --tag-label-bg:#083a2b;  --tag-label-fg:#eafff5;
    --none-label-bg:#3b1a1a; --none-label-fg:#ffd1d1;
  }
  html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:14px/1.45 ui-sans-serif,system-ui,Segoe UI,Roboto,Ubuntu}
  *{box-sizing:border-box}
  .app{display:grid;grid-template-rows:auto 1fr auto;grid-template-columns:var(--leftW) 1fr;grid-template-areas:"header header" "left builder" "console console";height:100%;transition:grid-template-columns .2s ease}
  header{grid-area:header;display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:var(--paper-bg);border-bottom:1px solid #202736;position:sticky;top:0;z-index:100}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .tabbar .tab{appearance:none;border:none;background:#1b2230;color:var(--fg);padding:8px 10px;border-radius:8px;cursor:pointer}
  .pill{display:inline-block;padding:4px 10px;border:1px solid #2a3344;border-radius:999px;color:var(--fg);font-size:12px}
  .btn{appearance:none;border:none;background:#1b2230;color:var(--fg);padding:6px 10px;border-radius:8px;cursor:pointer}
  .left{grid-area:left;background:var(--card);border-right:1px solid #202736;padding:10px;display:flex;flex-direction:column;gap:10px;overflow:auto}
  .search{display:flex;gap:8px}
  #q{flex:1;padding:8px 10px;border-radius:8px;border:1px solid #2a3344;background:#0e1320;color:var(--fg)}
  .section{margin-top:8px;margin-bottom:4px;color:var(--muted);font-weight:800}
  .item{cursor:grab;padding:8px;border:1px solid #2a3344;border-radius:6px;margin-bottom:6px;background:#0f1525}
  .short{font-weight:800;color:var(--accent);display:flex;align-items:center;gap:8px}
  .desc{margin:6px 0}
  .meta{color:var(--muted);font-size:12px}
  .builder{grid-area:builder;position:relative;overflow:hidden}

  /* Zoom (header) */
  .zoomwrap{display:flex;gap:10px;align-items:center;background:#0e1320;border:1px solid #2a3344;border-radius:10px;padding:6px 10px}
  .zoomwrap input[type=range]{width:200px}

  /* Canvas & stage */
  .canvas{position:absolute;inset:0;overflow:auto}
  .stage{position:relative;width:5000px;height:4000px;transform-origin:0 0}
  .areas{position:absolute;left:0;top:0;right:0;bottom:0;pointer-events:none
  z-index: 5;
}
  .areas > div{pointer-events:auto}
  .links{position:absolute;left:0;top:0;width:5000px;height:4000px;pointer-events:none
  z-index: 1;
}

  /* Nodes */
  .node{position:absolute;width:280px;min-height:88px;background:#0f1525;border:1px solid #2a3344;border-radius:12px;padding:8px;cursor:move;box-shadow:0 4px 14px rgba(0,0,0,.25);word-wrap:break-word
  z-index: 20;
}
  .node .title{font-weight:800;color:var(--fg)}
  .node .caption{color:var(--muted);font-size:12px;margin-top:4px}
  .node.selected{outline:2px solid var(--accent);outline-offset:2px}

  /* Project & Tag bubbles */
  .projArea{background:transparent;border-radius:24px;position:absolute;border:2px solid var(--proj-border)}
  .projAreaLabel{
    position:absolute;left:10px;top:10px;padding:5px 14px;background:var(--proj-label-bg);
    border:1px solid var(--proj-border);border-radius:999px;font-size:17px;font-weight:900;color:var(--proj-label-fg);
    user-select:none;letter-spacing:.2px;box-shadow:0 1px 0 rgba(255,255,255,.05) inset
  
  z-index:50; pointer-events:auto; cursor:move;
}
  .projAreaLabel.none{ background:var(--none-label-bg); color:var(--none-label-fg); border-color:#5a2a2a }
  .tagArea{position:absolute;border:1px dashed var(--tag-border);border-radius:18px;background:transparent
  pointer-events:auto;}

  .tagAreaLabel{position:absolute;left:10px;top:10px;  top:10px;padding:4px 12px;background:var(--tag-label-bg);
    border:1px solid var(--tag-border);border-radius:999px;font-size:15px;font-weight:800;color:var(--tag-label-fg);
    user-select:none;letter-spacing:.2px;box-shadow:0 1px 0 rgba(255,255,255,.05) inset
  z-index:50; pointer-events:auto; cursor:move;

}
  .tagAreaLabel.none{ background:var(--none-label-bg); color:var(--none-label-fg); border-color:#5a2a2a }

  /* Selection rectangle */
  .marquee{position:absolute;border:1px dashed #2563eb;background:var(--select);pointer-events:none;z-index:11000}

  /* Drawer handle (visible when collapsed) */
  .drawerHandle{position:fixed;left:0;top:40%;transform:translateY(-50%);background:#1b2230;border:1px solid #2a3344;border-left:none;border-radius:0 8px 8px 0;color:var(--fg);padding:8px 10px;cursor:pointer;z-index:15000;display:none}
  body.drawer-collapsed .drawerHandle{display:block}

  /* Console panel */
  .console{grid-area:console;background:#0e1320;border-top:1px solid #202736;display:none}
  .console.open{display:block}
  .consoleHead{display:flex;align-items:center;justify-content:space-between;padding:6px 10px;color:var(--muted)}
  .consoleBody{padding:8px 10px}
  #consoleText{width:100%;height:160px;background:#0b1020;color:#a5b4fc;border:1px solid #2a3344;border-radius:8px;font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;font-size:12px;line-height:1.4;white-space:pre}


/* === Tw Patch: clearer areas, virtualization helpers, fit button === */
:root{ --proj-border:#7aa2f7; --tag-border:#98c379; --fg:#e5e7eb; --muted:#9aa5b1; }
.projArea{
  background:linear-gradient(180deg, rgba(122,162,247,.08), rgba(122,162,247,.03));
  border:2px solid var(--proj-border);
  border-radius:24px;
  box-shadow:inset 0 0 0 1px rgba(122,162,247,.12), 0 8px 24px rgba(0,0,0,.18);
}
.tagArea{
  background:linear-gradient(180deg, rgba(152,195,121,.08), rgba(152,195,121,.03));
  border:1px dashed var(--tag-border);
  border-radius:18px;
  box-shadow:inset 0 0 0 1px rgba(152,195,121,.12);
}
/* Make project label sit above tags, and push tag label lower */
.projAreaLabel{ z-index:12; }
.tagAreaLabel{ z-index:11; top:10px; }
/* Virtualization helper */
.virtHidden{ display:none !important; }
/* Fit button basic look */
#fitBtn{ margin-left:8px; padding:6px 10px; border-radius:8px; border:1px solid #2a3344; background:#0c1118; color:var(--fg); cursor:pointer; }
#fitBtn:hover{ filter:brightness(1.1); }



/* === Tw Patch: FAB styles (ensured) === */
.fab{
  position:fixed; right:20px; bottom:24px;
  width:56px; height:56px; border-radius:50%;
  background:#2563eb; color:#fff;
  display:flex; align-items:center; justify-content:center;
  font-size:28px; cursor:pointer; user-select:none;
  box-shadow:0 8px 24px rgba(0,0,0,.35); z-index:30000;
}
.fab:hover{ filter:brightness(1.1); }

.fabMenu{
  position:fixed; right:20px; bottom:88px;
  display:flex; flex-direction:column; gap:8px; z-index:30000;
}
.fabMenu.hidden{ display:none; }
.fabMenu button{
  background:#1b2230; color:var(--fg);
  border:1px solid #2a3344; border-radius:10px;
  padding:8px 12px; cursor:pointer; white-space:nowrap;
}
.fabMenu button::after{
  content: attr(data-kbd);
  margin-left:8px; color:var(--muted); font-size:12px;
}


/* Add button inside tag label */
.tagAddBtn{ font-size:12px; line-height:18px; }

  .due{color:#a5b4fc;font-size:12px;margin-top:6px;}

  .projAddBtn{position:absolute;right:6px;top:6px;width:20px;height:20px;border-radius:50%;border:1px solid #2a3344;background:#1b2230;color:var(--fg);cursor:pointer}

/* == dep handle (middle-right) ============================================= */
.depHandle{
  position:absolute; right:-10px; top:50%; transform:translateY(-50%);
  width:22px; height:22px; line-height:22px;
  text-align:center; font-weight:700; font-size:12px;
  color:#0b1220; background:#93c5fd; border:1px solid #60a5fa;
  border-radius:999px; cursor:grab; user-select:none; z-index:2000;
  box-shadow:0 1px 2px rgba(0,0,0,.30); pointer-events:auto;
}
.depHandle.dragging{ cursor:grabbing; }


/* == dep handle (middle-right) ============================================= */
.depHandle{
  position:absolute; right:-10px; top:50%; transform:translateY(-50%);
  width:22px; height:22px; line-height:22px;
  text-align:center; font-weight:700; font-size:12px;
  color:#0b1220; background:#93c5fd; border:1px solid #60a5fa;
  border-radius:999px; cursor:grab; user-select:none; z-index:2000;
  box-shadow:0 1px 2px rgba(0,0,0,.30); pointer-events:auto;
}
.depHandle.dragging{ cursor:grabbing; }

/* === dep-handle strict visibility (hover + edges keep visible) ============= */
/* Hidden by default (high specificity + !important beats earlier rules) */
#builderStage [data-short] > .depHandle{
  opacity:0 !important;
  transform:translateY(-50%) scale(0.86) !important;
  transition:opacity .15s ease, transform .15s ease !important;
}
/* Visible when: has deps, hovered, or dragging */
#builderStage [data-short] > .depHandle.dep-hasdeps,
#builderStage [data-short] > .depHandle:hover,
#builderStage [data-short] > .depHandle.dragging{
  opacity:1 !important;
  transform:translateY(-50%) scale(1) !important;
}

/* dep-handle counts (Chrome): flexible width so 'A12/7' fits */
#builderStage [data-short] > .depHandle{
  width:auto !important;
  min-width:24px;
  padding:0 6px;
  font-size:12px;
  letter-spacing:.2px;
  text-align:center;
  box-sizing:border-box;
}

/* == dep pulses ============================================================= */
#builderLinks #depPulseOverlay .pulse-dot{
  fill:#93c5fd;
  opacity:.95;
  filter: drop-shadow(0 0 3px rgba(147,197,253,.9));
}

/* __EXISTING_SOLID_V3A__ existing vs staged edges */
#builderLinks path.dep-edge{ stroke-linecap:round; }
#builderLinks path.dep-edge.existing{ stroke:#9ecbff; stroke-width:2; stroke-dasharray:none; }
#builderLinks path.dep-edge.staged  { stroke:#7aa2f7; stroke-width:2.5; stroke-dasharray:6 6; }
</style>
<style id="feature-toast-util-v1-css">
#devConsoleToast {
  position: fixed; right: 12px; bottom: 12px;
  background: #1b2230; color: #e6edf3;
  border: 1px solid #2a3344; border-radius: 8px;
  padding: 8px 12px; z-index: 99999;
  font: 13px/1.35 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
  box-shadow: 0 6px 20px rgba(0,0,0,.35);
  opacity: 0; pointer-events: none;
  transform: translateY(8px);
  transition: opacity .18s ease, transform .18s ease;
}
#devConsoleToast.show { opacity: 1; transform: translateY(0); }
</style>

<style id="feature-dedupe-focus-v1-css">
/* pulse highlight for focused/duplicate-found nodes */
@keyframes nodePulse {
  0%   { box-shadow: 0 0 0 0 rgba(122,162,247,.0), 0 0 0 0 rgba(122,162,247,.0); }
  20%  { box-shadow: 0 0 0 2px #7aa2f7, 0 0 0 8px rgba(122,162,247,.25); }
  100% { box-shadow: 0 0 0 0 rgba(122,162,247,.0), 0 0 0 0 rgba(122,162,247,.0); }
}
.node.pulse {
  animation: nodePulse .8s ease-out 1;
}
</style>


<style id="feature-project-addtag-v4-css">
  .projAddTagBtn {
    display:inline-flex; align-items:center; justify-content:center;
    width:18px; height:18px; line-height:16px;
    border:1px solid rgba(122,162,247,.6); border-radius:4px;
    margin-left:6px; font-size:12px; color:#7aa2f7; background:rgba(12,18,34,.6);
    cursor:pointer; user-select:none;
  }
  .projAddTagBtn:hover{ background:rgba(122,162,247,.15); }
</style>

</head>
<body><script>(function(){
  function safeInit(){
    try{ if(!window.__INIT_DONE__ && typeof initFromDATA==='function'){ window.__INIT_DONE__=true; initFromDATA(); }}
    catch(e){ console.log('[boot] init error', e); }
  }
  document.addEventListener('twdata', safeInit, {once:true});
  window.addEventListener('load', function(){ if(window.DATA_READY) safeInit(); }, {once:true});
})();</script>

<script>
/* __EXISTING_SOLID_V3A__ boot EXIST_EDGES from payload graph.edges */
(function(){
  try{
    var G = (window.DATA && window.DATA.graph) ? window.DATA.graph : (window.GRAPH || {});
    if (!('EXIST_EDGES' in window)){
      window.EXIST_EDGES = (G && Array.isArray(G.edges)) ? G.edges.slice() : [];
    }
  }catch(_){}
  setTimeout(function(){
    try{ if (typeof refreshDepHandleLetters === 'function') refreshDepHandleLetters(); }catch(_){}
  }, 0);
})();
</script>

<script>
(function(){
  function safeInit(){
    try {
      if (!window.__INIT_DONE__ && typeof initFromDATA === 'function') {
        window.__INIT_DONE__ = true;
        initFromDATA();
      }
    } catch(e){ console.log('[boot] init error', e); }
  }
  document.addEventListener('twdata', safeInit, { once:true });
  window.addEventListener('load', function(){ if (window.DATA_READY) safeInit(); }, { once:true });
})();
</script>
<!-- Inline payload -->
<!-- INLINE_PAYLOAD_HERE -->

<div class="app">
  <header>
    <div class="row">
      <div class="tabbar">
        <button id="tabBuilder" class="tab">Builder</button>
        <button id="tabViewer" class="tab">Viewer</button>
        <button id="toggleDrawer" class="btn" title="Show/Hide drawer">☰ Drawer</button>
      </div>
      <span id="count" class="pill">Loaded: 0</span>
      <span id="parsedBadge" class="pill" title="Parsed in browser">Parsed: 0</span>
    </div>
    <div class="row">
      <div class="zoomwrap">
        <span>Zoom</span>
        <input id="zoom" type="range" min="50" max="200" value="100" />
<button id="fitBtn" title="Fit to screen">Fit</button>

        <span id="zoomPct">100%</span>
      </div>
      <button id="toggleConsole" class="btn">Console</button>
      <button id="copyBtn" class="btn" title="Copy Taskwarrior commands">Copy commands</button>
      <label class="btn" style="background:#241a0a;color:#f5bf74"><input type="checkbox" id="removeMode"> Remove mode</label>
    </div>
  </header>

  <div id="left" class="left">
    <div class="search"><input id="q" placeholder="Search…  project:work  tag:home  text"/></div>
    <label><input type="checkbox" id="hideHasDeps"> Hide tasks that already have depends</label>
    <div id="list"></div>
  </div>

  <div id="builderWrap" class="builder">
    <div class="canvas">
      <div id="builderStage" class="stage">
        <div id="areasLayer" class="areas"></div>
        <div id="tagsLayer" class="areas"></div>
        <svg id="builderLinks" class="links" viewBox="0 0 5000 4000" preserveAspectRatio="none"></svg>
      </div>
    </div>
  </div>

  <div id="viewerWrap" class="builder" style="display:none">
    <div class="canvas">
      <div id="viewerStage" class="stage"></div>
    </div>
  </div>

  <div id="consolePanel" class="console">
    <div class="consoleHead">
      <div>Pending commands</div>
      <div class="row">
        <button id="copyBtn2" class="btn">Copy</button>
      </div>
    </div>
    <div class="consoleBody">
      <textarea id="consoleText" readonly></textarea>
    </div>
  </div>
</div>

<!-- Drawer hover handle -->
<div id="drawerHandle" class="drawerHandle">Tasks ▸</div>

<!-- Floating Add button and menu -->
<div id="fab" class="fab" title="Add…">＋</div>
<div id="fabMenu" class="fabMenu hidden">
  <button id="fabAddProject">Add project…</button>
  <button id="fabAddFiltered">Add filtered tasks</button>
  <button id="fabAddNew">Add new task…</button>
</div>

<script>
if (typeof projectPalette !== 'function'){
  function projectPalette(proj){
    try{
      var h = hash32(String(proj||"(no project)")) % 360;
      return {
        bg:  "linear-gradient(180deg, hsla("+h+",30%,18%,.20), hsla("+h+",30%,12%,.12))",
        border: "hsla("+h+",55%,46%,.85)",
        labelBg: "hsla("+h+",50%,20%,.85)"
      };
    }catch(_){
      return { bg:"linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,.01))",
               border:"#3f4757", labelBg:"#2a3344" };
    }
  }
}


/* ===== State / helpers ===== */
if (typeof window.escapeHtml !== 'function') {
  window.escapeHtml = function(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, function(c){
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
    });
  };
}

var TASKS = [];
var INIT_MAIN_TAG = {};     // short -> initial main tag
var INIT_PROJECT = {};      // short -> initial project
var TASK_BY_SHORT = {};     // short -> task object (live)
var PARENT_DEPS0 = {};
var CHILD_TO_PARENTS = {};

var ZSCALE = 1.0;
var DRAWER_PINNED = false; // start collapsed

var projectAreas = new Map(); // project -> {x,y,w,h,tagCols,tagW0,tagH0,nextTagIndex,el}
var tagAreas = new Map();     // key "p||t" -> {x,y,w,h,project,tag,el,_cols}
var LAYOUT = {
  CELL_W:280, COLS:2, COL_GAP:24, ROW_GAP:18,
  AREA_PAD:16, AREA_GAP:60, TAG_PAD:10, TAG_HEAD:40, PROJ_HEAD:56, TAG_COLS:3
};

// === Tag color helpers ===
function hash32(str){
  var h=2166136261>>>0;
  for (var i=0;i<str.length;i++){ h^=str.charCodeAt(i); h=(h>>>0)*16777619>>>0; }
  return h>>>0;
}
function tagPalette(tag){
  var h = hash32(tag||"none") % 360;
  return {
    bg:  "linear-gradient(180deg, hsla("+h+",40%,18%,.22), hsla("+h+",40%,12%,.14))",
    border: "hsla("+h+",55%,46%,.85)",
    labelBg: "hsla("+h+",50%,20%,.85)"
  };
}


var left        = document.getElementById('left');
var builderWrap = document.getElementById('builderWrap');
var viewerWrap  = document.getElementById('viewerWrap');
var tabBuilder  = document.getElementById('tabBuilder');
var tabViewer   = document.getElementById('tabViewer');
var toggleDrawer= document.getElementById('toggleDrawer');
var drawerHandle= document.getElementById('drawerHandle');

var list        = document.getElementById('list');
var q           = document.getElementById('q');
var hideHasDeps = document.getElementById('hideHasDeps');
var count       = document.getElementById('count');
var parsedBadge = document.getElementById('parsedBadge');
var removeMode  = document.getElementById('removeMode');

var builderStage = document.getElementById('builderStage');
var areasLayer   = document.getElementById('areasLayer');
var tagsLayer    = document.getElementById('tagsLayer');
var builderLinks = document.getElementById('builderLinks');
var viewerStage  = document.getElementById('viewerStage');

var zoom        = document.getElementById('zoom');
var zoomPct     = document.getElementById('zoomPct');
var copyBtn     = document.getElementById('copyBtn');
var copyBtn2    = document.getElementById('copyBtn2');
var consolePanel= document.getElementById('consolePanel');
var toggleConsole=document.getElementById('toggleConsole');
var consoleText = document.getElementById('consoleText');

var fab = document.getElementById('fab');
var fabMenu = document.getElementById('fabMenu');
var fabAddProject = document.getElementById('fabAddProject');
var fabAddFiltered = document.getElementById('fabAddFiltered');
var fabAddNew = document.getElementById('fabAddNew');

/* ===== Drawer collapse/expand ===== */
function setDrawerWidth(px){ document.documentElement.style.setProperty('--leftW', px + 'px'); }
function collapseDrawer(){ DRAWER_PINNED=false; setDrawerWidth(0); document.body.classList.add('drawer-collapsed'); }
function expandDrawer(pin){ if (pin===true) DRAWER_PINNED=true; setDrawerWidth(360); document.body.classList.remove('drawer-collapsed'); }
toggleDrawer.addEventListener('click', function(){ if (DRAWER_PINNED){ collapseDrawer(); } else { expandDrawer(true); } });
drawerHandle.addEventListener('mouseenter', function(){ if (!DRAWER_PINNED) expandDrawer(false); });
left.addEventListener('mouseleave', function(){ if (!DRAWER_PINNED) collapseDrawer(); });

/* ===== Tabs ===== */
function setMode(mode){
  if(mode==="viewer"){
    left.style.display='none';
    builderWrap.style.display='none';
    viewerWrap.style.display='block';
    tabViewer.classList.add('active'); tabBuilder.classList.remove('active');
    renderViewer();
  }else{
    left.style.display='block';
    builderWrap.style.display='block';
    viewerWrap.style.display='none';
    tabBuilder.classList.add('active'); tabViewer.classList.remove('active');
    recomputeAreasAndTags();
    drawLinks();
  }
}
tabBuilder.addEventListener('click', function(){ setMode('builder'); });
tabViewer.addEventListener('click', function(){ setMode('viewer'); });

/* ===== Filters ===== */
function parseQuery(txt){
  var t=(txt||"").trim().toLowerCase().split(/\s+/).filter(function(s){return s;});
  var res={proj:null,tags:[],text:[]};
  for(var i=0;i<t.length;i++){
    var v=t[i];
    if(v.startsWith("project:")) res.proj=v.slice(8);
    else if(v.startsWith("tag:")) res.tags.push(v.slice(4));
    else res.text.push(v);
  }
  return res;
}
function matches(t, f){
  if(f.proj && (t.project||"").toLowerCase().indexOf(f.proj)===-1) return false;
  for(var i=0;i<f.tags.length;i++){
    if(!t.tags || t.tags.map(function(x){return (x||"").toLowerCase();}).indexOf(f.tags[i])===-1) return false;
  }
  var hay=(t.desc||"").toLowerCase()+" "+(t.project||"").toLowerCase()+" "+(t.tags||[]).join(" ").toLowerCase();
  for(var j=0;j<f.text.length;j++){ if(hay.indexOf(f.text[j])===-1) return false; }
  return true;
}
// helper: collapse full UUIDs to short (8 chars)
function shortenUUIDs(s){
  return String(s || '').replace(
    /\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b/gi,
    m => m.slice(0, 8)
  );
}

/* ===== Drawer list ===== */
function renderList(){
  list.innerHTML="";
  count.textContent="Loaded: "+TASKS.length;
  var f=parseQuery(q ? q.value : "");
  var filtered;
  if ((q && q.value && q.value.trim()) || (hideHasDeps && hideHasDeps.checked)){
    filtered=TASKS.filter(function(t){return matches(t,f);});
    if (hideHasDeps && hideHasDeps.checked){ filtered = filtered.filter(function(t){ return !t.has_depends; }); }
  } else { filtered=TASKS.slice(); }
  var byProj={}, i;
  for(i=0;i<filtered.length;i++){
    var p=filtered[i].project||"(no project)";
    if(!byProj[p]) byProj[p]=[];
    byProj[p].push(filtered[i]);
  }
  var keys=Object.keys(byProj).sort();
  for(i=0;i<keys.length;i++){
    var proj=keys[i];
    var sec=document.createElement('div'); sec.className="section"; sec.textContent=proj+" ("+byProj[proj].length+")";
    list.appendChild(sec);
    var arr=byProj[proj];
    for(var k=0;k<arr.length;k++){
      var t=arr[k];
      var el=document.createElement('div'); el.className="item";
      el.innerHTML='<div class="short">'+t.short+'</div><div class="desc">'+escapeHtml(t.desc)+'</div>';
      // place INSIDE its project/tag bubble (grid)
      el.addEventListener('mousedown', (function(task){
        return function(e){ if(e.button!==0) return; addToBuilder(task, null, null); };
      })(t));
      list.appendChild(el);
    }
  }
  if(!filtered.length){
    var empty=document.createElement('div'); empty.className="meta"; empty.textContent="No tasks.";
    list.appendChild(empty);
  }
}

/* ===== Keys & helpers ===== */
function keyPT(project, tag){ return (project||"(no project)") + "||" + (tag||"(no tag)"); }
function firstTag(t){ return (t.tags && t.tags.length) ? t.tags[0] : "(no tag)"; }

/* ===== Areas: projects & tags ===== */
function ensureProjectArea(project){
  var p=project||"(no project)";
  var a = projectAreas.get(p);
  if(!a){
    // stack vertically: place after bottom-most project
    var maxBottom = 20, first = true;
    projectAreas.forEach(function(pa){ first=false; maxBottom = Math.max(maxBottom, pa.y + (pa.h||0)); });
    var y = first ? 20 : (maxBottom + LAYOUT.AREA_GAP);
    a = { x:20, y:y, w:280, h:120, tagCols:LAYOUT.TAG_COLS, tagW0:(LAYOUT.TAG_PAD*2+LAYOUT.CELL_W),
          tagH0:(LAYOUT.TAG_HEAD + LAYOUT.TAG_PAD + 140), nextTagIndex:0, el:null };
    projectAreas.set(p,a);
  }
  return a;
}
function ensureTagArea(project, tag){
  var p = project || "(no project)";
  var t = tag || "(no tag)";
  var k = keyPT(p, t);
  var ta = tagAreas.get(k);
  if (ta) return ta;

  var pa = ensureProjectArea(p);
  var idx = pa.nextTagIndex++;
  var c = idx % pa.tagCols;
  var r = Math.floor(idx / pa.tagCols);
  var tx = pa.x + LAYOUT.AREA_PAD + c*(pa.tagW0 + LAYOUT.COL_GAP);
  var ty = pa.y + LAYOUT.PROJ_HEAD + LAYOUT.AREA_PAD + r*(pa.tagH0 + LAYOUT.ROW_GAP);

  ta = { x:tx, y:ty, w:pa.tagW0, h:pa.tagH0, project:p, tag:t, el:null };
  ta._cols = new Array(LAYOUT.COLS).fill(ta.y + LAYOUT.TAG_HEAD + LAYOUT.TAG_PAD);
  tagAreas.set(k, ta);
  updateProjectBoundsFromTags(p);
  return ta;
}
function renameTagAreaKey(oldProj, tag, newProj){
  var oldKey = keyPT(oldProj, tag);
  var ta = tagAreas.get(oldKey);
  if (!ta) return;
  tagAreas.delete(oldKey);
  ta.project = newProj;
  tagAreas.set(keyPT(newProj, tag), ta);
}
function updateProjectBoundsFromTags(project){
  var pa = ensureProjectArea(project);
  var maxR = pa.x + 260, maxB = pa.y + 120;
  tagAreas.forEach(function(ta){
    if (ta.project !== project) return;
    maxR = Math.max(maxR, ta.x + ta.w);
    maxB = Math.max(maxB, ta.y + ta.h);
  });
  pa.w = (maxR - pa.x) + LAYOUT.AREA_PAD;
  pa.h = (maxB - pa.y) + LAYOUT.AREA_PAD;
}

/* ===== Node helpers ===== */
function nodesForTag(project, tag){
  return Array.from(builderStage.querySelectorAll('.node'))
    .filter(function(n){ return n.getAttribute('data-proj') === (project||"(no project)") && n.getAttribute('data-tag') === (tag||"(no tag)"); });
}
function moveNodesForTag(project, tag, dx, dy){
  nodesForTag(project, tag).forEach(function(n){
    var x = parseInt(n.style.left||"0",10), y = parseInt(n.style.top||"0",10);
    n.style.left = ((x+dx)|0) + "px";
    n.style.top  = ((y+dy)|0) + "px";
  });
}

/* ===== Overlap detection & resolution ===== */
function rectsOverlap(a,b){
  return (a.x < b.x + b.w) && (a.x + a.w > b.x) && (a.y < b.y + b.h) && (a.y + a.h > b.y);
}

/* Tag-level magnetic push (within one project) */
function resolveTagOverlaps(project){
  var tags=[];
  tagAreas.forEach(function(ta){ if (ta.project===project) tags.push(ta); });
  if (tags.length<=1) { updateProjectBoundsFromTags(project); return; }

  // sort top-to-bottom, then left-to-right for stable pushes
  tags.sort(function(a,b){ return (a.y-b.y) || (a.x-b.x); });

  var changed=true, safety=0;
  while (changed && safety<50){
    changed=false; safety++;
    for (var i=0;i<tags.length;i++){
      for (var j=0;j<tags.length;j++){
        if (i===j) continue;
        var A=tags[i], B=tags[j];
        if (!rectsOverlap(A,B)) continue;
        // Push the lower one down; if heights equal, push B
        var target = (A.y <= B.y) ? B : A;
        var other  = (target===B) ? A : B;
        var newY = other.y + other.h + LAYOUT.ROW_GAP;
        var dy = newY - target.y;
        if (dy <= 0) dy = (other.h/2 + LAYOUT.ROW_GAP); // fallback
        target.y += dy;
        if (target.el){ target.el.style.top = (target.y|0)+"px"; }
        moveNodesForTag(target.project, target.tag, 0, dy);
        changed=true;
      }
    }
  }
  updateProjectBoundsFromTags(project);
}

/* Project-level magnetic push (between projects) */
function moveWholeProject(project, dx, dy){
  var pa = projectAreas.get(project); if (!pa) return;
  pa.x += dx; pa.y += dy;
  if (pa.el){ pa.el.style.left=(pa.x|0)+"px"; pa.el.style.top=(pa.y|0)+"px"; }
  // move children tags and their nodes
  tagAreas.forEach(function(ta){
    if (ta.project !== project) return;
    ta.x += dx; ta.y += dy;
    if (ta.el){ ta.el.style.left=(ta.x|0)+"px"; ta.el.style.top=(ta.y|0)+"px"; }
    moveNodesForTag(ta.project, ta.tag, dx, dy);
  });
}
function resolveProjectOverlaps(){
  var projs=[];
  projectAreas.forEach(function(pa, name){ projs.push({name:name, pa:pa}); });
  if (projs.length<=1) return;
  projs.sort(function(a,b){ return (a.pa.y - b.pa.y) || (a.pa.x - b.pa.x); });

  var changed=true, safety=0;
  while (changed && safety<50){
    changed=false; safety++;
    for (var i=0;i<projs.length;i++){
      for (var j=0;j<projs.length;j++){
        if (i===j) continue;
        var A=projs[i].pa, B=projs[j].pa;
        var aRect={x:A.x,y:A.y,w:A.w,h:A.h}, bRect={x:B.x,y:B.y,w:B.w,h:B.h};
        if (!rectsOverlap(aRect,bRect)) continue;
        // push the lower one down
        var targetIdx = (A.y <= B.y) ? j : i;
        var otherIdx  = (targetIdx===j) ? i : j;
        var target = projs[targetIdx]; var other = projs[otherIdx];
        var newY = other.pa.y + other.pa.h + LAYOUT.AREA_GAP;
        var dy = newY - target.pa.y; if (dy<=0) dy = other.pa.h/2 + LAYOUT.AREA_GAP;
        moveWholeProject(target.name, 0, dy);
        changed=true;
      }
    }
  }
}

/* ===== Relayout (no task overlap inside a tag) ===== */
function relayoutTag(project, tag){
  var ta = ensureTagArea(project, tag);
  var nodes = nodesForTag(project, tag);
  if (!nodes.length) return;

  ta._cols = new Array(LAYOUT.COLS).fill(ta.y + LAYOUT.TAG_HEAD + LAYOUT.TAG_PAD);
  var colX = [];
  for (var c=0;c<LAYOUT.COLS;c++){
    colX[c] = ta.x + LAYOUT.TAG_PAD + c*(LAYOUT.CELL_W + LAYOUT.COL_GAP);
  }
  var maxRight = ta.x + ta.w, maxBottom = ta.y + ta.h;

  nodes.forEach(function(n){
    var col = 0, minY = ta._cols[0];
    for (var i=1;i<LAYOUT.COLS;i++){ if (ta._cols[i] < minY){ minY = ta._cols[i]; col = i; } }
    var nx = colX[col];
    var ny = minY;
    n.style.left = nx+"px";
    n.style.top  = ny+"px";
    var h = n.offsetHeight;
    ta._cols[col] = ny + h + LAYOUT.ROW_GAP;
    maxRight = Math.max(maxRight, nx + LAYOUT.CELL_W + LAYOUT.TAG_PAD);
    maxBottom = Math.max(maxBottom, ny + h + LAYOUT.TAG_PAD);
  });

  ta.w = Math.max(ta.w, maxRight - ta.x);
  ta.h = Math.max(ta.h, maxBottom - ta.y);

  updateProjectBoundsFromTags(project);
  recomputeAreasAndTags();
  resolveTagOverlaps(project);
  resolveProjectOverlaps();
}

/* ===== Redraw areas with draggable labels ===== */
function recomputeAreasAndTags(){
  areasLayer.innerHTML=""; tagsLayer.innerHTML="";
  // projects
  projectAreas.forEach(function(pa, proj){
    var pd = document.createElement('div');
    pd.className = "projArea";
    pd.style.left = (pa.x|0)+"px"; pd.style.top=(pa.y|0)+"px";
    pd.style.width = (pa.w|0)+"px"; pd.style.height = (pa.h|0)+"px";
    pd.setAttribute('data-proj', proj);
    var pl = document.createElement('div');
    pl.className="projAreaLabel"; if (proj==="(no project)") pl.classList.add('none');
    pl.textContent = proj;
    pd.appendChild(pl);
    // Apply project palette
    try {
      var ppal = projectPalette(proj);
      pd.style.background = ppal.bg;
      pd.style.borderColor = ppal.border;
      pl.style.background = ppal.labelBg;
    } catch(_) {}

    areasLayer.appendChild(pd);
    pa.el = pd;
    pl.addEventListener('mousedown', function(e){ startProjectDrag(e, pa); });
  });
  // tags
  tagAreas.forEach(function(ta){
    if (!projectAreas.has(ta.project)) return;
    var td = document.createElement('div');
    td.className="tagArea";
    td.style.left=(ta.x|0)+"px"; td.style.top=(ta.y|0)+"px";
    td.style.width=(ta.w|0)+"px"; td.style.height=(ta.h|0)+"px";
    td.setAttribute('data-proj', ta.project);
    td.setAttribute('data-tag', ta.tag);
    var tl = document.createElement('div');
    tl.className="tagAreaLabel"; if (ta.tag==="(no tag)") tl.classList.add('none');
    tl.textContent = ta.tag;
    // Apply per-tag palette
    var pal = tagPalette(ta.tag);
    td.style.background = pal.bg;
    td.style.borderColor = pal.border;
    tl.style.background = pal.labelBg;
    tl.style.borderRadius = "999px";
    tl.style.paddingRight = "28px"; // room for the + button

    // Add a per-tag '+' button
    var addBtn = document.createElement('button');
    addBtn.addEventListener('mousedown', function(e){ e.stopPropagation(); e.preventDefault(); });
        addBtn.className = 'tagAddBtn';
    addBtn.textContent = '＋';
    addBtn.title = 'Add task to tag “'+ta.tag+'”';
    addBtn.style.position = 'absolute';
    addBtn.style.right = '6px';
    addBtn.style.top = '6px';
    addBtn.style.width = '20px';
    addBtn.style.height = '20px';
    addBtn.style.border = '1px solid #2a3344';
    addBtn.style.borderRadius = '50%';
    addBtn.style.background = '#1b2230';
    addBtn.style.color = 'var(--fg)';
    addBtn.style.cursor = 'pointer';
    addBtn.addEventListener('click', function(e){
      e.stopPropagation();
      var desc = prompt("New task description:", "");
      if (!desc) return;
      var uuid = "new-"+Date.now().toString(36)+Math.random().toString(36).slice(2,6);
      var t = { uuid:uuid, short:uuid.slice(0,8), desc:desc, project: ta.project, tags:[ta.tag], has_depends:false };
      TASKS.push(t); TASK_BY_SHORT[t.short]=t;
      renderList();
      ensureTagArea(ta.project, ta.tag);
      addToBuilder(t, null, null);
      updateConsole();
    });
    tl.appendChild(addBtn);

    td.appendChild(tl);
    tagsLayer.appendChild(td);
    ta.el = td;
    tl.addEventListener('mousedown', function(e){ startTagDrag(e, ta); });
  });

  try{queueVirt&&queueVirt();}catch(e){} // Tw Patch hook
}

/* ===== Hit testing ===== */
function areaAtPoint(x, y){
  var within = null;
  tagAreas.forEach(function(ta){
    if (x>=ta.x && x<=ta.x+ta.w && y>=ta.y && y<=ta.y+ta.h){
      within = {type:'tag', area:ta};
    }
  });
  if (within) return within;
  projectAreas.forEach(function(pa, proj){
    if (x>=pa.x && x<=pa.x+pa.w && y>=pa.y && y<=pa.y+pa.h){
      within = {type:'project', area:pa, project:proj};
    }
  });
  return within;
}
function projectAtPoint(x, y){
  var found = null;
  projectAreas.forEach(function(pa, proj){
    if (x>=pa.x && x<=pa.x+pa.w && y>=pa.y && y<=pa.y+pa.h){ found = proj; }
  });
  return found;
}

/* ===== Selection & node dragging ===== */
var selected = new Set();
function clearSelection(){ selected.forEach(function(n){ n.classList.remove('selected');}); selected.clear(); }
function selectNode(n){ n.classList.add('selected'); selected.add(n); }

function makeDraggable(node){
  var dragging=false, group=false, sx=0, sy=0, start=[];
  node.addEventListener('mousedown', function(e){
    if (e.button!==0) return;
    if (removeMode && removeMode.checked) return;
    if (!node.classList.contains('selected')){ clearSelection(); selectNode(node); }
    dragging = true; group = (selected.size>1);
    sx = e.clientX; sy = e.clientY;
    start = [];
    (group?selected:new Set([node])).forEach(function(n){
      start.push({n:n, x: parseInt(n.style.left||"0",10), y: parseInt(n.style.top||"0",10)});
    });
    e.preventDefault();
  });
  document.addEventListener('mousemove', function(e){
    if(!dragging) return;
    var dx = (e.clientX - sx)/ZSCALE, dy = (e.clientY - sy)/ZSCALE;
    for (var i=0;i<start.length;i++){
      var sp = start[i];
      sp.n.style.left = ((sp.x+dx)|0)+"px";
      sp.n.style.top  = ((sp.y+dy)|0)+"px";
    }
  });
  document.addEventListener('mouseup', function(e){
    if(!dragging) return; dragging = false;
    for (var i=0;i<start.length;i++){
      var n = start[i].n;
      var shortId = n.getAttribute('data-short');
      var t = TASK_BY_SHORT[shortId]; if(!t) continue;
      var oldProj = t.project || "(no project)";
      var oldTag  = firstTag(t);
      var cx = parseInt(n.style.left||"0",10) + (n.offsetWidth/2);
      var cy = parseInt(n.style.top ||"0",10) + (n.offsetHeight/2);
      var hit = areaAtPoint(cx, cy);

      if (hit && hit.type==='tag'){
        var ta = hit.area;
        if (ta.project !== oldProj){
          t.project = ta.project; n.setAttribute('data-proj', t.project);
        }
        if (ta.tag !== oldTag){
          t.tags = (ta.tag==="(no tag)") ? [] : [ta.tag];
          n.setAttribute('data-tag', ta.tag);
        }
        n.querySelector('.caption').textContent = (t.project + ' • ' + (firstTag(t) || '(no tag)'));
        relayoutTag(ta.project, ta.tag);
      } else if (hit && hit.type==='project'){
        if (hit.project !== oldProj){
          t.project = hit.project; n.setAttribute('data-proj', t.project);
          n.querySelector('.caption').textContent = (t.project + ' • ' + (firstTag(t) || '(no tag)'));
          // reflow its current tag area under the new project, if present
          relayoutTag(t.project, firstTag(t));
        }
      } else {
        if (oldProj !== "(no project)"){
          t.project = "(no project)"; n.setAttribute('data-proj', t.project);
          n.querySelector('.caption').textContent = (t.project + ' • ' + (firstTag(t) || '(no tag)'));
          relayoutTag("(no project)", firstTag(t));
        }
      }
    }
    updateConsole();
    drawLinks();
  });
}

/* ===== Tag bubble dragging (snapshot + project-at-point) ===== */
var dragTag = null, dragTagStart = null, dragTagNodes = null;
function startTagDrag(e, ta){
  e.preventDefault();
  dragTag = ta;
  dragTagStart = { sx:e.clientX, sy:e.clientY, x:ta.x, y:ta.y };
  // snapshot node positions at start
  dragTagNodes = nodesForTag(ta.project, ta.tag).map(function(n){
    return { n:n, x: parseInt(n.style.left||"0",10), y: parseInt(n.style.top||"0",10) };
  });
  document.addEventListener('mousemove', onTagMove);
  document.addEventListener('mouseup', onTagUp, { once:true });
}
function onTagMove(e){
  if (!dragTag) return;
  var dx = (e.clientX - dragTagStart.sx)/ZSCALE, dy = (e.clientY - dragTagStart.sy)/ZSCALE;
  var nx = dragTagStart.x + dx, ny = dragTagStart.y + dy;
  dragTag.x = nx; dragTag.y = ny;
  if (dragTag.el){ dragTag.el.style.left = (nx|0)+"px"; dragTag.el.style.top = (ny|0)+"px"; }
  dragTagNodes.forEach(function(sp){
    sp.n.style.left = ((sp.x + dx)|0) + "px";
    sp.n.style.top  = ((sp.y + dy)|0) + "px";
  });
}
function onTagUp(e){
  document.removeEventListener('mousemove', onTagMove);
  if (!dragTag) return;
  var cx = dragTag.x + dragTag.w/2, cy = dragTag.y + 20;
  var newProj = projectAtPoint(cx, cy) || "(no project)";
  var oldProj = dragTag.project;

  if (newProj !== oldProj){
    renameTagAreaKey(oldProj, dragTag.tag, newProj);
    var items = dragTagNodes.map(function(sp){ return sp.n; });
    items.forEach(function(n){
      var t = TASK_BY_SHORT[n.getAttribute('data-short')];
      if (!t) return;
      t.project = newProj;
      n.setAttribute('data-proj', newProj);
      n.querySelector('.caption').textContent = (t.project + ' • ' + (firstTag(t) || '(no tag)'));
    });
    updateProjectBoundsFromTags(oldProj);
    updateProjectBoundsFromTags(newProj);
  }
  ensureProjectArea(newProj);
  recomputeAreasAndTags();
  relayoutTag(newProj, dragTag.tag);           // also resolves overlaps
  resolveProjectOverlaps();

  dragTag = null; dragTagStart = null; dragTagNodes = null;
  updateConsole();
}

/* ===== Project bubble dragging (snapshot) ===== */
var dragProj = null, dragProjStart = null, dragProjTags = null, dragProjNodes = null, dragProjName = null;
function startProjectDrag(e, pa){
  e.preventDefault();
  dragProj = pa;
  dragProjStart = { sx:e.clientX, sy:e.clientY, x:pa.x, y:pa.y };
  dragProjName = getProjName(pa);
  // snapshot child tags & nodes
  dragProjTags = [];
  dragProjNodes = [];
  tagAreas.forEach(function(ta){
    if (ta.project !== dragProjName) return;
    dragProjTags.push({ ta:ta, x:ta.x, y:ta.y });
    nodesForTag(ta.project, ta.tag).forEach(function(n){
      dragProjNodes.push({ n:n, x: parseInt(n.style.left||"0",10), y: parseInt(n.style.top||"0",10) });
    });
  });
  document.addEventListener('mousemove', onProjMove);
  document.addEventListener('mouseup', onProjUp, { once:true });
}
function onProjMove(e){
  if (!dragProj) return;
  var dx = (e.clientX - dragProjStart.sx)/ZSCALE, dy = (e.clientY - dragProjStart.sy)/ZSCALE;
  var nx = dragProjStart.x + dx, ny = dragProjStart.y + dy;
  dragProj.x = nx; dragProj.y = ny;
  if (dragProj.el){ dragProj.el.style.left = (nx|0)+"px"; dragProj.el.style.top = (ny|0)+"px"; }

  dragProjTags.forEach(function(sp){
    sp.ta.x = sp.x + dx; sp.ta.y = sp.y + dy;
    if (sp.ta.el){ sp.ta.el.style.left=(sp.ta.x|0)+"px"; sp.ta.el.style.top=(sp.ta.y|0)+"px"; }
  });
  dragProjNodes.forEach(function(sp){
    sp.n.style.left = ((sp.x + dx)|0) + "px";
    sp.n.style.top  = ((sp.y + dy)|0) + "px";
  });
}
function onProjUp(e){
  document.removeEventListener('mousemove', onProjMove);
  // snap against other projects if overlapping
  resolveProjectOverlaps();
  dragProj = null; dragProjStart = null; dragProjTags = null; dragProjNodes = null; dragProjName = null;
}

/* ===== Helpers ===== */
function getProjName(pa){
  for (const [k,v] of projectAreas){ if (v===pa) return k; }
  return "(no project)";
}

/* ===== Add nodes ===== */
function addNodeForTask(task, cx, cy, opts){
  opts = opts || {};
  var proj = task.project || "(no project)";
  var tag  = firstTag(task);
  ensureProjectArea(proj);
  ensureTagArea(proj, tag);
  recomputeAreasAndTags();

  var node = document.createElement('div');
  node.className="node";
  node.innerHTML = '<div class="title">'+escapeHtml(task.desc)+'</div><div class="caption">'+escapeHtml(proj+' • '+tag)+'</div>';
  node.setAttribute('data-short', task.short);
  node.setAttribute('data-proj', proj);
  node.setAttribute('data-tag', tag);
  builderStage.appendChild(node);

  if (cx != null && cy != null){
    node.style.left = (cx|0)+"px";
    node.style.top  = (cy|0)+"px";
  } else if (!opts.deferLayout){
    relayoutTag(proj, tag);
  }

  makeDraggable(node);
  try{queueVirt&&queueVirt();}catch(e){} // Tw Patch hook
  try{ attachDepHandleToNode(node); }catch(_){ }
  return node;
}

function addToBuilder(task, cx, cy){
  var r = builderStage.getBoundingClientRect();
  var x = (cx!=null? (cx - r.left)/ZSCALE : null);
  var y = (cy!=null? (cy - r.top )/ZSCALE : null);
  var n = addNodeForTask(task, x, y);
  try{ attachDepHandleToNode(n); }catch(_){ }
// If we placed with explicit coordinates, still normalize into the grid:
  if (x!=null && y!=null){
    relayoutTag(task.project || "(no project)", firstTag(task));
  }
  updateConsole();
  drawLinks();
  return n;
}

/* ===== Marquee selection ===== */
var marquee=null, mStart=null;
builderStage.addEventListener('mousedown', function(e){
  if (e.button!==0) return;
  if (e.target.closest('.node')) return;
  clearSelection();
  var rect = builderStage.getBoundingClientRect();
  mStart = {x:(e.clientX-rect.left)/ZSCALE, y:(e.clientY-rect.top)/ZSCALE};
  marquee = document.createElement('div');
  marquee.className="marquee";
  marquee.style.left = mStart.x+"px"; marquee.style.top = mStart.y+"px";
  marquee.style.width="0px"; marquee.style.height="0px";
  builderStage.appendChild(marquee);
});
document.addEventListener('mousemove', function(e){
  if (!marquee) return;
  var rect = builderStage.getBoundingClientRect();
  var x = (e.clientX-rect.left)/ZSCALE, y=(e.clientY-rect.top)/ZSCALE;
  var w = x - mStart.x, h=y - mStart.y;
  marquee.style.left = (w<0? x : mStart.x)+"px";
  marquee.style.top  = (h<0? y : mStart.y)+"px";
  marquee.style.width = Math.abs(w)+"px";
  marquee.style.height= Math.abs(h)+"px";
});
document.addEventListener('mouseup', function(e){
  if(!marquee) return;
  var mx = parseFloat(marquee.style.left), my=parseFloat(marquee.style.top);
  var mw = parseFloat(marquee.style.width), mh=parseFloat(marquee.style.height);
  var nodes = builderStage.querySelectorAll('.node');
  for (var i=0;i<nodes.length;i++){
    var n = nodes[i];
    var nx = parseInt(n.style.left,10)||0, ny=parseInt(n.style.top,10)||0;
    var nw = n.offsetWidth, nh=n.offsetHeight;
    if (nx < mx+mw && nx+nw > mx && ny < my+mh && ny+nh > my){ selectNode(n); }
  }
  marquee.remove(); marquee=null; mStart=null;
});

/* ===== Viewer (dependent tasks only) ===== */
function isDependentShort(shortId){
  if (!shortId) return false;
  if (PARENT_DEPS0 && PARENT_DEPS0[shortId] && PARENT_DEPS0[shortId].length) return true;
  if (CHILD_TO_PARENTS && CHILD_TO_PARENTS[shortId] && CHILD_TO_PARENTS[shortId].length) return true;
  return false;
}
function renderViewer(){
  viewerStage.innerHTML="";
  var depTasks = [];
  for (var i=0;i<TASKS.length;i++){
    var t=TASKS[i];
    if (isDependentShort(t.short)) depTasks.push(t);
  }
  if (!depTasks.length){
    var empty=document.createElement('div');
    empty.style.position="absolute"; empty.style.left="40px"; empty.style.top="40px";
    empty.textContent="No dependent tasks.";
    viewerStage.appendChild(empty);
    return;
  }
  var byProj={}, i;
  for(i=0;i<depTasks.length;i++){
    var p=depTasks[i].project||"(no project)";
    if(!byProj[p]) byProj[p]=[];
    byProj[p].push(depTasks[i]);
  }
  var keys=Object.keys(byProj).sort();
  var x=40;
  for(i=0;i<keys.length;i++){
    var col=document.createElement('div');
    col.style.position="absolute";
    col.style.left=(x|0)+"px"; col.style.top="40px";
    col.style.minWidth="260px";
    col.style.border="1px solid #2a3344";
    col.style.borderRadius="8px"; col.style.padding="8px";
    var title=document.createElement('div'); title.style.fontWeight="800"; title.textContent=keys[i]+" ("+byProj[keys[i]].length+")";
    col.appendChild(title);
    var arr=byProj[keys[i]];
    for(var k=0;k<arr.length;k++){
      var it=document.createElement('div'); it.style.margin="6px 0";
      it.innerHTML='<div class="short">'+arr[k].short+'</div><div class="desc">'+escapeHtml(arr[k].desc)+'</div>';
      col.appendChild(it);
    }
    viewerStage.appendChild(col);
    x+=320;
  }
}

/* ===== Zoom ===== */
function applyZoom(){
  var v = parseInt(zoom.value,10) || 100;
  ZSCALE = v / 100.0;
  builderStage.style.transform = "scale(" + ZSCALE + ")";
  viewerStage.style.transform  = "scale(" + ZSCALE + ")";
  zoomPct.textContent = v + "%";
}
zoom.addEventListener('input', applyZoom);
applyZoom();

/* ===== FAB actions ===== */
fab.addEventListener('click', function(){ fabMenu.classList.toggle('hidden'); });
document.addEventListener('click', function(e){
  if (e.target===fab || fabMenu.contains(e.target)) return;
  fabMenu.classList.add('hidden');
});

function uniqueByProject(){
  var set={}, arr=[];
  for (var i=0;i<TASKS.length;i++){
    var p=TASKS[i].project||"(no project)";
    if(!set[p]){ set[p]=1; arr.push(p); }
  }
  arr.sort();
  return arr;
}
function uniqueTagsForProject(project){
  var set={"(no tag)":1}, arr=["(no tag)"];
  for (var i=0;i<TASKS.length;i++){
    var t=TASKS[i];
    if ((t.project||"(no project)")===project){
      var tag = firstTag(t);
      if(!set[tag]){ set[tag]=1; arr.append ? 0 : 0; } // no-op placeholder (keep linter happy)
    }
  }
  // Manual to avoid accidental mutation above:
  set={"(no tag)":1}; arr=["(no tag)"];
  for (var i2=0;i2<TASKS.length;i2++){
    var tt=TASKS[i2];
    if ((tt.project||"(no project)")===project){
      var tg = firstTag(tt);
      if(!set[tg]){ set[tg]=1; arr.push(tg); }
    }
  }
  return arr;
}

function addProjectTasks(projName){
  var tags = uniqueTagsForProject(projName);
  ensureProjectArea(projName);
  for (var i=0;i<tags.length;i++){ ensureTagArea(projName, tags[i]); }
  recomputeAreasAndTags();

  // Add nodes with deferred layout
  var added=0;
  for (var i2=0;i2<TASKS.length;i2++){
    var t=TASKS[i2];
    if ((t.project||"(no project)")===projName){ addNodeForTask(t, null, null, {deferLayout:true}); added++; }
  }
  // Single relayout pass per tag + resolve overlaps
  for (var i3=0;i3<tags.length;i3++){ relayoutTag(projName, tags[i3]); }
  resolveTagOverlaps(projName);
  resolveProjectOverlaps();
  drawLinks();
  updateConsole();
  return added;
}

function addFilteredTasks(){
  var f=parseQuery(q ? q.value : "");
  var projectsOnCanvas = new Set();
  projectAreas.forEach(function(_,proj){ projectsOnCanvas.add(proj); });
  if (projectsOnCanvas.size===0){ alert("No projects on canvas. Add a project first."); return 0; }
  var added=0, skipped=0;
  var byPT = {};
  for (var i=0;i<TASKS.length;i++){
    var t=TASKS[i];
    if(!matches(t,f)) continue;
    if (hideHasDeps && hideHasDeps.checked && t.has_depends) continue;
    var p = t.project || "(no project)";
    if (!projectsOnCanvas.has(p)){ skipped++; continue; }
    var tag = firstTag(t);
    var k = keyPT(p, tag);
    (byPT[k] = byPT[k] || []).push(t);
  }
  Object.keys(byPT).forEach(function(k){
    var parts = k.split("||"); var p = parts[0], tag = parts[1];
    ensureTagArea(p, tag);
    byPT[k].forEach(function(t){ addNodeForTask(t, null, null, {deferLayout:true}); added++; });
    relayoutTag(p, tag);
    resolveTagOverlaps(p);
  });
  resolveProjectOverlaps();
  if (skipped>0){ alert("Skipped "+skipped+" task(s) from projects not on the canvas."); }
  drawLinks();
  updateConsole();
  return added;
}

fabAddProject.addEventListener('click', function(){
  fabMenu.classList.add('hidden');
  var projs = uniqueByProject();
  var msg = "Choose project to add:\n" + projs.map(function(p,idx){return (idx+1)+") "+p;}).join("\n");
  var choice = prompt(msg, "1");
  if (choice==null) return;
  var idx = parseInt(choice,10)-1;
  if (!isFinite(idx) || idx<0 || idx>=projs.length){ alert("Invalid selection"); return; }
  var p = projs[idx];
  var n = addProjectTasks(p);
  alert("Added "+n+" tasks from project '"+p+"'");
});
fabAddFiltered.addEventListener('click', function(){
  fabMenu.classList.add('hidden');
  var n = addFilteredTasks();
  if (n>0) alert("Added "+n+" task(s) from current filter to existing projects.");
});
fabAddNew.addEventListener('click', function(){
  fabMenu.classList.add('hidden');
  var desc = prompt("New task description:", "");
  if (!desc) return;
  var projs = uniqueByProject();
  var defProj = projs[0] || "(no project)";
  var project = prompt("Project (existing or new):", defProj) || "(no project)";
  var tagsIn = prompt("Tags (comma-separated):", "")||"";
  var tags = tagsIn.split(",").map(function(s){return s.trim();}).filter(function(s){return s;});
  var uuid = "new-"+Date.now().toString(36)+Math.random().toString(36).slice(2,6);
  var t = { uuid:uuid, short:uuid.slice(0,8), desc:desc, project:project, tags:tags, has_depends:false };
  TASKS.push(t); TASK_BY_SHORT[t.short]=t;
  renderList();
  if (projectAreas.has(project)){
    ensureTagArea(project, firstTag(t));
    addToBuilder(t, null, null);
  } else {
    alert("Task created. Add the project (“"+project+"”) to the canvas to place it.");
  }
  updateConsole();
});

/* ===== Command builder + console ===== */
function quote(s){ return '"' + String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"') + '"'; }
function buildCommands(){
  var lines=[];
  for (var i=0;i<TASKS.length;i++){
    var t=TASKS[i]; if (String(t.uuid).startsWith("new-")) continue;
    var oldTag = INIT_MAIN_TAG[t.short] || "(no tag)";
    var newTag = firstTag(t) || "(no tag)";
    var oldProj= INIT_PROJECT[t.short] || "(no project)";
    var newProj= t.project || "(no project)";
    var ops=[]; if (oldTag !== newTag){ if (oldTag !== "(no tag)") ops.push("-"+oldTag); if (newTag !== "(no tag)") ops.push("+"+newTag); }
    var projPart = null; if (oldProj !== newProj){ projPart = (newProj==="(no project)") ? "project:" : "project:"+newProj; }
    if (ops.length || projPart){ var cmd = "task "+t.uuid+" modify "; if (projPart) cmd += projPart + " "; if (ops.length) cmd += ops.join(" "); lines.push(cmd.trim()); }
  }
  for (var j=0;j<TASKS.length;j++){
    var n=TASKS[j]; if (!String(n.uuid).startsWith("new-")) continue;
    var parts = ["task add", n.desc];
    if (n.project && n.project!=="(no project)") parts.push("project:"+n.project);
    (n.tags||[]).forEach(function(tag){ if (tag && tag !== "(no tag)") parts.push("+"+tag); });
    lines.push(parts.join(" "));
  }
  return lines.join("\n");
}
function updateConsole(){ consoleText.value = buildCommands(); }
copyBtn.addEventListener('click', async function(){
  var cmds = buildCommands();
  if (!cmds){ alert("No changes to copy."); return; }
  try{ await navigator.clipboard.writeText(cmds); alert("Commands copied ("+cmds.split("\\n").length+" line(s))."); }
  catch(e){ prompt("Copy these commands:", cmds); }
});
copyBtn2.addEventListener('click', function(){ copyBtn.click(); });
toggleConsole.addEventListener('click', function(){ consolePanel.classList.toggle('open'); });

/* ===== Lines (placeholder) ===== */
function drawLinks(){ builderLinks.innerHTML = ""; }

/* ===== Boot ===== */
function initFromDATA(){
  try {
    var D = window.DATA || {};
    TASKS       = Array.isArray(D.tasks) ? D.tasks.slice() : [];
    TASK_BY_SHORT = {}; INIT_MAIN_TAG = {}; INIT_PROJECT  = {};
    for (var i=0;i<TASKS.length;i++){
      TASK_BY_SHORT[TASKS[i].short]=TASKS[i];
      INIT_MAIN_TAG[TASKS[i].short] = firstTag(TASKS[i]) || "(no tag)";
      INIT_PROJECT[TASKS[i].short]  = TASKS[i].project || "(no project)";
    }
    var G = (D.graph && typeof D.graph === "object") ? D.graph : {};
    PARENT_DEPS0     = (G.parent_current_deps && typeof G.parent_current_deps === "object") ? G.parent_current_deps : {};
    CHILD_TO_PARENTS = (G.child_to_parents && typeof G.child_to_parents === "object") ? G.child_to_parents : {};

    if (parsedBadge) parsedBadge.textContent = "Parsed: " + TASKS.length;
    if (hideHasDeps) hideHasDeps.checked = false;
    if (q) q.value = "";

    renderList();
    
    // __EXISTING_SOLID_V3B__ boot edges inside init
    try {
      var G2 = (D.graph && typeof D.graph === 'object') ? D.graph : {};
      window.EXIST_EDGES = (G2 && Array.isArray(G2.edges)) ? G2.edges.slice() : [];
    } catch(_){ window.EXIST_EDGES = []; }
    try { if (typeof refreshDepHandleLetters === 'function') refreshDepHandleLetters(); } catch(_){}
    try { if (typeof drawLinks === 'function') drawLinks(); } catch(_){}
projectAreas = new Map(); tagAreas = new Map(); // EMPTY canvas
    recomputeAreasAndTags();
    setMode('builder');

    collapseDrawer();  // start hidden
    // this helps to pre-load projects in the canvas when they are submitted as arguments to the script
    if (D && Array.isArray(D.init_projects) && D.init_projects.length) {
      // De-dupe while preserving order-ish
      var seen = Object.create(null);
      var wanted = D.init_projects.filter(function(p){
        p = (p || "(no project)");
        if (seen[p]) return false; seen[p] = 1; return true;
      });

      var addedAny = false;
      for (var i = 0; i < wanted.length; i++) {
        try {
          var n = addProjectTasks(wanted[i]);
          if (n > 0) addedAny = true;
        } catch(_) {}
      }
      try { resolveProjectOverlaps(); } catch(_){}
      try { drawLinks(); } catch(_){}
    }

    // --- Auto-place filtered tasks (from -f/--filter) as if added from the drawer
    try {
      var D = window.DATA || {};
      if (D && Array.isArray(D.init_task_uuids) && D.init_task_uuids.length) {
        // 1) map uuid->task
        var byUuid = window.UUID2TASK || (function(){
          var m = Object.create(null);
          (window.TASKS || []).forEach(function(t){ if (t && t.uuid) m[t.uuid] = t; });
          return m;
        })();

        // 2) already placed?
        var already = Object.create(null);
        Array.prototype.forEach.call(
          document.querySelectorAll('#builderStage .node'),
          function(n){
            var u = n.getAttribute('data-uuid') || n.getAttribute('data-short');
            if (u) already[u] = 1;
          }
        );

        // 3) group by Project/Tag & ensure bubbles first
        var groups = Object.create(null);
        var projectsNeeded = Object.create(null);
        D.init_task_uuids.forEach(function(u){
          var t = byUuid[u];
          if (!t) return;
          var id = String(t.uuid || t.short || '');
          if (already[id]) return;
          var p = t.project || '(no project)';
          var tag = (t.tags && t.tags.length ? t.tags[0] : '(no tag)');
          (groups[p+'||'+tag] = groups[p+'||'+tag] || []).push(t);
          (projectsNeeded[p] = projectsNeeded[p] || new Set()).add(tag);
        });

        var keys = Object.keys(groups);
        if (!keys.length) { /* nothing to place */ }
        else {
          Object.keys(projectsNeeded).forEach(function(p){
            ensureProjectArea(p);
            projectsNeeded[p].forEach(function(tag){ ensureTagArea(p, tag); });
          });
          recomputeAreasAndTags();

          // 4) append all nodes (deferLayout=true) — no relayout yet
          keys.forEach(function(k){
            groups[k].forEach(function(t){
              addNodeForTask(t, null, null, {deferLayout:true});
            });
          });

          // 5) relayout AFTER paint so offsetHeight is correct
          var doRelayout = function(){
            try {
              keys.forEach(function(k){
                var parts = k.split('||'); var p = parts[0], tag = parts[1];
                relayoutTag(p, tag);
                resolveTagOverlaps(p);
              });
              resolveProjectOverlaps();
              drawLinks();
            } catch(e){ console.log('[auto-place] relayout error', e); }
          };
          requestAnimationFrame(function(){ requestAnimationFrame(doRelayout); });
        }
      }
    } catch(e){ console.log('[auto-place] error', e); }



    updateConsole();
  } catch (e) { console.log('[TaskCanvas] initFromDATA error', e); }
}
document.addEventListener('twdata', function(){ initFromDATA(); }, { once:true });
window.addEventListener('load', function(){ if (window.DATA_READY) initFromDATA(); }, { once:true });
if(q) q.addEventListener('input', renderList);
if(hideHasDeps) hideHasDeps.addEventListener('change', renderList);
</script>

<script id="FEATURE_TOAST_UTIL_V1">(function(){
  if (window.__FEATURE_TOAST_UTIL_V1__) return; window.__FEATURE_TOAST_UTIL_V1__=true;
  function ensureToast(){
    var el = document.getElementById('devConsoleToast');
    if (!el){
      el = document.createElement('div');
      el.id = 'devConsoleToast';
      document.body.appendChild(el);
    }
    return el;
  }
  window.showToast = window.showToast || function(msg){
    try{
      var el = ensureToast();
      el.textContent = (msg==null ? '' : String(msg));
      el.classList.add('show');
      clearTimeout(el.__hide);
      el.__hide = setTimeout(function(){ el.classList.remove('show'); }, 1600);
    }catch(_){
      try{ console.log(msg); }catch(__){}
    }
  };
})();</script><script id="FEATURE_CONSOLE_LINE_ENFORCER_V3">(function(){
  if (window.__FEATURE_CONSOLE_LINE_ENFORCER_V3__) return; window.__FEATURE_CONSOLE_LINE_ENFORCER_V3__=true;

  // ---------- helpers ----------
  function qs(s,root){ return (root||document).querySelector(s); }
  function qsa(s,root){ return (root||document).querySelectorAll(s); }
  function pickCT(){
    return document.getElementById('consoleText')
        || qs('#consolePanel textarea#consoleText')
        || qs('#devConsoleDock textarea#consoleText')
        || qs('textarea#consoleText')
        || qs('#consolePanel textarea')
        || qs('#devConsoleDock textarea')
        || qs('textarea');
  }
  function splitLinesSmart(x){
    if (x == null) return [];
    var s = String(x).replace(/\r\n/g,'\n');
    // convert any literal \n into a real newline BEFORE splitting
    s = s.replace(/\\n/g, '\n');
    var parts = s.split('\n');
    var out=[], seen={};
    for (var i=0;i<parts.length;i++){
      var t = parts[i].trim();
      if (!t) continue;
      if (seen[t]) continue; seen[t]=1;
      out.push(t);
    }
    return out;
  }
  function normalizeTextarea(ct){
    if (!ct) return;
    var lines = splitLinesSmart(ct.value);
    var joined = lines.join('\n');
    if (ct.value !== joined){ ct.value = joined; }
  }
  function scheduleBurst(ms){
    var end = Date.now() + (ms||1500);
    if (window.__LINE_ENFORCER_TIMER__) return;
    window.__LINE_ENFORCER_TIMER__ = setInterval(function(){
      try{ normalizeTextarea(pickCT()); }catch(_){}
      if (Date.now() > end){ clearInterval(window.__LINE_ENFORCER_TIMER__); window.__LINE_ENFORCER_TIMER__=null; }
    }, 120);
  }

  // ---------- proxy the textarea .value so any writes are normalized ----------
  function proxyValue(ct){
    if (!ct || ct.__lineEnforcerProxied) return;
    ct.__lineEnforcerProxied = true;
    var proto = Object.getPrototypeOf(ct) || HTMLTextAreaElement.prototype;
    var desc  = Object.getOwnPropertyDescriptor(proto, 'value') || Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
    if (!desc || !desc.get || !desc.set) return;
    Object.defineProperty(ct, 'value', {
      get: function(){ return desc.get.call(this); },
      set: function(v){
        try{
          var norm = splitLinesSmart(v).join('\n');
          return desc.set.call(this, norm);
        } catch(e){
          try { return desc.set.call(this, v); } catch(_) {}
        }
      }
    });
    // normalize on interactions too
    ct.addEventListener('input',  function(){ try{ normalizeTextarea(ct); }catch(_){}});
    ct.addEventListener('change', function(){ try{ normalizeTextarea(ct); }catch(_){}});
    ct.addEventListener('paste',  function(){ setTimeout(function(){ try{ normalizeTextarea(ct); }catch(_){}} , 10); });
  }

  // ---------- wrap stageAdd / stageToggle if present ----------
  function wrapStageAdd(){
    var orig = window.stageAdd;
    window.stageAdd = function(cmd, human){
      try{
        var parts = splitLinesSmart(Array.isArray(cmd) ? cmd.join('\n') : String(cmd||''));
        if (parts.length === 0) return;
        for (var i=0;i<parts.length;i++){
          if (typeof orig === 'function'){
            try{ orig.call(this, parts[i], human); }catch(_){}
          }
        }
      } finally {
        try{ scheduleBurst(1200); }catch(_){}
      }
    };
  }
  function wrapStageToggle(){
    var orig = window.stageToggle;
    if (typeof orig !== 'function') return;
    window.stageToggle = function(uuid, action, human){
      try{
        return orig.apply(this, arguments);
      } finally {
        try{ scheduleBurst(1200); }catch(_){}
      }
    };
  }

  // ---------- intercept copy buttons to normalize before copy ----------
  function wireCopy(){
    var ids = ['btnCopy','copyBtn','copyBtn2'];
    for (var i=0;i<ids.length;i++){
      var b = document.getElementById(ids[i]);
      if (!b || b.__lineEnforcerCopy) continue;
      b.__lineEnforcerCopy = true;
      b.addEventListener('click', function(ev){
        try{ normalizeTextarea(pickCT()); }catch(_){}
      }, true);
    }
  }

  function boot(){
    var ct = pickCT(); if (ct) proxyValue(ct);
    wrapStageAdd(); wrapStageToggle(); wireCopy();
    scheduleBurst(1500);
    // watch for console replacements
    var root = document.body;
    var mo = new MutationObserver(function(){ var ct=pickCT(); if (ct) proxyValue(ct); wireCopy(); });
    mo.observe(root, {childList:true, subtree:true});
  }

  window.addEventListener('load', function(){ setTimeout(boot, 60); });
  document.addEventListener('twdata', function(){ setTimeout(boot, 0); });
})();</script><script id="FEATURE_COPY_FULL_OVERRIDE_V1">(function(){
  if (window.__FEATURE_COPY_FULL_OVERRIDE_V1__) return; window.__FEATURE_COPY_FULL_OVERRIDE_V1__=true;

  function qs(s,root){ return (root||document).querySelector(s); }
  function qsa(s,root){ return (root||document).querySelectorAll(s); }
  function pickCT(){
    return document.getElementById('consoleText')
        || qs('#consolePanel textarea#consoleText')
        || qs('#devConsoleDock textarea#consoleText')
        || qs('#devConsoleDock textarea')
        || qs('#consolePanel textarea')
        || qs('textarea');
  }
  function normalize(str){
    if (str==null) return '';
    // turn literal \n into real newlines, standardize CRLF
    var s = String(str).replace(/\r\n/g,'\n').replace(/\\n/g,'\n');
    // split/trim/filter and rejoin so count is accurate
    var lines = s.split('\n').map(function(t){return t.trim();}).filter(Boolean);
    return lines.join('\n');
  }
  function countLines(s){
    if (!s) return 0;
    return String(s).split(/\r?\n/).filter(function(t){return t.trim().length>0;}).length;
  }
  function toast(msg){
    if (typeof window.showToast === 'function') return window.showToast(msg);
    try{ console.log(msg); }catch(_){}
  }

  function overrideCopyOn(el){
    if (!el || el.__copyFullOverride) return;
    el.__copyFullOverride = true;
    var handler = function(ev){
      try{ ev.preventDefault(); ev.stopImmediatePropagation(); ev.stopPropagation(); }catch(_){}
      var ct = pickCT();
      var txt = normalize(ct && ct.value || '');
      if (!txt){
        toast('No changes to copy.'); 
        return;
      }
      var n = countLines(txt);
      function ok(){ toast('Copied '+n+' line(s).'); }
      function fb(){
        try{
          var ta=document.createElement('textarea');
          ta.value = txt; document.body.appendChild(ta);
          ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
          ok();
        }catch(e){ alert('Copy failed'); }
      }
      if (navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(txt).then(ok).catch(fb);
      } else {
        fb();
      }
    };
    // capture + bubble + onclick to fully replace any existing behavior
    el.addEventListener('click', handler, true);
    el.addEventListener('click', handler, false);
    el.onclick = handler;
  }

  function wireAllCopies(){
    var dock = document.getElementById('devConsoleDock') || document;
    // common ids first
    ['btnCopy','copyBtn','copyBtn2'].forEach(function(id){
      var b = document.getElementById(id);
      if (b) overrideCopyOn(b);
    });
    // any button-like in the dock that says "copy"
    var btns = qsa('button, [role="button"]', dock);
    for (var i=0;i<btns.length;i++){
      var b = btns[i];
      if (/copy/i.test(b.id) || /copy/i.test(b.textContent||'')){
        overrideCopyOn(b);
      }
    }
  }

  function boot(){
    wireAllCopies();
    // watch for dynamic replacements
    var root = document.getElementById('devConsoleDock') || document.body;
    if (!root.__copyOvMO){
      root.__copyOvMO = true;
      var mo = new MutationObserver(function(){ wireAllCopies(); });
      mo.observe(root, {childList:true, subtree:true});
    }
  }

  window.addEventListener('load', function(){ setTimeout(boot, 60); });
  document.addEventListener('twdata', function(){ setTimeout(boot, 0); });
})();</script>

<script id="FEATURE_SINGLE_CONSOLE_AUGMENT_V1">(function(){
  if (window.__FEATURE_SINGLE_CONSOLE_AUGMENT_V1__) return; window.__FEATURE_SINGLE_CONSOLE_AUGMENT_V1__=true;

  // -------- helpers --------
  function qs(s,root){ return (root||document).querySelector(s); }
  function qsa(s,root){ return (root||document).querySelectorAll(s); }
  function pad2(n){ return (n<10?'0':'')+n; }
  function nowStr(){ var d=new Date(); return pad2(d.getHours())+':'+pad2(d.getMinutes())+':'+pad2(d.getSeconds()); }
  function splitLines(s){
    if (s==null) return [];
    return String(s).replace(/\r\n/g,'\n').replace(/\\n/g,'\n').split('\n').map(function(t){return t.trim();}).filter(Boolean);
  }
  function buildMaps(){
    if (!window.__DESC_BY_UUID__) window.__DESC_BY_UUID__ = Object.create(null);
    if (!window.__DESC_BY_SHORT__) window.__DESC_BY_SHORT__ = Object.create(null);
    if (!window.__CMD_TS__) window.__CMD_TS__ = Object.create(null);
    if (window.__DESC_BUILT__) return;
    try{
      if (window.DATA && Array.isArray(window.DATA.tasks)){
        for (var i=0;i<DATA.tasks.length;i++){
          var t = DATA.tasks[i];
          var uuid = t.uuid, short = t.short || String(uuid||'').slice(0,8);
          var desc = t.desc || t.description || '';
          if (uuid) window.__DESC_BY_UUID__[uuid] = desc;
          if (short) window.__DESC_BY_SHORT__[short] = desc;
        }
      }
    }catch(_){}
    window.__DESC_BUILT__ = true;
  }
  function parseAddDesc(cmd){
    // task add <desc words...> [k:v | +tag | -tag | due:...]*
    var m = /^task\s+add\s+(.+)$/i.exec(cmd);
    if (!m) return '';
    var rest = m[1];
    var toks = rest.split(/\s+/);
    var out=[];
    for (var i=0;i<toks.length;i++){
      var tk = toks[i];
      if (/^[+-][^\s]+$/.test(tk)) break;
      if (/^[a-z0-9_-]+:/.test(tk)) break;
      out.push(tk);
    }
    return out.join(' ');
  }
  function findDescForCmd(cmd){
    cmd = String(cmd||'');
    var m = /^task\s+([0-9a-f-]{8,})\b/i.exec(cmd);
    if (m){ // modify/done/delete
      var id = m[1];
      return window.__DESC_BY_UUID__[id] || window.__DESC_BY_SHORT__[id.slice(0,8)] || '';
    }
    if (/^task\s+add\b/i.test(cmd)){
      return parseAddDesc(cmd);
    }
    return '';
  }
  function ensureTs(cmd){
    if (!window.__CMD_TS__) window.__CMD_TS__ = Object.create(null);
    if (!window.__CMD_TS__[cmd]) window.__CMD_TS__[cmd] = nowStr();
    return window.__CMD_TS__[cmd];
  }
  function augmentLine(cmd){
    var raw = String(cmd||'').trim();
    if (!raw) return '';
    // If already augmented (contains " > task "), strip to raw first
    var i = raw.indexOf(' > task ');
    if (i !== -1){ raw = raw.slice(i+3).trim(); }
    return raw;
  function stripAugment(s){
    var lines = splitLines(s);
    var out=[];
    for (var i=0;i<lines.length;i++){
      var L = lines[i];
      var j = L.indexOf(' > task ');
      if (j !== -1) out.push(L.slice(j+3).trim());
      else out.push(L);
    }
    return out.join('\n');
  }

  // -------- wrap updateConsole --------
  function wrapUpdate(){
    var orig = window.updateConsole;
    window.updateConsole = function(){
      buildMaps();
      var rv;
      if (typeof orig === 'function'){ try{ rv = orig.apply(this, arguments); }catch(_){ } }
      try{
        var ta = document.getElementById('consoleText') || qs('#devConsoleDock textarea#consoleText') || qs('#consolePanel textarea#consoleText');
        if (!ta) return rv;
        var rawLines = splitLines( stripAugment(ta.value) );
        var aug = rawLines.map(augmentLine).join('\n');
        if (aug !== ta.value) ta.value = aug;
      }catch(_){}
      return rv;
    };
  }

  // -------- ensure copy copies RAW commands only --------
  function wireCopyRaw(){
    var btnIds = ['btnCopy','copyBtn','copyBtn2'];
    btnIds.forEach(function(id){
      var b = document.getElementById(id);
      if (!b || b.__augRaw) return;
      b.__augRaw = true;
      b.addEventListener('mousedown', function(){
        try{
          var ta = document.getElementById('consoleText') || qs('#devConsoleDock textarea#consoleText') || qs('#consolePanel textarea#consoleText');
          if (!ta) return;
          b.__augPrev = ta.value;
          ta.value = stripAugment(ta.value);
        }catch(_){}
      }, true);
      b.addEventListener('mouseup', function(){
        setTimeout(function(){
          try{
            var ta = document.getElementById('consoleText') || qs('#devConsoleDock textarea#consoleText') || qs('#consolePanel textarea#consoleText');
            if (!ta) return;
            if (b.__augPrev != null){ ta.value = b.__augPrev; b.__augPrev = null; }
            // force re-augment in case copy handler normalized content
            var ev = new Event('input'); ta.dispatchEvent(ev);
          }catch(_){}
        }, 60);
      }, true);
    });
  }

  function boot(){
    buildMaps();
    wrapUpdate();
    wireCopyRaw();
    // normalize once on load
    if (typeof window.updateConsole === 'function'){ try{ window.updateConsole(); }catch(_){ } }
    var mo = new MutationObserver(function(){ wireCopyRaw(); });
    mo.observe(document.body, {childList:true, subtree:true});
  }
  window.addEventListener('load', function(){ setTimeout(boot, 80); });
  document.addEventListener('twdata', function(){ setTimeout(boot, 0); });
})();</script>


<script id="FEATURE_DEDUPE_FOCUS_V1">(function(){
  if (window.__FEATURE_DEDUPE_FOCUS_V1__) return; window.__FEATURE_DEDUPE_FOCUS_V1__=true;

  function qs(s,root){ return (root||document).querySelector(s); }
  function canvasEl(){ return qs('#builderWrap .canvas'); }
  function centerIntoView(el){
    if (!el) return;
    var cv = canvasEl(); if (!cv) return;
    var cvr = cv.getBoundingClientRect();
    var er  = el.getBoundingClientRect();
    var elCx = er.left + er.width/2;
    var elCy = er.top  + er.height/2;
    var cvCx = cvr.left + cvr.width/2;
    var cvCy = cvr.top  + cv.clientHeight/2;
    var dx = elCx - cvCx;
    var dy = elCy - cvCy;
    var targetLeft = cv.scrollLeft + dx;
    var targetTop  = cv.scrollTop  + dy;
    targetLeft = Math.max(0, Math.min(cv.scrollWidth  - cv.clientWidth,  targetLeft));
    targetTop  = Math.max(0, Math.min(cv.scrollHeight - cv.clientHeight, targetTop));
    cv.scrollTo({ left: targetLeft, top: targetTop, behavior: 'smooth' });
    try{ el.classList.add('pulse'); setTimeout(function(){ el.classList.remove('pulse'); }, 820);}catch(_){}
  }

  (function(){
    var orig = window.addNodeForTask;
    if (typeof orig !== 'function') return;
    window.addNodeForTask = function(task, cx, cy, opts){
      try{
        var uuid = task && task.uuid || '';
        if (/^new[-_]/i.test(uuid)){
          return orig.call(this, task, cx, cy, opts);
        }
        if (uuid){
          var exU = document.querySelector('.node[data-uuid="'+uuid+'"]');
          if (exU) return exU;
        }
        var short = task && task.short;
        if (short){
          var exS = document.querySelector('.node[data-short="'+short+'"]');
          if (exS) return exS;
        }
      }catch(_){}
      return orig.call(this, task, cx, cy, opts);
    };
  })();

  (function(){
    var orig = window.addToBuilder;
    if (typeof orig !== 'function') return;
    window.addToBuilder = function(task, cx, cy){
      var node = null;
      try{
        var uuid = task && task.uuid || '';
        if (/^new[-_]/i.test(uuid)){
          node = orig.call(this, task, cx, cy);
          requestAnimationFrame(function(){ centerIntoView(node); });
          return node;
        }
        var short = task && task.short;
        var existing = null;
        if (uuid) existing = document.querySelector('.node[data-uuid="'+uuid+'"]');
        if (!existing && short) existing = document.querySelector('.node[data-short="'+short+'"]');
        node = existing || orig.call(this, task, cx, cy);
        requestAnimationFrame(function(){ centerIntoView(node); });
        return node;
      }catch(e){
        try{ return orig.call(this, task, cx, cy); }catch(_){ return null; }
      }
    };
  })();

})();</script>


<script id="FEATURE_PROJECT_ADD_TAG_V4">(function(){
  if (window.__FEATURE_PROJECT_ADD_TAG_V4__) return; window.__FEATURE_PROJECT_ADD_TAG_V4__=true;

  function qs(s,root){ return (root||document).querySelector(s); }
  function qsa(s,root){ return (root||document).querySelectorAll(s); }
  function text(el){ return (el && (el.textContent||'').trim()) || ''; }
  function canvasEl(){ return qs('#builderWrap .canvas'); }
  function centerIntoView(el){
    if (!el) return;
    var cv = canvasEl(); if (!cv) return;
    var cvr = cv.getBoundingClientRect();
    var er  = el.getBoundingClientRect();
    var elCx = er.left + er.width/2;
    var elCy = er.top  + er.height/2;
    var cvCx = cvr.left + cvr.width/2;
    var cvCy = cvr.top  + cv.clientHeight/2;
    var dx = elCx - cvCx;
    var dy = elCy - cvCy;
    var targetLeft = cv.scrollLeft + dx;
    var targetTop  = cv.scrollTop  + dy;
    targetLeft = Math.max(0, Math.min(cv.scrollWidth  - cv.clientWidth,  targetLeft));
    targetTop  = Math.max(0, Math.min(cv.scrollHeight - cv.clientHeight, targetTop));
    cv.scrollTo({ left: targetLeft, top: targetTop, behavior: 'smooth' });
  }
  function CSSescape(s){
    return String(s).replace(/(["\#.:;?*+^$[\]()%!@<>=|{}])/g, '\\$1');
  }

  function getProjFromLabel(label){
    if (!label) return '';
    var holder = label.closest('[data-proj]') || label.closest('[data-project]');
    if (holder){
      var dp = holder.getAttribute('data-proj') || holder.getAttribute('data-project');
      if (dp) return dp;
    }
    var cached = label.getAttribute('data-projname');
    if (cached) return cached;
    var t = text(label);
    if (/\+\s*$/.test(t)) t = t.replace(/\+\s*$/,'').trim();
    return t;
  }

  function ensureButtons(){
    var labels = qsa('.projAreaLabel');
    for (var i=0;i<labels.length;i++){
      var lab = labels[i];
      if (lab.__hasAddTagBtn) continue;

      var proj = (lab.closest('[data-proj]') && lab.closest('[data-proj]').getAttribute('data-proj'))
                 || (lab.closest('[data-project]') && lab.closest('[data-project]').getAttribute('data-project'))
                 || text(lab);
      if (proj) lab.setAttribute('data-projname', proj);

      if (lab.querySelector('.projAddTagBtn')) { lab.__hasAddTagBtn = true; continue; }

      var btn = document.createElement('span');
      btn.className = 'projAddTagBtn';
      btn.textContent = '+';
      btn.title = 'Add a tag to this project';
      if (proj) btn.dataset.project = proj;
      lab.appendChild(btn);
      lab.__hasAddTagBtn = true;
    }
  }

  document.addEventListener('click', function(ev){
    var t = ev.target;
    if (!t || !t.classList || !t.classList.contains('projAddTagBtn')) return;
    ev.preventDefault(); ev.stopPropagation();

    var label = t.closest('.projAreaLabel');
    if (!label) return;
    var proj = t.dataset.project || getProjFromLabel(label);
    if (!proj) return;

    var input = prompt('New tag name(s) for project "'+proj+'" (separate multiple tags with spaces):');
    if (!input) return;
    input = String(input).trim();
    if (!input) return;

    // Split by spaces and filter out empty strings
    var tagNames = input.split(/\s+/).filter(function(n){ return n.length > 0; });
    if (tagNames.length === 0) return;

    // Process each tag
    var addedTags = [];
    var skippedTags = [];

    for (var j = 0; j < tagNames.length; j++) {
      var name = tagNames[j];
      
      if (name === '(no tag)'){
        skippedTags.push(name + ' (reserved)');
        continue;
      }

      // Check if tag already exists
      var exists = false;
      try{
        if (typeof uniqueTagsForProject === 'function'){
          var tgs = uniqueTagsForProject(proj) || [];
          exists = tgs.indexOf(name) !== -1;
        }
      }catch(_){}
      
      if (exists){
        skippedTags.push(name + ' (already exists)');
        continue;
      }

      // Add the tag
      try{
        if (typeof ensureTagArea === 'function'){
          ensureTagArea(proj, name);
        } else {
          var area = label.closest('[data-proj]') || label.closest('[data-project]') || label.parentElement;
          var tagEl = document.createElement('div');
          tagEl.className = 'tagArea';
          tagEl.setAttribute('data-proj', proj);
          tagEl.setAttribute('data-tag', name);
          var l = document.createElement('div'); l.className='tagAreaLabel'; l.textContent = name;
          tagEl.appendChild(l);
          (area||document.body).appendChild(tagEl);
        }
        addedTags.push(name);
      }catch(_){}
    }

    // Recompute and redraw once after all tags are added
    try{ if (typeof recomputeAreasAndTags === 'function') recomputeAreasAndTags(); }catch(_){}
    for (var k = 0; k < addedTags.length; k++) {
      try{ if (typeof relayoutTag === 'function') relayoutTag(proj, addedTags[k]); }catch(_){}
    }
    try{ if (typeof resolveTagOverlaps === 'function') resolveTagOverlaps(proj); }catch(_){}
    try{ if (typeof drawLinks === 'function') drawLinks(); }catch(_){}
    try{ if (typeof updateConsole === 'function') updateConsole(); }catch(_){}

    // Show appropriate toast message
    if (addedTags.length > 0){
      var msg = 'Added tag' + (addedTags.length > 1 ? 's' : '') + ' "' + addedTags.join('", "') + '" to ' + proj + '.';
      if (skippedTags.length > 0) msg += ' Skipped: ' + skippedTags.join(', ');
      try{ if (window.showToast) showToast(msg); }catch(_){}
      
      // Center on the first added tag
      try{
        var el2 = document.querySelector('[data-proj="'+CSSescape(proj)+'"][data-tag="'+CSSescape(addedTags[0])+'"]')
              || document.querySelector('[data-project="'+CSSescape(proj)+'"][data-tag="'+CSSescape(addedTags[0])+'"]');
        centerIntoView(el2);
      }catch(_){}
    } else if (skippedTags.length > 0){
      try{ if (window.showToast) showToast('No tags added. Skipped: ' + skippedTags.join(', ')); }catch(_){}
    }

    var exists = false;
    try{
      if (typeof uniqueTagsForProject === 'function'){
        var tgs = uniqueTagsForProject(proj) || [];
        exists = tgs.indexOf(name) !== -1;
      }
    }catch(_){}
    if (exists){
      try{
        var el = document.querySelector('[data-proj="'+CSSescape(proj)+'"][data-tag="'+CSSescape(name)+'"]')
              || document.querySelector('[data-project="'+CSSescape(proj)+'"][data-tag="'+CSSescape(name)+'"]');
        centerIntoView(el);
        if (window.showToast) showToast('Tag already exists.');
      }catch(_){}
      return;
    }

    try{
      if (typeof ensureTagArea === 'function'){
        ensureTagArea(proj, name);
      } else {
        var area = label.closest('[data-proj]') || label.closest('[data-project]') || label.parentElement;
        var tagEl = document.createElement('div');
        tagEl.className = 'tagArea';
        tagEl.setAttribute('data-proj', proj);
        tagEl.setAttribute('data-tag', name);
        var l = document.createElement('div'); l.className='tagAreaLabel'; l.textContent = name;
        tagEl.appendChild(l);
        (area||document.body).appendChild(tagEl);
      }
    }catch(_){}

    try{ if (typeof recomputeAreasAndTags === 'function') recomputeAreasAndTags(); }catch(_){}
    try{ if (typeof relayoutTag === 'function') relayoutTag(proj, name); }catch(_){}
    try{ if (typeof resolveTagOverlaps === 'function') resolveTagOverlaps(proj); }catch(_){}
    try{ if (typeof drawLinks === 'function') drawLinks(); }catch(_){}
    try{ if (typeof updateConsole === 'function') updateConsole(); }catch(_){}

    try{
      var el2 = document.querySelector('[data-proj="'+CSSescape(proj)+'"][data-tag="'+CSSescape(name)+'"]')
             || document.querySelector('[data-project="'+CSSescape(proj)+'"][data-tag="'+CSSescape(name)+'"]');
      centerIntoView(el2);
    }catch(_){}

    try{ if (window.showToast) showToast('Tag "'+name+'" added to '+proj+'.'); }catch(_){}
  }, true);

  function boot(){
    ensureButtons();
    var mo = new MutationObserver(function(){ ensureButtons(); });
    mo.observe(document.body, {childList:true, subtree:true});
  }
  window.addEventListener('load', function(){ setTimeout(boot, 120); });
})();</script>


<script id="FEATURE_QUICKFIX_ADD_RENDER_V1">(function(){
  if (window.__FEATURE_QUICKFIX_ADD_RENDER_V1__) return; window.__FEATURE_QUICKFIX_ADD_RENDER_V1__=true;

  function qs(s,root){ return (root||document).querySelector(s); }

  function centerIntoView(el){
    var cv = qs('#builderWrap .canvas'); if (!cv || !el) return;
    var cvr = cv.getBoundingClientRect();
    var er  = el.getBoundingClientRect();
    var dx = (er.left + er.width/2) - (cvr.left + cvr.width/2);
    var dy = (er.top  + er.height/2) - (cvr.top  + cvr.height/2);
    var L = Math.max(0, Math.min(cv.scrollWidth  - cv.clientWidth,  cv.scrollLeft + dx));
    var T = Math.max(0, Math.min(cv.scrollHeight - cv.clientHeight, cv.scrollTop  + dy));
    cv.scrollTo({left:L, top:T, behavior:'smooth'});
    try{ el.classList.add('pulse'); setTimeout(function(){ el.classList.remove('pulse'); }, 820);}catch(_){}
  }

  function parseAdd(cmd){
    var m = /^task\s+add\s+(.+)$/i.exec(cmd||''); if (!m) return null;
    var rest = m[1];
    var toks = rest.split(/\s+/);
    var descParts = [];
    var project = '(no project)';
    var tags = [];
    var fields = {};
    for (var i=0;i<toks.length;i++){
      var tk = toks[i];
      if (/^[+-][^\s]+$/.test(tk)){
        if (tk[0]==='+'){
          var tag = tk.slice(1);
          if (tag && tag !== '(no' && tag !== '(no tag)'){
            if (tag === 'tag)' || tag === 'tag') { /* skip */ }
            else tags.push(tag);
          }
        }
        continue;
      }
      var kv = /^([a-z0-9_.-]+):(.*)$/i.exec(tk);
      if (kv){
        var k = kv[1].toLowerCase();
        var v = kv[2];
        if (k === 'project') project = v || '(no project)';
        else fields[k] = v;
        continue;
      }
      descParts.push(tk);
    }
    var desc = descParts.join(' ').trim();
    return {desc:desc, project:project, tags:tags, fields:fields};
  }

  function ensureProj(name){
    try{ if (typeof ensureProjectArea === 'function') ensureProjectArea(name || '(no project)'); }catch(_){}
  }
  function ensureTag(proj, tag){
    if (!tag || tag === '(no tag)') return;
    try{ if (typeof ensureTagArea === 'function') ensureTagArea(proj||'(no project)', tag); }catch(_){}
  }

  if (typeof window.__NEW_TASK_COUNTER__ !== 'number') window.__NEW_TASK_COUNTER__ = 0;
  function strongId(){
    window.__NEW_TASK_COUNTER__++;
    var base = Date.now().toString(36) + '-' + (performance.now().toString(36));
    return 'new-' + base + '-' + window.__NEW_TASK_COUNTER__;
  }
  function uniqueShort(){
    var s = (Math.random().toString(36).slice(2,7) + Date.now().toString(36).slice(-5));
    return s.slice(0,10);
  }

  function setNodeDescription(node, desc, marker){
    try{
      var el = node.querySelector('.title, .descText, .taskDesc, .desc, [data-role="desc"]') || node;
      var t = el.textContent||'';
      if (marker && t.indexOf(marker) !== -1){
        el.textContent = t.replace(marker, '').trim();
      } else if (marker){
        var els = node.querySelectorAll('*');
        for (var i=0;i<els.length;i++){
          var tt = els[i].textContent||'';
          if (tt.indexOf(marker)!==-1){ els[i].textContent = tt.replace(marker,'').trim(); break; }
        }
      } else {
        el.textContent = desc;
      }
    }catch(_){}
  }

  function optimisticAdd(cmd){
    var info = parseAdd(cmd);
    if (!info) return false;

    var proj = info.project || '(no project)';
    ensureProj(proj);
    if (info.tags && info.tags.length){
      for (var i=0;i<info.tags.length;i++) ensureTag(proj, info.tags[i]);
    }

    var uuid = strongId();
    var short = uniqueShort();
    var marker = '  ['+uuid.slice(-6)+']';
    var injectedDesc = (info.desc || '(no description)') + marker;

    var t = {
      uuid: uuid,
      short: short,
      desc: injectedDesc,
      project: proj,
      tags: (info.tags||[]).slice(0),
      has_depends: false
    };
    if (info.fields && info.fields.due){ t.due = info.fields.due; }

    try{
      var node = (typeof addNodeForTask === 'function') ? addNodeForTask(t, null, null, {deferLayout:true}) : null;

      try{
        if (node){
          if (!node.getAttribute('data-uuid')) node.setAttribute('data-uuid', uuid);
          if (!node.getAttribute('data-short')) node.setAttribute('data-short', short);
          setNodeDescription(node, info.desc||'(no description)', marker);
        }
      }catch(_){}

      try{
        if (info.tags && info.tags.length && typeof relayoutTag === 'function'){
          for (var i=0;i<info.tags.length;i++) relayoutTag(proj, info.tags[i]);
        }
        if (typeof resolveTagOverlaps === 'function') resolveTagOverlaps(proj);
      }catch(_){}
      try{ if (typeof resolveProjectOverlaps === 'function') resolveProjectOverlaps(); }catch(_){}
      try{ if (typeof drawLinks === 'function') drawLinks(); }catch(_){}
      try{ if (typeof updateConsole === 'function') updateConsole(); }catch(_){}

      if (node) centerIntoView(node);
      return true;
    }catch(e){
      return false;
    }
  }

  (function(){
    var orig = window.stageAdd;
    if (typeof orig !== 'function') return;
    if (orig.__quickfixAddWrapped) return;
    function wrapped(cmd, human){
      var rv;
      try{ rv = orig.apply(this, arguments); }catch(_){}
      try{
        var lines = Array.isArray(cmd) ? cmd : String(cmd||'').replace(/\r\n/g,'\n').split('\n');
        for (var i=0;i<lines.length;i++){
          var line = lines[i].trim();
          if (/^task\s+add\b/i.test(line)){
            optimisticAdd(line);
          }
        }
      }catch(_){}
      return rv;
    }
    wrapped.__quickfixAddWrapped = true;
    window.stageAdd = wrapped;
  })();

})();</script>


<script>
// === Minimal dep handle (no overrides of app internals) =====================
(function(){
  // Util
  var $  = (s,r)=> (r||document).querySelector(s);
  function stage(){ return $('#builderStage'); }
  function linksSvg(){ return $('#builderLinks'); }
  function z(){ return (typeof window.ZSCALE==='number' && window.ZSCALE) ? window.ZSCALE : 1; }

  // Rect/anchors from DOM
  function nodeRectByShort(short){
    var st = stage(); if (!st) return null;
    var el = $('#builderStage [data-short="'+String(short).replace(/"/g,'\\"')+'"]');
    if (!el) return null;
    var r  = el.getBoundingClientRect();
    var sr = st.getBoundingClientRect();
    var zz = z();
    return { x:(r.left - sr.left)/zz, y:(r.top - sr.top)/zz, w:r.width/zz, h:r.height/zz };
  }
  function aRight(short){ var r=nodeRectByShort(short); return r? {x:r.x+r.w, y:r.y+r.h/2} : null; }
  function aTop(short){   var r=nodeRectByShort(short);  return r? {x:r.x+r.w/2, y:r.y}     : null; }
  function cubic(a,b){
    var g=40, cx1=a.x+g, cy1=a.y, cx2=b.x, cy2=Math.max(b.y-g,0);
    return "M "+a.x+" "+a.y+" C "+cx1+" "+cy1+", "+cx2+" "+cy2+", "+b.x+" "+b.y;
  }

  // Attach handle to a node (called from addNodeForTask)
  window.attachDepHandleToNode = function(nodeEl){
    if (!nodeEl || nodeEl.querySelector('.depHandle')) return;
    var s = nodeEl.getAttribute('data-short'); if (!s) return;
    var h = document.createElement('div');
    h.className = 'depHandle';
    h.dataset.short = s;
    h.textContent = '—';
    h.addEventListener('mousedown', onHandleDown);
    nodeEl.appendChild(h);
  };

  // Drag state
  var depDrag = null; // { fromShort, tempPath }

  function onHandleDown(e){
    e.stopPropagation(); e.preventDefault();
    if (e.button!==0) return;
    var s = e.currentTarget.dataset.short;
    depDrag = { fromShort:s, temp:null };
    e.currentTarget.classList.add('dragging');
    document.addEventListener('mousemove', onHandleMove);
    document.addEventListener('mouseup', onHandleUp, { once:true });
  }
  function onHandleMove(e){
    if (!depDrag) return;
    var st = stage(); if (!st) return;
    var R = st.getBoundingClientRect(), zz = z();
    var a = aRight(depDrag.fromShort); if (!a) return;
    var mx = (e.clientX - R.left)/zz, my = (e.clientY - R.top)/zz;

    var svg = linksSvg(); if (!svg) return;
    if (!depDrag.temp){
      depDrag.temp = document.createElementNS('http://www.w3.org/2000/svg','path');
      depDrag.temp.setAttribute('stroke', '#9ecbff');
      depDrag.temp.setAttribute('stroke-width', '2');
      depDrag.temp.setAttribute('fill', 'none');
      depDrag.temp.setAttribute('stroke-dasharray', '6 6');
      svg.appendChild(depDrag.temp);
    }
    depDrag.temp.setAttribute('d', cubic(a, {x:mx, y:my}));
  }

  function onHandleUp(e){
    var h = document.querySelector('.depHandle.dragging'); if (h) h.classList.remove('dragging');
    document.removeEventListener('mousemove', onHandleMove);
    if (depDrag && depDrag.temp) depDrag.temp.remove();

    var under = document.elementFromPoint(e.clientX, e.clientY);
    var target = under && under.closest && under.closest('#builderStage [data-short]');
    var toShort = target ? target.getAttribute('data-short') : null;
    var fromShort = depDrag && depDrag.fromShort;
    depDrag = null;

    if (!fromShort || !toShort || fromShort===toShort) return;

    // Cycle guard
    if (typeof depCreatesCycle==='function' && depCreatesCycle(fromShort,toShort)){
      try{ if (typeof toastMsg==='function') toastMsg('Blocked — cycle'); }catch(_){}
      return;
    }

    // Stage it
    try{
      if(!('stagedAdd' in window)) window.stagedAdd=[];
      if(!window.stagedAdd.some(function(e){return e.from===fromShort && e.to===toShort;})){
        window.stagedAdd.push({from:fromShort, to:toShort});
      }
    }catch(_){}

    // Redraw/console
    try{ if (typeof drawLinks==='function') drawLinks(); }catch(_){}
    try{ if (typeof updateConsole==='function') updateConsole(); }catch(_){}

    // Log helpful command
    try{
      var fe=document.querySelector('#builderStage [data-short="'+fromShort+'"]');
      var te=document.querySelector('#builderStage [data-short="'+toShort+'"]');
      var fu=(fe && fe.getAttribute('data-uuid')) || fromShort;
      var tu=(te && te.getAttribute('data-uuid')) || toShort;
      console.log('[dep]', 'task '+fu+' modify depends:'+tu);
      if (typeof toastMsg==='function') toastMsg('Staged: '+fromShort+' depends on '+toShort);
    }catch(_){}
  }

  // ===== Overlay + topo letters + dynamic updates ===========================
  if (!('stagedAdd' in window)) window.stagedAdd = [];

  function renderStagedOverlay(){
    var svg = linksSvg(); if(!svg) return;
    var g = svg.querySelector('#depStagedOverlay');
    if(!g){
      g = document.createElementNS('http://www.w3.org/2000/svg','g');
      g.setAttribute('id','depStagedOverlay');
      svg.appendChild(g);
    }
    while(g.firstChild) g.removeChild(g.firstChild);
    (window.stagedAdd||[]).forEach(function(e){
      var a=aRight(e.from), b=aTop(e.to);
      if(!a||!b) return;
      var p=document.createElementNS('http://www.w3.org/2000/svg','path');
      p.setAttribute('d', cubic(a,b));
      p.setAttribute('stroke','#9ecbff');
      p.setAttribute('stroke-width','2');
      p.setAttribute('fill','none');
      p.setAttribute('stroke-dasharray','6 6');
      g.appendChild(p);
    });
  }

  function computeTopoLevels(){
    var edges = (window.stagedAdd||[]).slice();
    if (!edges.length) return {};
    var nodes = new Set(); edges.forEach(e=>{nodes.add(e.from); nodes.add(e.to);});
    var indeg = {}; nodes.forEach(n=>indeg[n]=0);
    edges.forEach(e=>{ indeg[e.to] = (indeg[e.to]||0)+1; });
    var level = {}; nodes.forEach(n=>{ level[n]=0; });
    var adj = {}; nodes.forEach(n=>adj[n]=[]);
    edges.forEach(e=>adj[e.from].push(e.to));
    var q = []; nodes.forEach(n=>{ if(!indeg[n]) q.push(n); });
    while(q.length){
      var u=q.shift(), lu=level[u];
      adj[u].forEach(function(v){
        if (level[v] < lu+1) level[v]=lu+1;
        indeg[v]-=1; if(!indeg[v]) q.push(v);
      });
    }
    return level;
  }
  function letterFor(level){
    var n=Math.max(0, level|0), s='';
    do{ s=String.fromCharCode(65+(n%26))+s; n=Math.floor(n/26)-1; }while(n>=0);
    return s;
  }
  function refreshDepHandleLetters(){
    var lvl = computeTopoLevels();
    document.querySelectorAll('#builderStage [data-short] .depHandle').forEach(function(h){
      var s=h.dataset.short;
      h.textContent = (s in lvl) ? letterFor(lvl[s]) : '—';
    });
  }

  // drawLinks hook (call original, then overlay+letters)
  if (!window.__depDrawHooked){
    var _orig = window.drawLinks;
    window.drawLinks = function(){
      try{ if (typeof _orig==='function') _orig.apply(this, arguments); }catch(_){}
      try{ renderStagedOverlay(); }catch(_){}
      try{ refreshDepHandleLetters(); }catch(_){}
    };
    window.__depDrawHooked = true;
  }

  // Reflow dashed overlay while cards move (lightweight)
  (function startMoveObserver(){
    var st = stage(); if (!st || st.__depMoveObs) return;
    var rafPending=false;
    function rerender(){ if(rafPending) return; rafPending=true; requestAnimationFrame(function(){rafPending=false; try{ renderStagedOverlay(); refreshDepHandleLetters(); }catch(_){} }); }
    var obs = new MutationObserver(function(muts){
      for (var i=0;i<muts.length;i++){
        var m=muts[i];
        if (m.type==='attributes' && (m.attributeName==='style' || m.attributeName==='transform')){ rerender(); break; }
      }
    });
    try{ obs.observe(st, { attributes:true, subtree:true, attributeFilter:['style','transform'] }); st.__depMoveObs=obs; }catch(_){}
    window.addEventListener('resize', rerender, {passive:true});
  })();

  // ===== Simple cycle guard (staged + existing edges if page provides them) ==
  window.depCreatesCycle = function(fromShort, toShort){
    try{
      var edges = [];
      if (Array.isArray(window.EXIST_EDGES)) edges = edges.concat(window.EXIST_EDGES);
      if (Array.isArray(window.stagedAdd))   edges = edges.concat(window.stagedAdd);
      var adj = Object.create(null);
      edges.forEach(function(e){ if(e&&e.from&&e.to){ (adj[e.from]||(adj[e.from]=[])).push(e.to); }});
      (adj[fromShort]||(adj[fromShort]=[])).push(toShort);
      var target = fromShort, stack=[toShort], seen=Object.create(null);
      while(stack.length){
        var u=stack.pop(); if(u===target) return true;
        if(seen[u]) continue; seen[u]=true;
        (adj[u]||[]).forEach(function(v){ stack.push(v); });
      }
      return false;
    }catch(_){ return false; }
  };

})();
</script>

<!-- == Top-right Deps Commands overlay (mirrors buildCommands) =============== -->
<style>
#depCmdOverlay{position:fixed; right:14px; top:14px; width:420px; max-height:40vh;
  background:#0b1220; color:#e6eef9; border:1px solid #243247; border-radius:10px;
  box-shadow:0 8px 30px rgba(0,0,0,.35); font:12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  display:flex; flex-direction:column; z-index:9999; overflow:hidden;}
#depCmdOverlay.hidden{ display:none; }
#depCmdOverlay .hdr{display:flex; align-items:center; gap:8px; padding:8px 10px; background:#0e1626; border-bottom:1px solid #243247;}
#depCmdOverlay .hdr .dot{width:8px; height:8px; border-radius:50%; background:#60a5fa;}
#depCmdOverlay .hdr .ttl{font-weight:700; letter-spacing:.3px; font-size:12px;}
#depCmdOverlay .hdr .sp{flex:1}
#depCmdOverlay .hdr .btn{cursor:pointer; padding:4px 8px; border:1px solid #2a3a54; border-radius:6px; color:#9cc2ff; user-select:none;}
#depCmdOverlay pre{margin:0; padding:10px; overflow:auto; white-space:pre; tab-size:2;}
</style>
<div id="depCmdOverlay" class="hidden" aria-label="Staged Commands">
  <div class="hdr">
    <div class="dot"></div>
    <div class="ttl">Staged Commands</div>
    <div class="sp"></div>
    <div class="btn" id="depCmdCopyBtn">Copy</div>
    <div class="btn" id="depCmdHideBtn">Hide</div>
  </div>
  <pre id="depCmdPre"></pre>
</div>
<script>
(function(){
  var overlay = document.getElementById('depCmdOverlay');
  var pre = document.getElementById('depCmdPre');
  var hideBtn = document.getElementById('depCmdHideBtn');
  var copyBtn = document.getElementById('depCmdCopyBtn');
  if (hideBtn) hideBtn.addEventListener('click', function(){ overlay.classList.add('hidden'); });
  if (copyBtn) copyBtn.addEventListener('click', function(){
    try{ navigator.clipboard.writeText(pre.textContent||""); }catch(_){}
  });
  // Toggle with 'd'
  document.addEventListener('keydown', function(e){
    if (e.key.toLowerCase()==='d' && !e.metaKey && !e.ctrlKey && !e.altKey){
      overlay.classList.toggle('hidden');
      if (!overlay.classList.contains('hidden')) render();
    }
  });
  function uuidFromShort(short){
    try{
      if (window.TASK_BY_SHORT && window.TASK_BY_SHORT[short]) return window.TASK_BY_SHORT[short].uuid || short;
      var el=document.querySelector('#builderStage [data-short="'+short+'"]');
      return (el && el.getAttribute('data-uuid')) || short;
    }catch(_){ return short; }
  }
  function build(){
    try{
      if (typeof buildCommands==='function'){
        return String(buildCommands()||'');
      }
    }catch(_){}
    // fallback from stagedAdd
    var out=[]; (window.stagedAdd||[]).forEach(function(e){
      out.push('task '+uuidFromShort(e.from)+' modify depends:'+uuidFromShort(e.to));
    });
    return out.join('\n');
  }
  function render(){ pre.textContent = build(); }
  window.__depsOverlayRender = render;
  // hook updateConsole lightly
  if (!window.__depsOverlayHooked){
    var _upd = window.updateConsole;
    window.updateConsole = function(){
      try{ if (typeof _upd==='function') _upd.apply(this, arguments); }catch(_){}
      try{ render(); }catch(_){}
    };
    window.__depsOverlayHooked = true;
  }
  setTimeout(function(){ render(); if ((pre.textContent||'').trim()){ overlay.classList.remove('hidden'); } }, 200);
})();
</script>

<!-- == buildCommands monkey patch to include staged depends ================== -->
<script>
(function(){
  if (window.__buildCommandsPatched) return;
  if (typeof window.buildCommands !== 'function'){ window.__buildCommandsPatched=true; return; }
  var _orig = window.buildCommands;
  function uuidFromShort(short){
    try{
      if (window.TASK_BY_SHORT && window.TASK_BY_SHORT[short]) return window.TASK_BY_SHORT[short].uuid || short;
      var el=document.querySelector('#builderStage [data-short="'+short+'"]');
      return (el && el.getAttribute('data-uuid')) || short;
    }catch(_){ return short; }
  }
  window.buildCommands = function(){
    var txt = "";
    try{ txt = _orig.call(this) || ""; }catch(_){}
    try{
      var extras=[];
      (window.stagedAdd||[]).forEach(function(e){
        extras.push("task "+uuidFromShort(e.from)+" modify depends:"+uuidFromShort(e.to));
      });
      if (extras.length) txt = (txt ? txt+"\n" : "") + extras.join("\n");
    }catch(_){}
    return txt;
  };
  window.__buildCommandsPatched = true;
})();
</script>


<script>
// === Dependency system (v0.7.7 strict) ======================================
(function(){
  // Utils
  var $  = (s,r)=> (r||document).querySelector(s);
  function stage(){ return $('#builderStage'); }
  function linksSvg(){ return $('#builderLinks'); }
  function z(){ return (typeof window.ZSCALE==='number' && window.ZSCALE) ? window.ZSCALE : 1; }
  function nodeElByShort(short){ return $('#builderStage [data-short="'+String(short).replace(/"/g,'\\"')+'"]'); }

  // Rect + anchors
  function rectByShort(short){
    var st=stage(), el=nodeElByShort(short);
    if (!st || !el) return null;
    var R=el.getBoundingClientRect(), SR=st.getBoundingClientRect(), zz=z();
    return {x:(R.left-SR.left)/zz, y:(R.top-SR.top)/zz, w:R.width/zz, h:R.height/zz};
  }
  function aRight(short){ var r=rectByShort(short); return r?{x:r.x+r.w, y:r.y+r.h/2}:null; }
  function aTop(short){   var r=rectByShort(short);  return r?{x:r.x+r.w/2, y:r.y}:null; }
  function cubic(a,b){ var g=40; return "M "+a.x+" "+a.y+" C "+(a.x+g)+" "+a.y+", "+b.x+" "+Math.max(b.y-g,0)+", "+b.x+" "+b.y; }

  // Attach handle to node
  window.attachDepHandleToNode = window.attachDepHandleToNode || function(nodeEl){
    if (!nodeEl || nodeEl.querySelector('.depHandle')) return;
    var s = nodeEl.getAttribute('data-short'); if (!s) return;
    var h = document.createElement('div');
    h.className = 'depHandle';
    h.dataset.short = s;
    h.textContent = '—';
    h.addEventListener('mousedown', onHandleDown);
    nodeEl.appendChild(h);
  };

  // Drag state
  var depDrag = null;
  function onHandleDown(e){
    e.stopPropagation(); e.preventDefault();
    if (e.button!==0) return;
    var s = e.currentTarget.dataset.short;
    depDrag = { fromShort:s, temp:null };
    e.currentTarget.classList.add('dragging');
    document.addEventListener('mousemove', onHandleMove);
    document.addEventListener('mouseup', onHandleUp, { once:true });
  }
  function onHandleMove(e){
    if (!depDrag) return;
    var st=stage(); if (!st) return;
    var R=st.getBoundingClientRect(), zz=z();
    var a=aRight(depDrag.fromShort); if (!a) return;
    var mx=(e.clientX-R.left)/zz, my=(e.clientY-R.top)/zz;
    var svg=linksSvg(); if (!svg) return;
    if (!depDrag.temp){
      depDrag.temp=document.createElementNS('http://www.w3.org/2000/svg','path');
      depDrag.temp.setAttribute('stroke','#9ecbff');
      depDrag.temp.setAttribute('stroke-width','2');
      depDrag.temp.setAttribute('fill','none');
      depDrag.temp.setAttribute('stroke-dasharray','6 6');
      depDrag.temp.style.pointerEvents='none';
      svg.appendChild(depDrag.temp);
    }
    depDrag.temp.setAttribute('d', cubic(a,{x:mx,y:my}));
  }

  // Cycle guard
  window.depCreatesCycle = window.depCreatesCycle || function(fromShort,toShort){
    try{
      var edges=[];
      if (Array.isArray(window.EXIST_EDGES)) edges=edges.concat(window.EXIST_EDGES);
      if (Array.isArray(window.stagedAdd))   edges=edges.concat(window.stagedAdd);
      var adj=Object.create(null);
      edges.forEach(function(e){ if(e&&e.from&&e.to){ (adj[e.from]||(adj[e.from]=[])).push(e.to); }});
      (adj[fromShort]||(adj[fromShort]=[])).push(toShort);
      var target=fromShort, stack=[toShort], seen=Object.create(null);
      while(stack.length){
        var u=stack.pop(); if(u===target) return true;
        if(seen[u]) continue; seen[u]=true;
        (adj[u]||[]).forEach(function(v){ stack.push(v); });
      }
      return false;
    }catch(_){ return false; }
  };

  function onHandleUp(e){
    var h=document.querySelector('.depHandle.dragging'); if (h) h.classList.remove('dragging');
    document.removeEventListener('mousemove', onHandleMove);
    if (depDrag && depDrag.temp) depDrag.temp.remove();

    var under=document.elementFromPoint(e.clientX,e.clientY);
    var tgt=under && under.closest && under.closest('#builderStage [data-short]');
    var toShort=tgt ? tgt.getAttribute('data-short') : null;
    var fromShort=depDrag && depDrag.fromShort;
    depDrag=null;
    if (!fromShort || !toShort || fromShort===toShort) return;

    if (typeof depCreatesCycle==='function' && depCreatesCycle(fromShort,toShort)){
      try{ if(typeof toastMsg==='function') toastMsg('Blocked — cycle'); }catch(_){}
      return;
    }

    try{
      if(!('stagedAdd' in window)) window.stagedAdd=[];
      if(!window.stagedAdd.some(function(e){return e.from===fromShort && e.to===toShort;})){
        window.stagedAdd.push({from:fromShort,to:toShort});
      }
    }catch(_){}
    try{ if (typeof drawLinks==='function') drawLinks(); }catch(_){}
    try{ if (typeof updateConsole==='function') updateConsole(); }catch(_){}
    try{
      var fe=nodeElByShort(fromShort), te=nodeElByShort(toShort);
      var fu=(fe && fe.getAttribute('data-uuid'))||fromShort;
      var tu=(te && te.getAttribute('data-uuid'))||toShort;
      console.log('[dep]','task '+fu+' modify depends:'+tu);
      if (typeof toastMsg==='function') toastMsg('Staged: '+fromShort+' depends on '+toShort);
    }catch(_){}
  }

  // Overlay + letters + dynamic updates
  if (!('stagedAdd' in window)) window.stagedAdd = [];

  function renderStagedOverlay(){
    var svg=linksSvg(); if(!svg) return;
    var g=svg.querySelector('#depStagedOverlay');
    if(!g){
      g=document.createElementNS('http://www.w3.org/2000/svg','g');
      g.setAttribute('id','depStagedOverlay');
      svg.appendChild(g);
    }
    while(g.firstChild) g.removeChild(g.firstChild);
    (window.stagedAdd||[]).forEach(function(e){
      var a=aRight(e.from), b=aTop(e.to);
      if(!a||!b) return;
      var p=document.createElementNS('http://www.w3.org/2000/svg','path');
      p.setAttribute('d', cubic(a,b));
      p.setAttribute('stroke','#9ecbff');
      p.setAttribute('stroke-width','2');
      p.setAttribute('fill','none');
      p.setAttribute('stroke-dasharray','6 6');
      g.appendChild(p);
    });
  }

  function computeTopoLevels(){
    var edges=(window.stagedAdd||[]).slice();
    if(!edges.length) return {};
    var nodes=new Set(); edges.forEach(e=>{nodes.add(e.from);nodes.add(e.to);});
    var indeg={}, level={}, adj={};
    nodes.forEach(n=>{indeg[n]=0; level[n]=0; adj[n]=[];});
    edges.forEach(function(e){ indeg[e.to]=(indeg[e.to]||0)+1; adj[e.from].push(e.to); });
    var q=[]; nodes.forEach(n=>{ if(!indeg[n]) q.push(n); });
    while(q.length){
      var u=q.shift(), lu=level[u];
      adj[u].forEach(function(v){
        if(level[v]<lu+1) level[v]=lu+1;
        indeg[v]-=1; if(!indeg[v]) q.push(v);
      });
    }
    return level;
  }
  function letterFor(level){
    var n=Math.max(0, level|0), s='';
    do{ s=String.fromCharCode(65+(n%26))+s; n=Math.floor(n/26)-1; }while(n>=0);
    return s;
  }
  window.refreshDepHandleLetters = (function(prev){
    return function(){
      var lvl=computeTopoLevels();
      document.querySelectorAll('#builderStage [data-short] .depHandle').forEach(function(h){
        var s=h.dataset.short;
        h.textContent = (s in lvl) ? letterFor(lvl[s]) : '—';
      });
      if (typeof prev==='function') try{ prev(); }catch(_){}
    };
  })(window.refreshDepHandleLetters);

  // Strict both-ends visibility manager
  window.__applyDepHandleVisibilityStrict = function(){
    var fromSet=Object.create(null), toSet=Object.create(null);
    try{ (window.stagedAdd||[]).forEach(function(e){ if(e){ if(e.from)fromSet[e.from]=true; if(e.to)toSet[e.to]=true; } }); }catch(_){}
    var nodes=document.querySelectorAll('#builderStage [data-short] > .depHandle');
    nodes.forEach(function(h){ h.classList.remove('dep-hasdeps'); });
    nodes.forEach(function(h){
      var s=h.dataset.short;
      if (fromSet[s] || toSet[s]) h.classList.add('dep-hasdeps');
    });
  };

  // Hook drawLinks — restore overlay, letters, and visibility after app draw
  if (!window.__depDrawHooked){
    var _orig=window.drawLinks;
    window.drawLinks=function(){
      try{ if(typeof _orig==='function') _orig.apply(this, arguments); }catch(_){}
      try{ renderStagedOverlay(); }catch(_){}
      try{ refreshDepHandleLetters(); }catch(_){}
      try{ __applyDepHandleVisibilityStrict(); }catch(_){}
    };
    window.__depDrawHooked=true;
  }

  // Re-render while nodes move (watch style/transform changes)
  (function(){
    var st=stage(); if(!st || st.__depMoveObs) return;
    var raf=false;
    function rer(){ if(raf) return; raf=true; requestAnimationFrame(function(){raf=false;
      try{ renderStagedOverlay(); refreshDepHandleLetters(); __applyDepHandleVisibilityStrict(); }catch(_){}
    }); }
    var obs=new MutationObserver(function(muts){
      for (var i=0;i<muts.length;i++){
        var m=muts[i];
        if (m.type==='attributes' && (m.attributeName==='style'||m.attributeName==='transform')){ rer(); break; }
      }
    });
    try{ obs.observe(st,{attributes:true, subtree:true, attributeFilter:['style','transform']}); st.__depMoveObs=obs; }catch(_){}
    window.addEventListener('resize', rer, {passive:true});
  })();

  // Deps Commands overlay + buildCommands patch
  (function overlayAndCommands(){
    if (!document.getElementById('depCmdOverlay')){
      var css = document.createElement('style');
      css.textContent = "#depCmdOverlay{position:fixed; right:14px; top:14px; width:420px; max-height:40vh; background:#0b1220; color:#e6eef9; border:1px solid #243247; border-radius:10px; box-shadow:0 8px 30px rgba(0,0,0,.35); font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; display:flex; flex-direction:column; z-index:9999; overflow:hidden;} #depCmdOverlay.hidden{display:none;} #depCmdOverlay .hdr{display:flex; align-items:center; gap:8px; padding:8px 10px; background:#0e1626; border-bottom:1px solid #243247;} #depCmdOverlay .hdr .dot{width:8px; height:8px; border-radius:50%; background:#60a5fa;} #depCmdOverlay .hdr .ttl{font-weight:700; letter-spacing:.3px; font-size:12px;} #depCmdOverlay .hdr .sp{flex:1} #depCmdOverlay .hdr .btn{cursor:pointer; padding:4px 8px; border:1px solid #2a3a54; border-radius:6px; color:#9cc2ff; user-select:none;} #depCmdOverlay pre{margin:0; padding:10px; overflow:auto; white-space:pre; tab-size:2;}";
      document.head.appendChild(css);
      var wrap=document.createElement('div');
      wrap.innerHTML = '<div id="depCmdOverlay" class="hidden" aria-label="Deps Commands"><div class="hdr"><div class="dot"></div><div class="ttl">Deps Commands</div><div class="sp"></div><div class="btn" id="depCmdCopyBtn">Copy</div><div class="btn" id="depCmdHideBtn">Hide</div></div><pre id="depCmdPre"></pre></div>';
      document.body.appendChild(wrap.firstChild);
      var overlay = document.getElementById('depCmdOverlay');
      document.getElementById('depCmdHideBtn').addEventListener('click', function(){ overlay.classList.add('hidden'); });
      document.getElementById('depCmdCopyBtn').addEventListener('click', function(){
        try{ navigator.clipboard.writeText(document.getElementById('depCmdPre').textContent||""); }catch(_){}
      });
      document.addEventListener('keydown', function(e){
        if (e.key.toLowerCase()==='d' && !e.metaKey && !e.ctrlKey && !e.altKey){
          overlay.classList.toggle('hidden');
          if (!overlay.classList.contains('hidden')) renderOverlay();
        }
      });
      setTimeout(function(){ renderOverlay(); if ((document.getElementById('depCmdPre').textContent||'').trim()){ overlay.classList.remove('hidden'); } }, 200);
    }
    function uuidFromShort(short){
      try{
        if (window.TASK_BY_SHORT && window.TASK_BY_SHORT[short]) return window.TASK_BY_SHORT[short].uuid || short;
        var el=nodeElByShort(short); return (el && el.getAttribute('data-uuid')) || short;
      }catch(_){ return short; }
    }
    function renderOverlay(){
      var pre=document.getElementById('depCmdPre'); if (!pre) return;
      var txt="";
      try{ if (typeof buildCommands==='function') txt=String(buildCommands()||''); }catch(_){}
      if (!txt){
        var out=[]; (window.stagedAdd||[]).forEach(function(e){
          out.push('task '+uuidFromShort(e.from)+' modify depends:'+uuidFromShort(e.to));
        });
        txt=out.join('\\n');
      }
      pre.textContent = txt;
    }
    if (!window.__depsOverlayHooked){
      var _upd = window.updateConsole;
      window.updateConsole = function(){
        try{ if (typeof _upd==='function') _upd.apply(this, arguments); }catch(_){}
        try{ renderOverlay(); __applyDepHandleVisibilityStrict(); }catch(_){}
      };
      window.__depsOverlayHooked = true;
    }
    if (!window.__buildCommandsPatched && typeof window.buildCommands==='function'){
      var _origBuild = window.buildCommands;
      window.buildCommands = function(){
        var txt=""; try{ txt=_origBuild.call(this)||""; }catch(_){}
        try{
          var extras=[];
          (window.stagedAdd||[]).forEach(function(e){
            extras.push('task '+uuidFromShort(e.from)+' modify depends:'+uuidFromShort(e.to));
          });
          if (extras.length) txt = (txt ? txt+'\\n' : '') + extras.join('\\n');
        }catch(_){}
        return txt;
      };
      window.__buildCommandsPatched = true;
    }
  })();

  // Kick initial UI sync
  try{ renderStagedOverlay(); refreshDepHandleLetters(); __applyDepHandleVisibilityStrict(); }catch(_){}
})();
</script>


<script>
// === dep-handle visibility manager (STRICT both-ends, edges-only; generator) =
(function(){
  if (window.__depHandleVisibilityStrictGen) return;

  function computeSets(){
    var fromSet = Object.create(null), toSet = Object.create(null);
    try{
      (window.stagedAdd || []).forEach(function(e){
        if (!e) return;
        if (e.from) fromSet[e.from] = true;
        if (e.to)   toSet[e.to]     = true;
      });
    }catch(_){}
    return {fromSet, toSet};
  }

  function __applyDepHandleVisibilityStrict(){
    var sets = computeSets();
    var fromSet = sets.fromSet, toSet = sets.toSet;
    var nodes = document.querySelectorAll('#builderStage [data-short] > .depHandle');
    nodes.forEach(function(h){ h.classList.remove('dep-hasdeps'); });
    nodes.forEach(function(h){
      var s = h.dataset.short;
      if (fromSet[s] || toSet[s]) h.classList.add('dep-hasdeps');
    });
  }

  // run once
  setTimeout(__applyDepHandleVisibilityStrict, 0);

  // re-apply after console updates
  (function hookUpdateConsole(){
    var _upd = window.updateConsole;
    window.updateConsole = function(){
      try{ if (typeof _upd === 'function') _upd.apply(this, arguments); }catch(_){}
      try{ __applyDepHandleVisibilityStrict(); }catch(_){}
    };
  })();

  // re-apply after draws
  (function hookDrawLinks(){
    var _draw = window.drawLinks;
    window.drawLinks = function(){
      try{ if (typeof _draw === 'function') _draw.apply(this, arguments); }catch(_){}
      try{ __applyDepHandleVisibilityStrict(); }catch(_){}
    };
  })();

  window.__depHandleVisibilityStrictGen = true;
})();
</script>


<script>
// === dep-handle counts (Chrome-optimized) ===================================
(function(){
  if (window.__depHandleCountsChrome) return;

  function qsa(sel, root){ return (root||document).querySelectorAll(sel); }

  // Collect edges as {from:<short or uuid>, to:<short or uuid>}
  function gatherEdges(){
    var edges = [], i, s, t, deps, e;
    // From TASK_BY_SHORT.depends (often shorts)
    try{
      var T = window.TASK_BY_SHORT;
      if (T && typeof T === 'object'){
        for (s in T){
          if (!Object.prototype.hasOwnProperty.call(T,s)) continue;
          t = T[s];
          deps = t && (t.depends || t.dependencies);
          if (Array.isArray(deps)){
            for (i=0;i<deps.length;i++){ edges.push({from:String(s), to:String(deps[i])}); }
          } else if (typeof deps === 'string' && deps.trim()){
            String(deps).split(/[\s,]+/).forEach(function(d){ if(d) edges.push({from:String(s), to:String(d)}); });
          }
        }
      }
    }catch(_){}
    // From EXIST_EDGES if present
    try{
      var ex = window.EXIST_EDGES;
      if (Array.isArray(ex)){
        for (i=0;i<ex.length;i++){ e=ex[i]; if(e&&e.from&&e.to) edges.push({from:String(e.from), to:String(e.to)}); }
      }
    }catch(_){}
    // From stagedAdd
    try{
      var st = window.stagedAdd;
      if (Array.isArray(st)){
        for (i=0;i<st.length;i++){ e=st[i]; if(e&&e.from&&e.to) edges.push({from:String(e.from), to:String(e.to)}); }
      }
    }catch(_){}
    return edges;
  }

  // Map UUIDs to shorts using DOM when needed (Chrome target; simple mapper)
  function buildDomMaps(){
    var nodes = qsa('#builderStage [data-short]');
    var shortSet = Object.create(null), uuid2short = Object.create(null);
    for (var i=0;i<nodes.length;i++){
      var el = nodes[i];
      var s  = el.getAttribute('data-short');
      var u  = el.getAttribute('data-uuid');
      if (s) shortSet[s] = true;
      if (u && s) uuid2short[String(u).toLowerCase()] = s;
    }
    return {shortSet:shortSet, uuid2short:uuid2short};
  }
  function first8(x){ return String(x||'').replace(/[^0-9a-fA-F-]/g,'').slice(0,8); }
  function toShort(id, maps){
    if (!id) return null;
    id = String(id);
    if (maps.shortSet[id]) return id;
    var low = id.toLowerCase();
    if (maps.uuid2short[low]) return maps.uuid2short[low];
    var f8 = first8(id);
    return maps.shortSet[f8] ? f8 : null;
  }

  function computeCounts(){
    var maps = buildDomMaps();
    var out = Object.create(null), inc = Object.create(null);
    var edges = gatherEdges();
    for (var i=0;i<edges.length;i++){
      var e = edges[i];
      var fs = toShort(e.from, maps);
      var ts = toShort(e.to, maps);
      if (!fs || !ts) continue;
      out[fs] = (out[fs]||0) + 1;
      inc[ts] = (inc[ts]||0) + 1;
    }
    return {out:out, inc:inc};
  }

  function baseLetterOf(txt){
    var s = String(txt||'').trim();
    // strip trailing counts like 12/3 if any
    s = s.replace(/\d+(?:\/\d+)?$/,'').trim();
    return s || '—';
  }

  function applyCounts(){
    var counts = computeCounts(), out = counts.out, inc = counts.inc;
    var hs = qsa('#builderStage [data-short] .depHandle');
    if (!hs.length) return;
    for (var i=0;i<hs.length;i++){
      var h  = hs[i];
      var sh = h.getAttribute('data-short');
      var letter = baseLetterOf(h.textContent);
      var o = out[sh]|0, n = inc[sh]|0;
      var next = (o===0 && n===0) ? letter : (letter + o + '/' + n);
      if (h.textContent !== next) h.textContent = next;
    }
  }

  // Hook into your existing redraw points
  (function(){
    var _letters = window.refreshDepHandleLetters;
    window.refreshDepHandleLetters = function(){
      if (typeof _letters === 'function') try{ _letters.apply(this, arguments); }catch(_){}
      try{ applyCounts(); }catch(_){}
    };
    var _draw = window.drawLinks;
    window.drawLinks = function(){
      if (typeof _draw === 'function') try{ _draw.apply(this, arguments); }catch(_){}
      try{ applyCounts(); }catch(_){}
    };
    var _upd = window.updateConsole;
    window.updateConsole = function(){
      if (typeof _upd === 'function') try{ _upd.apply(this, arguments); }catch(_){}
      try{ applyCounts(); }catch(_){}
    };
  })();

  // First paint
  setTimeout(applyCounts, 0);

  window.__depHandleCountsChrome = true;
})();
</script>


<script>
// == dep pulses: animate energy from higher letter -> lower letter ===========
(function(){
  if (window.__depPulses) return;

  function $(s,r){ return (r||document).querySelector(s); }
  function qsa(s,r){ return (r||document).querySelectorAll(s); }

  // ----- topo levels (use staged + existing) --------------------------------
  function gatherEdgesShorts(){
    var edges=[], i, e, s, t, deps;
    try{
      var T=window.TASK_BY_SHORT||{};
      for (s in T){
        if (!Object.prototype.hasOwnProperty.call(T,s)) continue;
        deps=T[s] && (T[s].depends||T[s].dependencies);
        if (Array.isArray(deps)){ for(i=0;i<deps.length;i++){ edges.push({from:String(s), to:String(deps[i])}); } }
        else if (typeof deps==='string' && deps.trim()){
          String(deps).split(/[\s,]+/).forEach(function(d){ if(d) edges.push({from:String(s), to:String(d)}); });
        }
      }
    }catch(_){}
    try{
      var ex=window.EXIST_EDGES; if(Array.isArray(ex)){
        for(i=0;i<ex.length;i++){ e=ex[i]; if(e&&e.from&&e.to) edges.push({from:String(e.from), to:String(e.to)}); }
      }
    }catch(_){}
    try{
      var st=window.stagedAdd; if(Array.isArray(st)){
        for(i=0;i<st.length;i++){ e=st[i]; if(e&&e.from&&e.to) edges.push({from:String(e.from), to:String(e.to)}); }
      }
    }catch(_){}
    // normalize to shorts using DOM where possible
    var maps = (function(){
      var M={shortSet:Object.create(null), uuid2short:Object.create(null)};
      qsa('#builderStage [data-short]').forEach(function(el){
        var sh=el.getAttribute('data-short'), uu=el.getAttribute('data-uuid');
        if (sh) M.shortSet[sh]=true;
        if (uu && sh) M.uuid2short[String(uu).toLowerCase()] = sh;
      });
      return M;
    })();
    function first8(x){ return String(x||'').replace(/[^0-9a-fA-F-]/g,'').slice(0,8); }
    function toShort(id){
      if (!id) return null;
      id=String(id);
      if (maps.shortSet[id]) return id;
      var low=id.toLowerCase(); if (maps.uuid2short[low]) return maps.uuid2short[low];
      var f8=first8(id); return maps.shortSet[f8]? f8 : null;
    }
    var out=[];
    for(i=0;i<edges.length;i++){
      var fs=toShort(edges[i].from), ts=toShort(edges[i].to);
      if (fs && ts) out.push({from:fs,to:ts});
    }
    return out;
  }

  function computeTopoLevels(){
    var E=gatherEdgesShorts(), i, u, v;
    var nodes=Object.create(null), indeg=Object.create(null), level=Object.create(null), adj=Object.create(null);
    for(i=0;i<E.length;i++){ nodes[E[i].from]=1; nodes[E[i].to]=1; }
    Object.keys(nodes).forEach(function(n){ indeg[n]=0; level[n]=0; adj[n]=[]; });
    for(i=0;i<E.length;i++){ u=E[i].from; v=E[i].to; indeg[v]=(indeg[v]||0)+1; adj[u].push(v); }
    var q=[]; Object.keys(nodes).forEach(function(n){ if(!indeg[n]) q.push(n); });
    while(q.length){
      u=q.shift(); var lu=level[u]||0; var a=adj[u]||[];
      for(i=0;i<a.length;i++){
        v=a[i];
        if ((level[v]||0) < lu+1) level[v]=lu+1;
        indeg[v]-=1; if(!indeg[v]) q.push(v);
      }
    }
    return level; // A=0, B=1, C=2...
  }

  // ----- pulse overlay builder ----------------------------------------------
  var anim = { enabled:true, items:[], raf:null, lastTs:0 };
  function ensurePulseGroup(){
    var svg = $('#builderLinks'); if (!svg) return null;
    var g = $('#depPulseOverlay');
    if (!g){
      g = document.createElementNS('http://www.w3.org/2000/svg','g');
      g.setAttribute('id','depPulseOverlay');
      svg.appendChild(g);
    }
    return g;
  }

  function rebuildPulses(){
    var svg = $('#builderLinks'); if (!svg) return;
    var overlay = ensurePulseGroup(); if (!overlay) return;

    // wipe previous
    while(overlay.firstChild) overlay.removeChild(overlay.firstChild);
    anim.items.length = 0;

    var lvl = computeTopoLevels();

    // We rely on staged paths for metadata (data-from/to). Existing paths without data are skipped.
    var paths = qsa('#builderLinks path.dep-edge.staged[data-from][data-to], #depStagedOverlay path[data-from][data-to]');
    for (var i=0;i<paths.length;i++){
      var p = paths[i];
      var from = p.getAttribute('data-from');
      var to   = p.getAttribute('data-to');
      if (!from || !to) continue;

      var L = p.getTotalLength ? p.getTotalLength() : null;
      if (!L || !isFinite(L) || L<20) continue;

      var lf = lvl[from]||0, lt = lvl[to]||0;
      if (lf === lt) continue; // no direction

      // Ensure the visual direction is higher -> lower along 0..L
      if (lf < lt){
        // swap labels if needed; the path direction is unchanged visually
        var tmp = from; from = to; to = tmp;
      }

      // Build a couple of pulses on this path
      var count = 2;
      for (var k=0;k<count;k++){
        var dot = document.createElementNS('http://www.w3.org/2000/svg','circle');
        dot.setAttribute('class','pulse-dot');
        dot.setAttribute('r','2.2');
        overlay.appendChild(dot);
        anim.items.push({
          path:p, len:L, el:dot,
          t: (k / count),
          speed: 80 + Math.random()*60
        });
      }
    }
    if (anim.enabled && !anim.raf){ anim.lastTs=0; anim.raf=requestAnimationFrame(step); }
  }

  function step(ts){
    if (!anim.enabled){ anim.raf=null; return; }
    if (!anim.lastTs) anim.lastTs=ts;
    var dt = Math.min(0.050, (ts - anim.lastTs)/1000);
    anim.lastTs = ts;

    for (var i=0;i<anim.items.length;i++){
      var it = anim.items[i];
      var d = (it.speed * dt) / it.len;
      it.t += d;
      if (it.t >= 1) it.t -= 1;
      var s = (1 - it.t) * it.len; /* __PULSE_DIR_REVERSED__ */
      try{
        var pt = it.path.getPointAtLength(s);
        it.el.setAttribute('cx', pt.x);
        it.el.setAttribute('cy', pt.y);
      }catch(_){}
    }
    anim.raf = requestAnimationFrame(step);
  }

  // Rebuild after each drawLinks
  (function(){
    var _draw = window.drawLinks;
    window.drawLinks = function(){
      if (typeof _draw==='function') try{ _draw.apply(this, arguments); }catch(_){}
      setTimeout(rebuildPulses, 0);
    };
  })();

  // Tag last staged overlay path with data-from/to (if not already)
  (function(){
    try{
      if (!('stagedAdd' in window)) window.stagedAdd = [];
      var a = window.stagedAdd;
      if (!a.__depPulseTagged){
        var push=a.push, splice=a.splice;
        a.push=function(e){ var r=push.apply(this, arguments); setTimeout(function(){
            var over = document.querySelector('#depStagedOverlay'); if (!over) return;
            var p = over.querySelector('path:last-of-type'); if (!p) return;
            if (e && e.from) p.setAttribute('data-from', String(e.from));
            if (e && e.to)   p.setAttribute('data-to',   String(e.to));
            setTimeout(rebuildPulses, 0);
          }, 0); return r; };
        a.splice=function(){ var r=splice.apply(this, arguments); setTimeout(rebuildPulses, 0); return r; };
        a.__depPulseTagged = true;
      }
    }catch(_){}
  })();

  // Toggle with 'P'
  document.addEventListener('keydown', function(e){
    if ((e.key==='p'||e.key==='P') && !e.ctrlKey && !e.metaKey && !e.altKey){
      anim.enabled = !anim.enabled;
      var g = document.getElementById('depPulseOverlay');
      if (g) g.style.display = anim.enabled ? '' : 'none';
      if (anim.enabled && !anim.raf){ anim.lastTs=0; anim.raf=requestAnimationFrame(step); }
    }
  });

  // bootstrap
  setTimeout(rebuildPulses, 0);
  window.__depPulses = true;
})();
</script>


<script>
/* __EXISTING_SOLID_V3A__ draw solid existing edges with robust anchors */
(function(){
  if (window.__existingSolidV3A) return;

  function $(s,r){ return (r||document).querySelector(s); }

  function ensureMarker(){
    var svg = $('#builderLinks'); if (!svg) return;
    var defs = svg.querySelector('defs');
    if(!defs){
      defs=document.createElementNS('http://www.w3.org/2000/svg','defs');
      svg.insertBefore(defs, svg.firstChild);
    }
    if (!svg.querySelector('#depArrow')){
      var m = document.createElementNS('http://www.w3.org/2000/svg','marker');
      m.setAttribute('id','depArrow'); m.setAttribute('viewBox','0 0 10 10');
      m.setAttribute('refX','8'); m.setAttribute('refY','5');
      m.setAttribute('markerWidth','6'); m.setAttribute('markerHeight','6');
      m.setAttribute('orient','auto-start-reverse');
      var p = document.createElementNS('http://www.w3.org/2000/svg','path');
      p.setAttribute('d','M 0 0 L 10 5 L 0 10 z'); p.setAttribute('fill','#9ecbff');
      m.appendChild(p); defs.appendChild(m);
    }
  }

  function ensureExistingGroup(){
    var svg = $('#builderLinks'); if (!svg) return null;
    var g = $('#depExistingEdges');
    if (!g){
      g = document.createElementNS('http://www.w3.org/2000/svg','g');
      g.setAttribute('id','depExistingEdges');
      svg.insertBefore(g, svg.firstChild); // keep overlay above
    }
    return g;
  }

  function svgPointFromScreen(svg, x, y){
    var pt = svg.createSVGPoint();
    pt.x = x; pt.y = y;
    try {
      var m = svg.getScreenCTM();
      if (m && m.inverse) pt = pt.matrixTransform(m.inverse());
    } catch(_){}
    return { x: pt.x, y: pt.y };
  }

  function anchorParentLeft(short){
    var el = document.querySelector('#builderStage [data-short="'+short+'"]');
    var svg = $('#builderLinks'); if (!el || !svg) return null;
    var r = el.getBoundingClientRect();
    // center-left on parent (incoming side)
    var sx = r.left, sy = r.top + r.height/2;
    return svgPointFromScreen(svg, sx, sy);
  }

  function anchorChildTop(short){
    var el = document.querySelector('#builderStage [data-short="'+short+'"]');
    var svg = $('#builderLinks'); if (!el || !svg) return null;
    var r = el.getBoundingClientRect();
    // top-center on child (outgoing side)
    var sx = r.left + r.width/2, sy = r.top;
    return svgPointFromScreen(svg, sx, sy);
  }

  function makePath(p,c){
    // cubic with soft elbow
    var gap = Math.max(24, Math.min(80, Math.abs(c.x - p.x) * 0.4));
    var cx1 = p.x - gap, cy1 = p.y;
    var cx2 = c.x,       cy2 = c.y - gap;
    return "M "+p.x+" "+p.y+" C "+cx1+" "+cy1+", "+cx2+" "+cy2+", "+c.x+" "+c.y;
  }

  var _orig = window.drawLinks;
  window.drawLinks = function(){
    if (typeof _orig === 'function'){ try{ _orig.apply(this, arguments); }catch(_){} }

    var svg = $('#builderLinks'); if(!svg) return;
    ensureMarker();
    var g = ensureExistingGroup(); if(!g) return;

    // refresh only our group
    while (g.firstChild) g.removeChild(g.firstChild);

    var ex = window.EXIST_EDGES || [];
    for (var i=0;i<ex.length;i++){
      var e = ex[i]; if (!e || !e.from || !e.to) continue;
      var a = anchorParentLeft(e.from), b = anchorChildTop(e.to);
      if (!a || !b || !isFinite(a.x) || !isFinite(a.y) || !isFinite(b.x) || !isFinite(b.y)) continue;
      var path = document.createElementNS('http://www.w3.org/2000/svg','path');
      path.setAttribute('class','dep-edge existing link-existing');
      path.setAttribute('fill','none');
      path.setAttribute('d', makePath(a,b));
      path.setAttribute('marker-end','url(#depArrow)');
      path.setAttribute('data-from', String(e.from));
      path.setAttribute('data-to',   String(e.to));
      g.appendChild(path);
    }

    try{ if (typeof refreshDepHandleLetters === 'function') refreshDepHandleLetters(); }catch(_){}
  };

  // refresh on resize (layout changes positions)
  window.addEventListener('resize', function(){
    try{ if (typeof drawLinks === 'function') drawLinks(); }catch(_){}
  }, {passive:true});

  // initial paint
  setTimeout(function(){ try{ if (typeof drawLinks === 'function') drawLinks(); }catch(_){} }, 0);

  window.__existingSolidV3A = true;
})();
</script>


<!-- PROJECT_PICKER_V2_CSS -->
<style id="PROJECT_PICKER_V2_CSS">
/* === Project picker modal (V2: multi-select) === */
.projPickOverlay{ position:fixed; inset:0; background:rgba(0,0,0,.45);
  display:flex; align-items:center; justify-content:center; z-index:40000; }
.projPick{ width:min(820px, 94vw); max-height:82vh; background:#0f1525; color:var(--fg, #c9d1d9);
  border:1px solid #2a3344; border-radius:12px; box-shadow:0 18px 48px rgba(0,0,0,.50);
  display:flex; flex-direction:column; overflow:hidden; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; }
.projPickHeader{ padding:10px; display:flex; gap:8px; align-items:center; border-bottom:1px solid #202736; }
.projPickHeader input{ flex:1; padding:10px 12px; border-radius:8px; border:1px solid #2a3344; background:#0e1320; color:inherit; }
.projPickHeader .btn{ padding:8px 10px; border:1px solid #2a3344; background:#121a2b; color:inherit; border-radius:8px; }
.projPickList{ overflow:auto; padding:6px; }
.projPickItem{ display:flex; justify-content:space-between; gap:10px; padding:10px 12px; border-radius:8px; cursor:pointer; align-items:center; }
.projPickItem:hover, .projPickItem.active{ background:#121a2b; }
.projPickItem .left{ display:flex; gap:10px; align-items:center; min-width:0; }
.projPickItem label{ display:flex; gap:10px; align-items:center; cursor:pointer; }
.projPickItem input[type="checkbox"]{ width:18px; height:18px; }
.projPickItem .name{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:52vw; }
.projPickItem .right{ color:var(--muted, #8b949e); }
.projPickFooter{ display:flex; justify-content:space-between; align-items:center; padding:10px 12px; border-top:1px solid #202736; color:var(--muted, #8b949e); font-size:12px; gap:10px; }
.projPickFooter .rightBtns{ display:flex; gap:8px; }
.projPickFooter .btn{ padding:8px 10px; border:1px solid #2a3344; background:#121a2b; color:inherit; border-radius:8px; font-size:13px; }
.projPickFooter .btn.primary{ background:#1b2945; border-color:#2d3a55; }
</style>
<!-- PROJECT_PICKER_V2_JS -->
<script id="PROJECT_PICKER_V2_JS">
(function(){
  if (window.__ProjPickerV2__) return; window.__ProjPickerV2__ = true;

  function makePicker(projects, counts){
    var ov = document.createElement('div'); ov.className = 'projPickOverlay';
    var box = document.createElement('div'); box.className = 'projPick';

    // Header
    var head = document.createElement('div'); head.className = 'projPickHeader';
    var inp = document.createElement('input'); inp.placeholder = 'Filter projects…';
    var btnClose = document.createElement('button'); btnClose.className='btn'; btnClose.textContent='Close';
    head.appendChild(inp); head.appendChild(btnClose);

    // List
    var list = document.createElement('div'); list.className = 'projPickList';

    // Footer
    var foot = document.createElement('div'); foot.className = 'projPickFooter';
    var info = document.createElement('div'); info.textContent = '';
    var right = document.createElement('div'); right.className = 'rightBtns';
    var btnAll = document.createElement('button'); btnAll.className='btn'; btnAll.textContent='Select all';
    var btnNone = document.createElement('button'); btnNone.className='btn'; btnNone.textContent='Clear';
    var btnAdd = document.createElement('button'); btnAdd.className='btn primary'; btnAdd.textContent='Add selected';
    right.appendChild(btnAll); right.appendChild(btnNone); right.appendChild(btnAdd);
    foot.appendChild(info); foot.appendChild(right);

    box.appendChild(head); box.appendChild(list); box.appendChild(foot);
    ov.appendChild(box);

    // Data / state
    var filtered = projects.slice();
    var activeIdx = 0;
    var selected = new Set();  // stores project names

    function render(){
      list.innerHTML = '';
      info.textContent = selected.size + ' selected · ' + filtered.length + ' shown / ' + projects.length + ' total';
      filtered.forEach(function(p, i){
        var it = document.createElement('div'); it.className = 'projPickItem' + (i===activeIdx?' active':'');
        var left = document.createElement('div'); left.className='left';
        var label = document.createElement('label');
        var cb = document.createElement('input'); cb.type='checkbox'; cb.checked = selected.has(p);
        var span = document.createElement('span'); span.className='name'; span.textContent = p;
        label.appendChild(cb); label.appendChild(span);
        left.appendChild(label);

        var right = document.createElement('div'); right.className='right';
        right.textContent = '(' + (counts[p]||0) + ')';

        it.appendChild(left); it.appendChild(right);
        it.addEventListener('mouseenter', function(){ activeIdx = i; hilite(); });
        it.addEventListener('click', function(e){
          if (e.target.tagName !== 'INPUT'){ cb.checked = !cb.checked; }
          toggle(p, cb.checked);
          // keep focus for keyboard flow
          inp.focus();
        });
        list.appendChild(it);
      });
      hilite();
    }

    function hilite(){
      var items = list.children;
      for (var i=0;i<items.length;i++){
        if (i===activeIdx) items[i].classList.add('active'); else items[i].classList.remove('active');
      }
    }

    function refilter(){
      var q = (inp.value||'').toLowerCase().trim();
      filtered = projects.filter(function(p){ return !q || p.toLowerCase().indexOf(q) !== -1; });
      activeIdx = Math.min(activeIdx, Math.max(0, filtered.length-1));
      render();
    }

    function toggle(p, on){
      if (on) selected.add(p); else selected.delete(p);
      info.textContent = selected.size + ' selected · ' + filtered.length + ' shown / ' + projects.length + ' total';
    }

    function selectAll(){
      filtered.forEach(function(p){ selected.add(p); }); render();
    }
    function selectNone(){
      selected.clear(); render();
    }

    function confirm(){
      if (!selected.size){ cleanup(); return; }
      var arr = Array.from(selected);
      cleanup();
      // public callbacks
      if (typeof window.onProjectPickedMany === 'function'){ window.onProjectPickedMany(arr); return; }
      if (typeof window.onProjectPicked === 'function'){ window.onProjectPicked(arr[0]); } // fallback single
    }

    function cleanup(){
      document.removeEventListener('keydown', onKey);
      try{ ov.remove(); }catch(_){}
    }

    function onKey(e){
      if (e.key === 'Escape'){ e.preventDefault(); cleanup(); return; }
      if (e.key === 'Enter'){ e.preventDefault(); confirm(); return; }
      if (e.key === ' ' || e.code === 'Space'){ // toggle current
        e.preventDefault();
        if (filtered.length){
          var p = filtered[activeIdx];
          var on = !selected.has(p);
          toggle(p, on);
          render();
        }
        return;
      }
      if (e.key === 'ArrowDown'){ e.preventDefault(); activeIdx = Math.min(activeIdx+1, Math.max(0, filtered.length-1)); hilite(); return; }
      if (e.key === 'ArrowUp'){ e.preventDefault(); activeIdx = Math.max(activeIdx-1, 0); hilite(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a'){ e.preventDefault(); selectAll(); return; }
    }

    btnClose.addEventListener('click', cleanup);
    ov.addEventListener('click', function(ev){ if (ev.target === ov) cleanup(); });
    document.addEventListener('keydown', onKey);
    inp.addEventListener('input', refilter);
    btnAll.addEventListener('click', selectAll);
    btnNone.addEventListener('click', selectNone);
    btnAdd.addEventListener('click', confirm);

    document.body.appendChild(ov);
    setTimeout(function(){ try{ inp.focus(); }catch(_){ } }, 0);
    render();
  }

  // Build & show picker from window.TASKS
  window.showProjectPickerV2 = function(){
    try{
      var set={}, counts={}, arr=[];
      (window.TASKS||[]).forEach(function(t){
        var p = (t && (t.project||'(no project)')) || '(no project)';
        if (!set[p]){ set[p]=1; arr.push(p); }
        counts[p] = (counts[p]||0) + 1;
      });
      arr.sort();
      makePicker(arr, counts);
    }catch(e){
      console.error('ProjectPickerV2 error', e);
      alert('Could not open project picker.');
    }
  };

})();
</script>
<!-- PROJECT_PICKER_V2_BIND -->
<script id="PROJECT_PICKER_V2_BIND">
(function(){
  if (window.__ProjPickerV2_BIND__) return; window.__ProjPickerV2_BIND__ = true;

  // Multi-project add: sums up added tasks and shows a compact summary
  window.onProjectPickedMany = function(projects){
    var totalAdded = 0, per = [];
    try{
      for (var i=0;i<projects.length;i++){
        var p = projects[i];
        var n = 0;
        try { n = addProjectTasks(p) | 0; } catch(_){}
        totalAdded += (n|0);
        per.push(p + ' +' + (n|0));
      }
      alert('Added ' + totalAdded + ' task(s) from ' + projects.length + ' project(s):\n' + per.join('\n'));
    }catch(e){
      alert('Add failed for some projects. Added so far: ' + totalAdded);
    }
  };

  // Keep single-project fallback
  window.onProjectPicked = function(p){
    try{
      var n = addProjectTasks(p) | 0;
      alert("Added " + n + " task(s) from project '" + p + "'");
    }catch(e){
      alert("Failed to add project '" + p + "'.");
    }
  };

  // Rebind FAB cleanly
  function bind(){
    var btn = document.getElementById('fabAddProject');
    if (!btn) return;
    var cloned = btn.cloneNode(true);
    btn.parentNode.replaceChild(cloned, btn); // remove old listeners
    cloned.addEventListener('click', function(){
      try{
        if (typeof fabMenu !== 'undefined' && fabMenu && fabMenu.classList) {
          fabMenu.classList.add('hidden');
        }
      }catch(_){}
      showProjectPickerV2();
    });
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', bind);
  }else{
    bind();
  }
})();
</script>
</body></html>"""

HTML = HTML.replace('</body>', '\n<!-- NEW_PROJECT_MODAL_V2_MINIMAL -->\n<script id="NEW_PROJECT_MODAL_V2_MINIMAL">\n(function(){\n  // Always prefer V2: neutralize any V1 guard and remove old fallback boxes\n  try{ delete window.__NEW_PROJECT_MODAL_V1__; }catch(_){}\n  function cleanupFallback(){\n    try{ document.querySelectorAll(\'.npProjBox, .projGhost\').forEach(function(n){ n.remove(); }); }catch(_){}\n  }\n\n  // Small, inline-styled modal to avoid needing CSS edits in the template\n  function showNewProjectModal(){\n    var ov = document.createElement(\'div\');\n    ov.style.position=\'fixed\'; ov.style.left=0; ov.style.top=0; ov.style.right=0; ov.style.bottom=0;\n    ov.style.background=\'rgba(0,0,0,.45)\'; ov.style.zIndex=40010;\n    ov.style.display=\'flex\'; ov.style.alignItems=\'center\'; ov.style.justifyContent=\'center\';\n\n    var box = document.createElement(\'div\');\n    box.style.width=\'min(560px,92vw)\'; box.style.maxWidth=\'92vw\';\n    box.style.background=\'#0f1525\'; box.style.color=\'var(--fg,#c9d1d9)\';\n    box.style.border=\'1px solid #2a3344\'; box.style.borderRadius=\'12px\';\n    box.style.boxShadow=\'0 18px 48px rgba(0,0,0,.5)\'; box.style.overflow=\'hidden\';\n\n    var head = document.createElement(\'div\');\n    head.textContent=\'Create new project\';\n    head.style.padding=\'12px\'; head.style.borderBottom=\'1px solid #202736\'; head.style.fontWeight=\'600\';\n\n    var body = document.createElement(\'div\');\n    body.style.padding=\'14px\'; body.style.display=\'flex\'; body.style.flexDirection=\'column\'; body.style.gap=\'10px\';\n    var lab = document.createElement(\'label\'); lab.textContent=\'Project name\';\n    var inp = document.createElement(\'input\');\n    inp.placeholder=\'e.g. Home.Renovation\';\n    inp.style.padding=\'10px 12px\'; inp.style.borderRadius=\'8px\'; inp.style.border=\'1px solid #2a3344\';\n    inp.style.background=\'#0e1320\'; inp.style.color=\'inherit\';\n\n    var foot = document.createElement(\'div\');\n    foot.style.padding=\'10px 12px\'; foot.style.borderTop=\'1px solid #202736\';\n    foot.style.display=\'flex\'; foot.style.justifyContent=\'flex-end\'; foot.style.gap=\'8px\';\n    var cancel = document.createElement(\'button\');\n    cancel.textContent=\'Cancel\';\n    cancel.style.padding=\'8px 10px\'; cancel.style.border=\'1px solid #2a3344\';\n    cancel.style.background=\'#121a2b\'; cancel.style.color=\'inherit\'; cancel.style.borderRadius=\'8px\';\n    var create = document.createElement(\'button\');\n    create.textContent=\'Create\';\n    create.style.padding=\'8px 10px\'; create.style.border=\'1px solid #2d3a55\';\n    create.style.background=\'#1b2945\'; create.style.color=\'inherit\'; create.style.borderRadius=\'8px\';\n\n    body.appendChild(lab); body.appendChild(inp);\n    foot.appendChild(cancel); foot.appendChild(create);\n    box.appendChild(head); box.appendChild(body); box.appendChild(foot);\n    ov.appendChild(box); document.body.appendChild(ov);\n\n    function close(){ try{ document.removeEventListener(\'keydown\', onKey); }catch(_){}\n      try{ ov.remove(); }catch(_){}\n    }\n    function onKey(e){ if(e.key===\'Escape\'){e.preventDefault();close();}\n                       else if(e.key===\'Enter\'){e.preventDefault();doCreate();} }\n\n    function centerIntoView(el){\n      try{\n        var cv = document.querySelector(\'#builderWrap .canvas\') || document.querySelector(\'.canvas\');\n        if (!cv || !el) return;\n        var cvr = cv.getBoundingClientRect(), er = el.getBoundingClientRect();\n        var dx = (er.left+er.width/2) - (cvr.left+cvr.width/2);\n        var dy = (er.top +er.height/2) - (cvr.top +cv.clientHeight/2);\n        cv.scrollTo({\n          left: Math.max(0, Math.min(cv.scrollWidth-cv.clientWidth,  cv.scrollLeft + dx)),\n          top:  Math.max(0, Math.min(cv.scrollHeight-cv.clientHeight, cv.scrollTop  + dy)),\n          behavior: \'smooth\'\n        });\n      }catch(_){}\n    }\n\n    function projectExists(name){\n      name=(name||\'\').trim(); if(!name) return false;\n      try{ if (window.projectAreas && typeof projectAreas.has===\'function\') return projectAreas.has(name); }catch(_){}\n      try{ return !!document.querySelector(\'.projArea[data-proj="\'+CSS.escape(name)+\'"]\'); }catch(_){ return !!document.querySelector(\'.projArea[data-proj="\'+name+\'"]\'); }\n    }\n\n    function doCreate(){\n      var name=(inp.value||\'\').trim(); if(!name){ inp.focus(); return; }\n      if (projectExists(name)){\n        try{ showToast && showToast(\'Project "\'+name+\'" already exists.\'); }catch(_){}\n        centerIntoView(document.querySelector(\'.projArea[data-proj="\'+(CSS?.escape?CSS.escape(name):name)+\'"]\'));\n        return;\n      }\n      try{ typeof ensureProjectArea===\'function\' && ensureProjectArea(name); }catch(_){}\n      try{ typeof recomputeAreasAndTags===\'function\' && recomputeAreasAndTags(); }catch(_){}\n      setTimeout(function(){\n        try{\n          var el = document.querySelector(\'.projArea[data-proj="\'+(CSS?.escape?CSS.escape(name):name)+\'"]\');\n          centerIntoView(el);\n          try{ showToast && showToast(\'Project "\'+name+\'" created.\'); }catch(_){}\n        }catch(_){}\n      },0);\n      close();\n    }\n\n    cancel.addEventListener(\'click\', close);\n    create.addEventListener(\'click\', doCreate);\n    setTimeout(function(){ try{ inp.focus(); }catch(_){} },0);\n    document.addEventListener(\'keydown\', onKey);\n  }\n\n  function normalize(s){ return (s||\'\').replace(/\\s+/g,\' \').trim().toLowerCase(); }\n\n  function rebindFAB(){\n    var menu = document.getElementById(\'fabMenu\') || document.querySelector(\'.fab-menu, #fab\');\n    var items = Array.from((menu||document).querySelectorAll(\'button, .item, [data-action]\'));\n    var target = null;\n\n    // If we already have a create-project entry, use it\n    target = items.find(function(el){ return (el.getAttribute(\'data-action\')||\'\').toLowerCase()===\'create-project\'; });\n    // Else hijack "Add new task"\n    if (!target){\n      target = items.find(function(el){\n        var t = normalize(el.textContent);\n        return t===\'add new task\' || t===\'add task\' || /add.*new.*task/.test(t);\n      });\n    }\n\n    if (target){\n      target.textContent = \'Add new project\';\n      target.setAttribute(\'data-action\',\'create-project\');\n      var c = target.cloneNode(true);\n      target.replaceWith(c);\n      c.addEventListener(\'click\', function(){\n        try{ (document.getElementById(\'fabMenu\')||window.fabMenu)?.classList.add(\'hidden\'); }catch(_){}\n        showNewProjectModal();\n      });\n    }else if(menu && !document.getElementById(\'fabCreateProject\')){\n      var btn=document.createElement(\'button\');\n      btn.id=\'fabCreateProject\'; btn.className=\'fab-item\'; btn.textContent=\'Add new project\';\n      btn.style.marginTop=\'8px\';\n      btn.addEventListener(\'click\', showNewProjectModal);\n      menu.appendChild(btn);\n    }\n  }\n\n  function boot(){\n    cleanupFallback();\n    rebindFAB();\n  }\n  if (document.readyState===\'loading\') document.addEventListener(\'DOMContentLoaded\', boot); else boot();\n})();\n</script>\n' + '\n</body>')

def open_file(path: Path):
    try:
        if os.environ.get("TERMUX_VERSION"):
            subprocess.Popen(["termux-open", str(path)])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore
        else:
            print(f"Open {path} in your browser.")
    except Exception:
        print(f"Open {path} in your browser.")

def _extract_filter_arg(argv):
    """
    Returns (filter_str, remaining_args).
    Supports:
      -f "project:Work +P1"
      --filter "due.before:2025-10-01 status:pending"
      --filter=project:Work
    """
    filt = None
    out = []
    skip_next = False
    for i, a in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if a == "-f" or a == "--filter":
            # take the next token as the filter string (user should quote if spaces)
            if i + 1 < len(argv):
                filt = argv[i + 1]
                skip_next = True
            else:
                filt = ""
        elif a.startswith("--filter="):
            filt = a.split("=", 1)[1]
        else:
            out.append(a)
    return filt, out

def inject_wire_deps_as_main(html: str) -> str:
    # CSS into </head>
    if "__ONLY_DEPS_CONSOLE_CSS__" not in html:
        html = (re.sub(r'</head\s*>', lambda m: CSS_WIRE_DEPS_AS_MAIN + '\n' + m.group(0), html, count=1, flags=re.I)
                if re.search(r'</head\s*>', html, flags=re.I) else CSS_WIRE_DEPS_AS_MAIN + html)
    # JS into </body>
    if "__ONLY_DEPS_CONSOLE_JS__" not in html:
        html = (re.sub(r'</body\s*>', lambda m: JS_WIRE_DEPS_AS_MAIN + '\n' + m.group(0), html, count=1, flags=re.I)
                if re.search(r'</body\s*>', html, flags=re.I) else html + '\n' + JS_WIRE_DEPS_AS_MAIN)
    return html


def _extract_bg_args(argv):
    """Parse --bg=FILE and --bg-opacity=0.00, return (bg_path_str, opacity_str, remaining_args)."""
    bg = None
    opacity = None
    out = []
    skip = False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a == "--bg":
            if i + 1 < len(argv):
                bg = argv[i + 1]; skip = True
            else:
                bg = ""
        elif a.startswith("--bg="):
            bg = a.split("=", 1)[1]
        elif a.startswith("--bg-opacity="):
            opacity = a.split("=", 1)[1]
        else:
            out.append(a)
    return bg, opacity, out

def _find_bg_file(prefer: str | None):
    """Look for a background image either by explicit path or by common names in script dir / CWD."""
    from pathlib import Path
    exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg")
    script_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()

    candidates = []
    if prefer:
        p = Path(prefer)
        candidates.append(p if p.is_absolute() else (cwd / p))
        candidates.append(script_dir / p.name)
    names = ["taskcanvas-bg", "TaskCanvas.bg", "canvas-bg", "background", "bg"]
    for root in (script_dir, cwd):
        for name in names:
            for ext in exts:
                candidates.append(root / f"{name}{ext}")

    for p in candidates:
        if p.is_file():
            return p
    return None

def inject_custom_background(html: str, img_path, opacity: str | None = None) -> str:
    """
    Ensures the background image is next to OUT_HTML and injects a <style> overlay.
    Uses a body::before fixed cover layer with adjustable opacity.
    """
    import re, shutil
    try:
        out_dir = OUT_HTML.parent  # uses existing OUT_HTML
        out_img = out_dir / img_path.name
        if img_path.resolve() != out_img.resolve():
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(img_path), str(out_img))
                eprint(f"[TaskCanvas] Copied bg → {out_img.name}")
            except Exception as e:
                eprint(f"[TaskCanvas] Copy bg failed: {e}; will still reference original name.")
        op = opacity if (opacity and opacity.strip()) else "0.18"
        css = f"""
<style id="FEATURE_CUSTOM_BG_V1">
  html,body{{background:var(--bg);}}
  body{{position:relative;}}
  body::before{{
    content:"";
    position:fixed; inset:0;
    background:url('{out_img.name}') center/cover no-repeat fixed;
    opacity:{op};
    pointer-events:none; z-index:0;
  }}
  .app{{position:relative; z-index:1;}}
</style>""".strip()
        if re.search(r'</head\s*>', html, flags=re.I):
            return re.sub(r'</head\s*>', css + '\n</head>', html, count=1, flags=re.I)
        else:
            return css + html
    except Exception as e:
        eprint(f"[TaskCanvas] custom bg inject failed: {e}")
        return html

def main():
    raw_args = sys.argv[1:]
    filter_str, args_wo_filter = _extract_filter_arg(raw_args)

    # 1) Load ALL pending tasks for the payload (drawer/search, etc.)
    tasks_all = fetch_tasks(None)

    # 2) If filter is present, run it separately and capture just the UUIDs to auto-place
    init_task_uuids = []
    if filter_str:
        filtered = fetch_tasks(filter_str)
        init_task_uuids = [t["uuid"] for t in filtered]

    # 3) Build payload using *all* tasks
    payload = build_payload(tasks_all)
    json_text = _json_text(payload)

    # 4) Merge selector/positional args (these are still supported)
    init_projects = []
    if any(a == "--selector" for a in args_wo_filter):
        try:
            init_projects = run_project_selector(tasks_all)
        except Exception as e:
            print(f"[selector] error: {e}")

    extra = [a for a in args_wo_filter if a and not a.startswith("-")]
    if extra:
        seen = set(init_projects)
        for p in extra:
            if p not in seen:
                init_projects.append(p); seen.add(p)

    # 5) Store initial placements into payload
    changed = False
    if init_projects:
        payload["init_projects"] = init_projects
        changed = True
    if init_task_uuids:
        payload["init_task_uuids"] = init_task_uuids 
        changed = True
    if changed:
        json_text = _json_text(payload)

    def _to_js_chunks(s, chunk=8000):
        esc = (
            s.replace("\\", "\\\\")
             .replace("'", "\\'")
             .replace("\r", "\\r")
             .replace("\n", "\\n")
             .replace("</script", "<\\/script")
             .replace("<!--", "<\\!--")
        )
        return [esc[i:i+chunk] for i in range(0, len(esc), chunk)] if esc else []

    html = HTML.replace("<!-- INLINE_PAYLOAD_HERE -->", "")
    
    # Append JSON payload at end of body (robust)
    safe_json = json_text.replace("</script", "<\/script")
    payload_tag = ("<script id='payload_data' type='application/json'>" + safe_json + "</script>\n")
    runner = """<script>(function(){
      try{
        var el = document.getElementById('payload_data');
        var raw = el ? el.textContent : '';
        window.__RAW_LEN__ = raw.length;
        console.log('[payload] raw length (end) =', window.__RAW_LEN__);
        window.DATA = JSON.parse(raw);
        window.DATA_READY = true;
        var tlen = (window.DATA && Array.isArray(window.DATA.tasks)) ? window.DATA.tasks.length : 0;
        console.log('[payload] tasks =', tlen);
        try { document.dispatchEvent(new CustomEvent('twdata')); } catch(_) {}
    try {
      if (!window.__INIT_DONE__ && typeof initFromDATA==='function') {
        window.__INIT_DONE__ = true;
        console.log('[payload] calling initFromDATA directly');
        initFromDATA();
      }
    } catch(e) { console.log('[payload] initFromDATA error', e); }
    try {
      if (!window.__INIT_DONE__ && typeof initFromDATA==='function') {
        window.__INIT_DONE__ = true;
        console.log('[payload] calling initFromDATA directly');
        initFromDATA();
      }
    } catch(e) { console.log('[payload] initFromDATA error', e); }
      } catch(e){
        console.log('[payload] parse error', e);
        window.DATA = {tasks:[],graph:{}}; window.DATA_READY = false;
      }
    })();</script>
    """
    html = html.replace("</body>", payload_tag + runner + "</body>")

    # --- Feature: hover actions + staging & due badge (inline) ---
    CSS_HOVER = r'''<style id="feature-hover-css">
      .node:hover .nodeActions{opacity:1; pointer-events:auto}
      .nodeActions{position:absolute; right:6px; bottom:6px; display:flex; gap:6px; opacity:0; pointer-events:none;}
      .nodeActions button{border:1px solid #2a3344; background:#1b2230; color:var(--fg); border-radius:8px; padding:2px 6px; font-size:12px; cursor:pointer}
      .stagedDone{ outline:2px solid rgba(34,197,94,.95); box-shadow:0 0 0 5px rgba(34,197,94,.24) inset; background:linear-gradient(180deg, rgba(34,197,94,.10), rgba(34,197,94,.06)); }
      .stagedDel{ outline:4px solid #ef4444; box-shadow:0 0 0 7px rgba(239,68,68,.34) inset; background:linear-gradient(180deg, rgba(239,68,68,.28), rgba(239,68,68,.14)); }
      .stagedDone .title, .stagedDel .title{ text-decoration:line-through; opacity:.94 }
    </style>'''

    JS_HOVER = r'''<script id="FEATURE_HOVERSTAGE">(function(){
      if (window.__FEATURE_HOVERSTAGE__) return; window.__FEATURE_HOVERSTAGE__=true;
      function ensureArrays(){ if(!window.STAGED_CMDS) window.STAGED_CMDS=[]; if(!window.STAGED_HUMAN) window.STAGED_HUMAN=[]; }
      function removeFrom(arr, pred){ var out=[],removed=false; for(var i=0;i<arr.length;i++){ if(pred(arr[i],i)) removed=true; else out.push(arr[i]); } return {out:out, removed:removed}; }
      function stageAdd(cmd, human){ ensureArrays(); window.STAGED_CMDS.push(cmd); window.STAGED_HUMAN.push(human); try{updateConsole();}catch(_){}} 
      function stageToggle(node, task, kind){
        ensureArrays();
        var uid = (task && task.uuid) || (node && node.getAttribute('data-uuid')) || (node && node.getAttribute('data-short')) || '';
        var short = (task && task.short) || (node && node.getAttribute('data-short')) || 'task';
        var desc = (task && task.desc) || ((node && node.querySelector('.title'))? node.querySelector('.title').textContent : '');
        var cmd = 'task '+uid+' '+(kind==='done'?'done':'delete');
        var human = (kind==='done'?'DONE ':'DELETE ') + short + ' — ' + desc;
        var cls = (kind==='done'?'stagedDone':'stagedDel');
        if (!node) return;
        if (node.classList.contains(cls)){
          var res1 = removeFrom(window.STAGED_CMDS,  function(s){ return s===cmd; });
          var res2 = removeFrom(window.STAGED_HUMAN, function(s){ return s===human; });
          window.STAGED_CMDS = res1.out; window.STAGED_HUMAN = res2.out;
          node.classList.remove(cls);
        } else {
          window.STAGED_CMDS.push(cmd); window.STAGED_HUMAN.push(human); node.classList.add(cls);
          var other = (kind==='done'?'stagedDel':'stagedDone');
          if (node.classList.contains(other)){
            node.classList.remove(other);
            var cmdOther = 'task '+uid+' '+(kind==='done'?'delete':'done');
            var humanOther = (kind==='done'?'DELETE ':'DONE ') + short + ' — '+ desc;
            window.STAGED_CMDS = removeFrom(window.STAGED_CMDS,  function(s){ return s===cmdOther; }).out;
            window.STAGED_HUMAN = removeFrom(window.STAGED_HUMAN, function(s){ return s===humanOther; }).out;
          }
        }
        try{ updateConsole(); }catch(_){}
      }
      function findTaskByShort(short){
        try{ if (window.TASKS){ for(var i=0;i<TASKS.length;i++){ if(TASKS[i].short===short) return TASKS[i]; } } }catch(_){}
        return null;
      }
      function installHoverForNode(node, task){
        if (!node || node.querySelector('.nodeActions')) return;
        var bar = document.createElement('div'); bar.className='nodeActions';
        bar.innerHTML = '<button class="btnDone" title="Mark done">✓</button>'
                      + '<button class="btnDel" title="Delete">🗑</button>'
                      + '<button class="btnMod" title="Modify">✎</button>';
        node.appendChild(bar);
        var t = task;
        if (!t){
          var short = node.getAttribute('data-short');
          t = findTaskByShort(short) || { uuid: (node.getAttribute('data-uuid')||short), short: short||'task', desc: ((node.querySelector('.title')||{}).textContent||'') };
        }
        var b1 = bar.querySelector('.btnDone'); if(b1){ b1.addEventListener('click', function(e){ e.stopPropagation(); stageToggle(node, t, 'done'); }); }
        var b2 = bar.querySelector('.btnDel');  if(b2){ b2.addEventListener('click', function(e){ e.stopPropagation(); stageToggle(node, t, 'delete'); }); }
        var b3 = bar.querySelector('.btnMod');  if(b3){ b3.addEventListener('click', function(e){ e.stopPropagation(); var mods=prompt('Modifiers (e.g., pri:H due:2025-09-20 +tag -oldtag):',''); if(mods==null) return; mods=mods.trim(); if(!mods) return; stageAdd('task '+t.uuid+' modify '+mods, 'MODIFY '+t.short+' — '+mods); }); }
      }
      function attachDataAttributes(){
        try{
          var nodes = document.querySelectorAll('.node');
          for (var i=0;i<nodes.length;i++){
            var n=nodes[i];
            if (!n.getAttribute('data-short')){
              var guess = n.getAttribute('data-id') || n.getAttribute('data-key') || (n.querySelector('.short')||{}).textContent || '';
              if (guess) n.setAttribute('data-short', guess);
            }
            if (!n.getAttribute('data-uuid')){
              var srt = n.getAttribute('data-short');
              var t = srt && findTaskByShort(srt);
              if (t) n.setAttribute('data-uuid', t.uuid);
            }
          }
        }catch(_){}
      }
      (function(){
        if (!window.__HOVERSTAGE_NODE_WRAP__ && typeof window.addNodeForTask === 'function'){
          window.__HOVERSTAGE_NODE_WRAP__ = true;
          var old = window.addNodeForTask;
          window.addNodeForTask = function(task, cx, cy, opts){
            var n = old.apply(this, arguments);
            try{
              if (n && task){
                if (!n.getAttribute('data-uuid') && task.uuid) n.setAttribute('data-uuid', task.uuid);
                if (!n.getAttribute('data-short') && task.short) n.setAttribute('data-short', task.short);
              }
            }catch(_){}
            try{ installHoverForNode(n, task); }catch(_){}
            return n;
          };
        }
      })();
      function wrapUpdateConsoleLate(){
        try{
          if (window.__HOVERSTAGE_WRAP_UPDATE__) return;
          if (typeof window.updateConsole !== 'function') return;
          if (window.updateConsole && window.updateConsole.__hoverstageWrapped) return;
          var orig = window.updateConsole;
          function wrapper(){
            var rv = orig.apply(this, arguments);
            try{
              var ct = document.getElementById('consoleText');
              if (ct){
                var base = ct.value || '';
                var staged = (window.STAGED_CMDS||[]).join('\\n');
                if (staged){
                  if (base.indexOf(staged)!==0){
                    ct.value = staged + (base? '\\n'+base : '');
                  }
                }
              }
            }catch(_){}
            return rv;
          }
          wrapper.__hoverstageWrapped = true;
          window.updateConsole = wrapper;
          window.__HOVERSTAGE_WRAP_UPDATE__ = true;
          try{ window.updateConsole(); }catch(_){}
        }catch(_){}
      }
      function kick(){
        try{ attachDataAttributes(); }catch(_){}
        try{
          var nodes=document.querySelectorAll('.node');
          for (var i=0;i<nodes.length;i++){ installHoverForNode(nodes[i], null); }
        }catch(_){}
        try{ wrapUpdateConsoleLate(); }catch(_){}
      }
      document.addEventListener('twdata', function(){ setTimeout(kick, 0); });
      window.addEventListener('load', function(){ setTimeout(kick, 60); });
      var oldRe = window.recomputeAreasAndTags;
      if (typeof oldRe === 'function'){
        window.recomputeAreasAndTags = function(){
          var r = oldRe.apply(this, arguments);
          try{ kick(); }catch(_){}
          return r;
        };
      }
    })();</script>'''

    CSS_DUE = r'''<style id="feature-due-css-v2">
      .node.hasDue{ padding-top: 28px; }
      .dueBadge{
        position:absolute; left:6px !important; top:4px !important; bottom:auto !important;
        display:inline-flex; align-items:center; gap:6px;
        padding:2px 6px; border-radius:8px; font-size:12px;
        border:1px solid #3a4456; background:rgba(58,68,86,.18); color:#cfd8e3;
        pointer-events:none; user-select:none; z-index:2;
      }
      .dueBadge .clock{font-size:12px; opacity:.9}
      .dueOverdue{ border-color:#ef4444; background:rgba(239,68,68,.16); color:#fecaca; }
      .dueSoon{ border-color:#f59e0b; background:rgba(245,158,11,.14); color:#fde68a; }
      .dueFuture{ opacity:.9 }
    </style>'''

    JS_DUE = r'''<script id="FEATURE_DUEBADGE2">(function(){
      if (window.__FEATURE_DUEBADGE2__) return; window.__FEATURE_DUEBADGE2__=true;
      function tasksArray(){
        try{
          if (window.DATA && Array.isArray(window.DATA.tasks)) return window.DATA.tasks;
          if (Array.isArray(window.TASKS)) return window.TASKS;
        }catch(_){}
        return [];
      }
      function taskByShort(s){
        var arr = tasksArray();
        for (var i=0;i<arr.length;i++) if (arr[i].short===s) return arr[i];
        return null;
      }
      function parseTWDue(s){
        if (!s || typeof s!=='string') return null;
        try{
          var m;
          if ((m = s.match(/^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})Z)?$/))){
            var Y=+m[1], M=+m[2]-1, D=+m[3], h=+(m[4]||'0'), mi=+(m[5]||'0'), se=+(m[6]||'0');
            if (m[4]) return new Date(Date.UTC(Y,M,D,h,mi,se));
            return new Date(Y, M, D, 0, 0, 0);
          }
          if ((m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?Z)?$/))){
            var Y=+m[1], M=+m[2]-1, D=+m[3], h=+(m[4]||'0'), mi=+(m[5]||'0'), se=+(m[6]||'0');
            if (m[4]) return new Date(Date.UTC(Y,M,D,h,mi,se));
            return new Date(Y, M, D, 0, 0, 0);
          }
          var d = new Date(s);
          if (!isNaN(d.getTime())) return d;
        }catch(_){}
        return null;
      }
      function pad(n){ return (n<10?'0':'')+n; }
      function fmtLocal(dt){
        try{
          return dt.getFullYear()+'-'+pad(dt.getMonth()+1)+'-'+pad(dt.getDate())+' '+pad(dt.getHours())+':'+pad(dt.getMinutes());
        }catch(_){ return '—'; }
      }
      function deltaString(due){
        var now = new Date();
        var ms = now.getTime() - due.getTime(); // overdue -> positive
        var sign = ms>=0 ? '+' : '-';
        var abs = Math.abs(ms);
        var mins = Math.floor(abs/60000);
        var txt;
        if (mins >= 1440){
          txt = Math.round(mins/1440) + 'd';
        } else if (mins >= 60){
          txt = Math.round(mins/60) + 'h';
        } else {
          txt = mins + 'm';
        }
        return { sign: sign, text: sign+txt, ms: ms };
      }
      function classForDelta(ms){
        if (ms >= 0) return 'dueOverdue';
        if (Math.abs(ms) <= 72*3600*1000) return 'dueSoon';
        return 'dueFuture';
      }
      function ensureDueBadgeTop(node, task){
        try{
          if (!node) return;
          var t = task || (function(){ var s = node.getAttribute('data-short'); return taskByShort(s); })();
          if (!t || !t.due) { node.classList.remove('hasDue'); return; }
          var due = parseTWDue(String(t.due));
          if (!due) { node.classList.remove('hasDue'); return; }
          var info = deltaString(due);
          var existing = node.querySelector('.dueBadge');
          var cls = classForDelta(info.ms);
          var label = '⏰';
          if (!existing){
            var b = document.createElement('div');
            b.className = 'dueBadge '+cls;
            b.innerHTML = '<span class="clock">'+label+'</span>'
                        + '<span class="when">'+fmtLocal(due)+'</span>'
                        + '<span class="delta">· '+info.text+'</span>';
            node.insertBefore(b, node.firstChild);
          } else {
            existing.classList.remove('dueOverdue','dueSoon','dueFuture');
            existing.classList.add(cls);
            var w = existing.querySelector('.when'), d = existing.querySelector('.delta');
            if (w) w.textContent = fmtLocal(due);
            if (d) d.textContent = '· '+info.text;
            if (existing.previousSibling){ try{ node.insertBefore(existing, node.firstChild); }catch(_){} }
          }
          node.classList.add('hasDue');
        }catch(e){}
      }
      (function(){
        if (!window.__DUE_NODE_WRAP2__ && typeof window.addNodeForTask === 'function'){
          window.__DUE_NODE_WRAP2__ = true;
          var old = window.addNodeForTask;
          window.addNodeForTask = function(task, cx, cy, opts){
            var n = old.apply(this, arguments);
            try{ ensureDueBadgeTop(n, task); }catch(_){}
            return n;
          };
        }
      })();
      function runAll(){ try{ var nodes=document.querySelectorAll('.node'); for (var i=0;i<nodes.length;i++) ensureDueBadgeTop(nodes[i], null); }catch(_){}}  
      document.addEventListener('twdata', function(){ setTimeout(runAll, 0); });
      window.addEventListener('load', function(){ setTimeout(runAll, 60); });
      var oldRe = window.recomputeAreasAndTags;
      if (typeof oldRe === 'function'){
        window.recomputeAreasAndTags = function(){
          var r = oldRe.apply(this, arguments);
          try{ runAll(); }catch(_){}
          return r;
        };
      }
    })();</script><script id="FEATURE_UNIFIED_ACTIONS_V1">(function(){
  if (window.__FEATURE_UNIFIED_ACTIONS_V1__) return; window.__FEATURE_UNIFIED_ACTIONS_V1__=true;

  // ===== utils =====
  function isNewId(u){ u=String(u||''); return /^new-/.test(u) || /^n-/.test(u); }
  function uuidFromNode(nd){
    if (!nd) return null;
    var u = nd.getAttribute && nd.getAttribute('data-uuid'); if (u) return u;
    var s = nd.getAttribute && nd.getAttribute('data-short'); if (s) return s;
    return null;
  }
  function firstTag(t){
    if (!t || !Array.isArray(t.tags) || !t.tags.length) return "(no tag)";
    return t.tags[0] || "(no tag)";
  }
  function oldTagOf(t){ try{ return (window.INIT_MAIN_TAG && INIT_MAIN_TAG[t.short]) || "(no tag)"; }catch(_){ return "(no tag)"; } }
  function oldProjOf(t){ try{ return (window.INIT_PROJECT && INIT_PROJECT[t.short]) || "(no project)"; }catch(_){ return "(no project)"; } }
  function taskById(id){
    id = String(id||'');
    if (!Array.isArray(window.TASKS)) return null;
    for (var i=0;i<TASKS.length;i++){
      var t = TASKS[i]; if (!t) continue;
      if (String(t.uuid||'')===id) return t;
      if (String(t.short||'')===id) return t;
    }
    return null;
  }
  function genToken(){
    try{ return (Date.now().toString(36)+Math.random().toString(36).slice(2,8)).toLowerCase().replace(/[^a-z0-9]/g,''); }
    catch(_){ return String(Math.random()).slice(2,10); }
  }
  function newIdPair(){ var t=genToken(); return {uuid:'new-'+t, short:'n-'+t}; }

  // ===== ensure unique & synced ids for new tasks =====
  function rekeySync(){
    try{
      var dNew = Array.prototype.slice.call(document.querySelectorAll('.node'))
        .filter(function(nd){ return isNewId(uuidFromNode(nd)); });
      var tNew = Array.isArray(window.TASKS) ? TASKS.filter(function(t){ return isNewId(t && (t.uuid||t.short)); }) : [];
      if (!dNew.length && !tNew.length) return;
      var used = Object.create(null);
      function claim(id){ if (id) used[id]=1; }
      dNew.forEach(function(nd){ claim(uuidFromNode(nd)); });
      tNew.forEach(function(t){ claim(t.uuid); claim(t.short); });
      var n = Math.min(dNew.length, tNew.length);
      for (var i=0;i<n;i++){
        var nd = dNew[i], t = tNew[i];
        var nid = uuidFromNode(nd);
        var tid = String(t.uuid||t.short||'');
        var need = (!isNewId(nid) || !isNewId(tid) || nid!==tid || used[nid]>1 || used[tid]>1);
        if (need){
          var pair, tries=0;
          do{ pair = newIdPair(); tries++; } while((used[pair.uuid] || used[pair.short]) && tries<50);
          nd.setAttribute('data-uuid', pair.uuid);
          nd.setAttribute('data-short', pair.short);
          t.uuid = pair.uuid; t.short = pair.short;
          claim(pair.uuid); claim(pair.short);
        }
        if (!nd.hasAttribute('data-created-ts')) nd.setAttribute('data-created-ts', String(Date.now()-i));
      }
    }catch(_){}
  }
  setInterval(rekeySync, 320);
  window.addEventListener('load', function(){ setTimeout(rekeySync, 140); });

  // ===== state =====
  var FOLD = window.__FOLD_STATE__ || Object.create(null);  // for new tasks
  window.__FOLD_STATE__ = FOLD;
  var EX_OPS = window.__EXISTING_OPS__ || Object.create(null); // for existing tasks
  window.__EXISTING_OPS__ = EX_OPS;

  function ensureFold(id){
    var t = taskById(id); if (!t) return null;
    return FOLD[t.uuid] || (FOLD[t.uuid] = {extra:[]});
  }
  function ensureOps(id){
    return EX_OPS[id] || (EX_OPS[id] = {done:false, deleted:false, mods:[]});
  }

  // ===== apply modifiers to new tasks =====
  function applyModsToNew(id, modStr){
    var t = taskById(id); if (!t) return;
    var f = ensureFold(id); if (!f) return;
    var toks = String(modStr||'').trim().split(/\s+/);
    for (var i=0;i<toks.length;i++){
      var tk = toks[i]; if (!tk) continue;
      if (tk[0]==='+'){
        var tag = tk.slice(1);
        if (tag && tag!=='(no tag)'){
          t.tags = Array.isArray(t.tags) ? t.tags : [];
          if (t.tags.indexOf(tag)===-1) t.tags.push(tag);
        }
        continue;
      }
      if (tk[0]==='-'){
        var tag2 = tk.slice(1);
        if (Array.isArray(t.tags)){ t.tags = t.tags.filter(function(x){ return x!==tag2; }); }
        continue;
      }
      var kv = /^([a-z0-9_.-]+):(.*)$/i.exec(tk);
      if (kv){
        var k=kv[1].toLowerCase(), v=kv[2];
        if (k==='project'){ t.project = v || '(no project)'; f.project = t.project; }
        else if (k==='due'){ t.due = v; f.due = v; }
        else { f.extra.push(k+':'+v); }
      } else {
        f.extra.push(tk);
      }
    }
  }

  // ===== button detection =====
  function isModBtn(el){
    return !!(el && (el.closest('.btnMod')
      || el.closest('[data-action="modify"]')
      || el.closest('[title*="odif"]')
      || el.closest('[aria-label*="odif"]')));
  }
  function isDoneBtn(el){
    return !!(el && (el.closest('.btnDone')
      || el.closest('[data-action="done"]')
      || el.closest('[title*="omplet"]')
      || el.closest('[aria-label*="omplet"]')));
  }
  function isDelBtn(el){
    return !!(el && (el.closest('.btnDel')
      || el.closest('[data-action="delete"]')
      || el.closest('[title*="elete"]')
      || el.closest('[aria-label*="elete"]')));
  }

  // ===== unified click capture (new + existing) =====
  document.addEventListener('click', function(ev){
    var el = ev.target; if (!el) return;
    if (!(isModBtn(el) || isDoneBtn(el) || isDelBtn(el))) return;
    var nd = el.closest && el.closest('.node'); if (!nd) return;
    var id = uuidFromNode(nd); if (!id) return;

    // Only intercept staging; allow UI to also do its visuals
    ev.stopImmediatePropagation(); ev.preventDefault();

    if (isNewId(id)){
      // NEW TASKS
      if (isModBtn(el)){
        var val = window.prompt('Modifiers (e.g. due:3d +tag -old):','');
        if (typeof val === 'string' && val.trim()){
          applyModsToNew(id, val.trim());
        }
      } else if (isDoneBtn(el)){
        var nowDone = !nd.classList.contains('stagedDone');
        if (nowDone) nd.classList.add('stagedDone'); else nd.classList.remove('stagedDone');
        var f = ensureFold(id); if (f) f.done = nowDone;
      } else if (isDelBtn(el)){
        var nowDel = !nd.classList.contains('stagedDel');
        if (nowDel) nd.classList.add('stagedDel'); else nd.classList.remove('stagedDel');
        var f2 = ensureFold(id); if (f2) f2.deleted = nowDel;
      }
    } else {
      // EXISTING TASKS
      var ops = ensureOps(id);
      if (isModBtn(el)){
        var val2 = window.prompt('Modifiers (e.g., pri:H due:2025-09-20 +tag -oldtag):','');
        if (typeof val2 === 'string' && val2.trim()){
          var add = val2.trim().split(/\s+/).filter(Boolean);
          var seen = Object.create(null), merged = [];
          ops.mods.concat(add).forEach(function(tk){ if (!seen[tk]){ seen[tk]=1; merged.push(tk); } });
          ops.mods = merged;
        }
      } else if (isDoneBtn(el)){
        ops.done = !ops.done; ops.deleted = false;
        // reflect immediately in UI
        nd.classList.toggle('stagedDone', ops.done);
        nd.classList.remove('stagedDel');
      } else if (isDelBtn(el)){
        ops.deleted = !ops.deleted; ops.done = false;
        // reflect immediately in UI
        nd.classList.toggle('stagedDel', ops.deleted);
        nd.classList.remove('stagedDone');
      }

    }

    try{ if (typeof updateConsole==='function') setTimeout(updateConsole, 30); }catch(_){}
  }, true);

  // ===== console builder =====
  function buildConsole(){
    try{
      if (!Array.isArray(window.TASKS)) return "";
      var lines = [];
      for (var i=0;i<TASKS.length;i++){
        var t = TASKS[i]; if (!t) continue;
        var id = t.uuid || t.short;

        if (isNewId(id)){
          // fold new tasks
          var nd = document.querySelector('.node[data-uuid="'+id+'"], .node[data-short="'+id+'"]');
          var done=false, deleted=false;
          if (nd){
            done = nd.classList.contains('stagedDone') || nd.classList.contains('completed') || nd.getAttribute('data-done')==='1';
            deleted = nd.classList.contains('stagedDel') || nd.getAttribute('data-deleted')==='1';
          }
          var f = FOLD[t.uuid] || FOLD[t.short] || {};
          if (f.done) done=true;
          if (f.deleted) deleted=true;
          if (deleted) continue;
          var verb = done ? "task log" : "task add";
          var parts = [verb, (t.desc||"(no description)")];
          var proj = (typeof f.project!=='undefined') ? f.project : (t.project || "(no project)");
          if (proj && proj!=="(no project)") parts.push("project:"+proj);
          var tagset = Object.create(null);
          if (Array.isArray(t.tags)){ for (var k=0;k<t.tags.length;k++){ var tg=t.tags[k]; if (tg && tg!=="(no tag)") tagset[tg]=true; } }
          if (f.tags){ for (var tg in f.tags){ if (f.tags[tg]) tagset[tg]=true; else delete tagset[tg]; } }
          Object.keys(tagset).forEach(function(tg){ parts.push("+"+tg); });
          var due = (typeof f.due!=='undefined') ? f.due : t.due;
          if (due) parts.push("due:"+due);
          if (Array.isArray(f.extra)){ for (var q=0;q<f.extra.length;q++){ parts.push(f.extra[q]); } }
          lines.push(parts.join(" "));
        } else {
          // existing tasks — merge diffs + EX_OPS
          var ex = EX_OPS[id] || {};
          if (ex.deleted){ lines.push("task "+t.uuid+" delete"); continue; }
          if (ex.done){ lines.push("task "+t.uuid+" done"); continue; }
          var oT = oldTagOf(t), nT = firstTag(t);
          var oP = oldProjOf(t), nP = t.project || "(no project)";
          var ops = [];
          if (oT !== nT){
            if (oT !== "(no tag)") ops.push("-"+oT);
            if (nT !== "(no tag)") ops.push("+"+nT);
          }
          var projPart = null;
          if (oP !== nP){ projPart = (nP === "(no project)") ? "project:" : "project:"+nP; }
          var mods = [];
          if (projPart) mods.push(projPart);
          if (ops.length) Array.prototype.push.apply(mods, ops);
          if (ex.mods && ex.mods.length){
            var seen = Object.create(null);
            mods.forEach(function(m){ seen[m]=1; });
            ex.mods.forEach(function(m){ if (!seen[m]){ seen[m]=1; mods.push(m); } });
          }
          if (mods.length){ lines.push(("task "+t.uuid+" modify " + mods.join(" ")).trim()); }
        }
      }
      return lines.join("\\n");
    }catch(_){ return ""; }
  }
  function tick(){
    try{
      var ta = document.getElementById('consoleText');
      if (!ta) return;
      var v = buildConsole();
      if (ta.value !== v) ta.value = v;
    }catch(_){}
  }
  setInterval(tick, 260);
  window.addEventListener('load', function(){ setTimeout(tick, 180); });

})();</script></body>'''

    # --- Dep Handle: embedded authoritative writer (v6) + dedup (v6b) ---
    V6_JS = r'''
<script>
/* === dep handle authoritative v6 ========================================== */
(function(){
  if (window.__depHandleAuthorV6) return;

  function qsa(sel, root){ return (root||document).querySelectorAll(sel); }
  function $(sel, root){ return (root||document).querySelector(sel); }

  // Map ids -> shorts using DOM (works with duplicates)
  function domMaps(){
    var els = qsa('#builderStage [data-short]');
    var shortSet = Object.create(null), uuid2short = Object.create(null);
    for (var i=0;i<els.length;i++){
      var el=els[i], s=el.getAttribute('data-short'), u=el.getAttribute('data-uuid');
      if (s) shortSet[s] = true;
      if (u && s) uuid2short[String(u).toLowerCase()] = s;
    }
    return { shortSet:shortSet, uuid2short:uuid2short };
  }
  function first8(x){ return String(x||'').replace(/[^0-9a-fA-F-]/g,'').slice(0,8); }
  function toShort(id, maps){
    if (!id) return null;
    var idstr = String(id);
    if (maps.shortSet[idstr]) return idstr;
    var low = idstr.toLowerCase();
    if (maps.uuid2short[low]) return maps.uuid2short[low];
    var f8 = first8(idstr);
    return maps.shortSet[f8] ? f8 : null;
  }

  // Build combined edge list in SHORT ids (existing + staged)
  function gatherEdgesShort(){
    var maps = domMaps(), out=[], i, e;
    var ex = window.EXIST_EDGES || [];
    for (i=0;i<ex.length;i++){
      e = ex[i]; if (!e) continue;
      var fs = toShort(e.from, maps), ts = toShort(e.to, maps);
      if (fs && ts) out.push({from:fs, to:ts});
    }
    var st = window.stagedAdd || [];
    for (i=0;i<st.length;i++){
      e = st[i]; if (!e) continue;
      var f2 = toShort(e.from, maps), t2 = toShort(e.to, maps);
      if (f2 && t2) out.push({from:f2, to:t2});
    }
    return out;
  }

  // Topo letters (A..Z wrap)
  function topoLetters(){
    var E = gatherEdgesShort();
    var nodes = Object.create(null), adj = Object.create(null), indeg = Object.create(null);
    var cards = qsa('#builderStage [data-short]'), i, n, u, v;
    for (i=0;i<cards.length;i++){ nodes[cards[i].getAttribute('data-short')] = 1; }
    for (i=0;i<E.length;i++){ nodes[E[i].from]=1; nodes[E[i].to]=1; }
    for (n in nodes){ adj[n]=[]; indeg[n]=0; }
    for (i=0;i<E.length;i++){ u=E[i].from; v=E[i].to; adj[u].push(v); indeg[v]++; }
    var q=[], level=Object.create(null);
    for (n in nodes){ if (!indeg[n]) q.push(n); level[n]=0; }
    while(q.length){
      u=q.shift(); var lu=level[u]||0, a=adj[u]||[];
      for (i=0;i<a.length;i++){
        v=a[i];
        if ((level[v]||0) < lu+1) level[v] = lu+1;
        indeg[v]--; if (!indeg[v]) q.push(v);
      }
    }
    var L=Object.create(null);
    for (n in nodes){ var lv=level[n]||0; L[n] = String.fromCharCode(65 + (lv % 26)); }
    return L;
  }

  // Degree counts per short
  function countsOutIn(){
    var E = gatherEdgesShort();
    var out = Object.create(null), inc = Object.create(null), i, e;
    for (i=0;i<E.length;i++){
      e = E[i];
      out[e.from] = (out[e.from]||0) + 1;
      inc[e.to]   = (inc[e.to]  ||0) + 1;
    }
    return {out:out, inc:inc};
  }

  // Ensure a handle exists inside the card (don’t duplicate if present)
  function ensureHandle(card){
    var h = card.querySelector('.depHandle');
    if (h) return h;
    try{
      h = document.createElement('div');
      h.className = 'depHandle';
      var s = card.getAttribute('data-short'); if (s) h.setAttribute('data-short', s);
      card.appendChild(h);
    }catch(_){}
    return h;
  }

  // Write authoritative text and visibility for all cards
  function writeHandles(){
    var L = topoLetters();
    var C = countsOutIn();
    var cards = qsa('#builderStage [data-short]');
    for (var i=0;i<cards.length;i++){
      var el = cards[i];
      var s  = el.getAttribute('data-short');
      var h  = ensureHandle(el);
      if (!h) continue;

      var base = L[s] || 'A';
      var o = C.out[s] || 0, d = C.inc[s] || 0;
      var next = base + String(o) + "/" + String(d);

      if (h.textContent !== next) h.textContent = next;
      // visible only if participates (has any degree)
      if (o>0 || d>0){ h.classList.add('dep-hasdeps'); }
      else{ h.classList.remove('dep-hasdeps'); }
    }
  }

  // Keep staged overlay paths tagged so pulses & tools can follow
  function tagStagedPaths(){
    var over = document.getElementById('depStagedOverlay');
    if (!over) return;
    var paths = over.querySelectorAll('path');
    var st = window.stagedAdd || [];
    for (var i=0;i<paths.length && i<st.length; i++){
      var p = paths[i], e = st[i]; if (!e) continue;
      if (!p.hasAttribute('data-from')) p.setAttribute('data-from', String(e.from||''));
      if (!p.hasAttribute('data-to'))   p.setAttribute('data-to',   String(e.to||''));
    }
  }

  // Wire up: after native refresh/draw, we write authoritative handles
  (function(){
    var _refresh = window.refreshDepHandleLetters;
    window.refreshDepHandleLetters = function(){
      if (typeof _refresh === 'function') try{ _refresh.apply(this, arguments); }catch(_){}
      setTimeout(function(){ try{ writeHandles(); }catch(_){ } }, 0);
    };
  })();

  (function(){
    var _draw = window.drawLinks;
    window.drawLinks = function(){
      if (typeof _draw === 'function') try{ _draw.apply(this, arguments); }catch(_){}
      try{ tagStagedPaths(); }catch(_){}
      // write after overlay settles
      setTimeout(function(){ try{ writeHandles(); }catch(_){ } }, 0);
    };
  })();

  // stagedAdd changes
  (function(){
    try{
      if (!('stagedAdd' in window)) window.stagedAdd = [];
      var a = window.stagedAdd;
      if (!a.__authorV6){
        var _p=a.push, _s=a.splice;
        a.push = function(e){ var r=_p.apply(this, arguments); setTimeout(function(){ try{ writeHandles(); }catch(_){ } }, 0); return r; };
        a.splice = function(){ var r=_s.apply(this, arguments); setTimeout(function(){ try{ writeHandles(); }catch(_){ } }, 0); return r; };
        a.__authorV6 = true;
      }
    }catch(_){}
  })();

  // mutations (style/class/childList) on stage
  (function(){
    var stage = $('#builderStage'); if (!stage) return;
    var t=null;
    var obs = new MutationObserver(function(){
      if (t) return;
      t = setTimeout(function(){ t=null; try{ writeHandles(); }catch(_){ } }, 40);
    });
    obs.observe(stage, {subtree:true, childList:true, attributes:true, attributeFilter:['style','class']});
    window.__depHandleAuthorV6Observer = obs;
  })();

  // resize
  window.addEventListener('resize', function(){ try{ writeHandles(); }catch(_){ } }, {passive:true});

  // initial paints
  setTimeout(function(){ try{ writeHandles(); }catch(_){ } }, 0);
  setTimeout(function(){ try{ writeHandles(); }catch(_){ } }, 120);

  window.__depHandleAuthorV6 = true;
})();
</script>
'''
    V6B_CSS = r'''
/* __DEP_HANDLE_V6B_DEDUP__ hide non-primary instantly (JS removes shortly) */
#builderStage [data-short] .depHandle.__primary { display:inline-flex !important; }
#builderStage [data-short] .depHandle:not(.__primary) { display:none !important; }
'''
    V6B_JS  = r'''
<script>
/* === dep handle authoritative dedup v6b =================================== */
(function(){
  if (window.__depHandleAuthorDedupV6b) return;

  function qsa(sel, root){ return (root||document).querySelectorAll(sel); }
  function $(sel, root){ return (root||document).querySelector(sel); }

  function choosePrimary(list){
    if (!list || !list.length) return null;
    if (list.length === 1) return list[0];
    // prefer one marked participating
    for (var i=0;i<list.length;i++){
      var h=list[i]; if (h.classList && h.classList.contains('dep-hasdeps')) return h;
    }
    // else longest text (usually includes full counts)
    var best=list[0], maxLen=(String(list[0].textContent||'').length|0);
    for (var j=1;j<list.length;j++){
      var len=(String(list[j].textContent||'').length|0);
      if (len>maxLen){ best=list[j]; maxLen=len; }
    }
    return best;
  }

  // Normalize to exactly one "A12/3"
  function sanitizeOne(txt){
    txt = String(txt||'').trim();
    // pick *first* leading letter (A..Z) if any
    var lead = (txt.match(/[A-Z]/) || [""])[0];
    // pick the *last* trailing counts pattern (d+ or d+/d+)
    var counts = (txt.match(/\d+(?:\/\d+)?(?!.*\d)/) || [""])[0];
    return (lead||"") + (counts ? counts : (lead ? "0/0" : ""));
  }

  function dedupOneCard(card){
    var hs = card.querySelectorAll('.depHandle');
    if (!hs || hs.length===0) return;
    // mark all non-primary for CSS hiding; set one primary
    var primary = choosePrimary(hs) || hs[0];
    for (var i=0;i<hs.length;i++){
      var h = hs[i];
      if (h === primary) h.classList.add('__primary');
      else h.classList.remove('__primary');
    }
    // sanitize text on primary
    var norm = sanitizeOne(primary.textContent);
    if (primary.textContent !== norm) primary.textContent = norm;
    // remove extras
    for (var j=0;j<hs.length;j++){
      var h2 = hs[j];
      if (h2 === primary) continue;
      try { h2.remove(); } catch(_){}
    }
  }

  function runDedup(){
    var cards = qsa('#builderStage [data-short]');
    for (var i=0;i<cards.length;i++) dedupOneCard(cards[i]);
  }

  // hook: if v6 writer exists, run dedup after it writes
  (function(){
    // detect v6 by presence of the observer symbol or writer wrapper
    var _refresh = window.refreshDepHandleLetters;
    window.refreshDepHandleLetters = function(){
      if (typeof _refresh === 'function') try{ _refresh.apply(this, arguments); }catch(_){}
      setTimeout(function(){ try{ runDedup(); }catch(_){ } }, 0);
    };
  })();

  // observe the stage for late insertions/mutations
  (function(){
    var stage = $('#builderStage'); if (!stage) return;
    var t=null;
    var obs = new MutationObserver(function(){
      if (t) return;
      t = setTimeout(function(){ t=null; try{ runDedup(); }catch(_){ } }, 30);
    });
    obs.observe(stage, {subtree:true, childList:true, attributes:true, attributeFilter:['class','style']});
    window.__depHandleAuthorDedupV6bObserver = obs;
  })();

  // resize can cause reinserts
  window.addEventListener('resize', function(){ try{ runDedup(); }catch(_){ } }, {passive:true});

  // first passes
  setTimeout(function(){ try{ runDedup(); }catch(_){ } }, 0);
  setTimeout(function(){ try{ runDedup(); }catch(_){ } }, 120);

  // manual helper
  window.depFix = window.depFix || {};
  window.depFix.dedup = runDedup;

  window.__depHandleAuthorDedupV6b = true;
})();
</script>
'''



    # Inject the CSS/JS into the generated html
    if "feature-hover-css" not in html:
        html = html.replace("</head>", CSS_HOVER + "</head>")
    if "FEATURE_HOVERSTAGE" not in html:
        html = html.replace("</body>", JS_HOVER + "</body>")
    if "feature-due-css-v2" not in html:
        html = html.replace("</head>", CSS_DUE + "</head>")
    if "FEATURE_DUEBADGE2" not in html:
        html = html.replace("</body>", JS_DUE + "</body>")
    # --- Integrate dep-handle authoritative writer (v6) + dedup (v6b) ---
    if "dep handle authoritative v6" not in html:
        html = html.replace("</body>", V6_JS + "</body>")
    if "__DEP_HANDLE_V6B_DEDUP__" not in html and "dep handle authoritative dedup v6b" not in html:
        # CSS
        if "</head>" in html:
            html = html.replace("</head>", "<style>" + V6B_CSS + "</style></head>")
        else:
            html = "<style>" + V6B_CSS + "</style>" + html
        # JS
        html = html.replace("</body>", V6B_JS + "</body>")
    # after you finish assembling `html`:
    if "__ENERGY_ARROW_CSS__" not in html:
        html = re.sub(r'</head\s*>', lambda m: ENERGY_ARROW_CSS + '\n' + m.group(0), html, count=1, flags=re.I) \
            if re.search(r'</head\s*>', html, flags=re.I) else ENERGY_ARROW_CSS + html

    if "__ENERGY_ARROW_JS__" not in html:
        html = re.sub(r'</body\s*>', lambda m: ENERGY_ARROW_JS + '\n' + m.group(0), html, count=1, flags=re.I) \
            if re.search(r'</body\s*>', html, flags=re.I) else html + '\n' + ENERGY_ARROW_JS


    if "<!-- INLINE_PAYLOAD_HERE -->" in html:
            eprint("[TaskCanvas] ERROR: placeholder was not replaced in HTML")
    else:
        eprint(f"[TaskCanvas] Embedded tasks: {len(tasks_all)}")

    
    html = inject_wire_deps_as_main(html)
    html = _append_remove_mode(html) 
    html = inject_hover_console_features(html)
    html = inject_multiline_add(html)
    html = inject_newtask_console_sync(html)
    html = inject_console_hotkey_patch(html)
    html = inject_staged_deps_color_split(html)
    html = inject_follow_edges_on_move(html)
    html = inject_actionable_beacon(html)

    # Parse bg flags out of the leftover args:
    bg_arg, bg_opacity, args_wo_filter = _extract_bg_args(args_wo_filter)

    bg_path = _find_bg_file(bg_arg)
    if bg_path:
        html = inject_custom_background(html, bg_path, bg_opacity)
        print(f"[TaskCanvas] Using background: {bg_path.name}")
    else:
        eprint("[TaskCanvas] No custom bg found. Put 'taskcanvas-bg.(jpg|png|webp|svg)' next to the script or pass --bg=FILE.")


    
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_HTML}")
    open_file(OUT_HTML)

if __name__ == "__main__":
    main()