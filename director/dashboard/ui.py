"""The Command Bridge UI — one calm, offline, single-file interface.

Redesigned for restraint (comparable to Claude/Codex desktop), away from the
earlier "command center". Same substance — projects, command-packet
decisions, conviction/verifier/coherence steering — but quiet: a thin project
rail, one focused conversation column, hairline separators, generous
whitespace, and dense metadata demoted to a single muted line with
progressive disclosure. No build step, no CDN, no framework, no external URL
(enforced by test) — vanilla JS + CSS over the same dual-use JSON API.
"""

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Director</title>
<style>
:root{
  --bg:#06080e; --rail:#080b13; --surface:#0d1422; --surface2:#142036;
  --line:#1b2942; --line2:#284064;
  --ink:#e9f1ff; --dim:#9db1d2; --faint:#728aac;
  --accent:#37e0f5; --accent-dim:#17a7c4;        /* electric cyan */
  --ok:#37f5a6; --warn:#ffc24a; --bad:#ff4d6e; --info:#5fa8ff;
  --pivot:#c77bff;
  --r:10px;
  --lamp:rgba(55,224,245,.10);                   /* cool neon ambient */
  --glow:rgba(55,224,245,.55);                   /* cyan bloom */
  --ok-glow:rgba(55,245,166,.60); --bad-glow:rgba(255,77,110,.65);
  --ink-on-accent:#04232b; --ink-on-red:#2a0410;
  --mono:"Cascadia Code",ui-monospace,Consolas,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:
    radial-gradient(75% 55% at 12% -8%,rgba(55,224,245,.12),transparent 55%),
    radial-gradient(70% 55% at 98% 108%,rgba(199,123,255,.10),transparent 55%),
    var(--bg);
  color:var(--ink);
  font:14.5px/1.6 -apple-system,"Segoe UI",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;overflow:hidden}
/* faint CRT scanlines — a clean neon-glass hint, not grain (CSS gradient only) */
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:60;
  opacity:.4;background-image:repeating-linear-gradient(0deg,rgba(0,0,0,.16) 0 1px,transparent 1px 3px)}
.mono{font-family:"Cascadia Code",ui-monospace,Consolas,monospace}
button{font:inherit;cursor:pointer;border:1px solid var(--line2);
  background:transparent;color:var(--ink);border-radius:8px;padding:7px 13px;
  transition:.12s}
button:hover{border-color:var(--faint);background:var(--surface2)}
button.primary{background:var(--accent);border-color:var(--accent);
  color:var(--ink-on-accent);font-weight:600;box-shadow:0 0 16px -4px var(--glow)}
button.primary:hover{background:var(--accent-dim);border-color:var(--accent-dim);
  box-shadow:0 0 24px -3px var(--glow)}
button.primary:active{transform:translateY(1px)}
button:disabled{opacity:.4;cursor:default}
button.ghost{border-color:transparent;color:var(--dim);padding:6px 9px}
button.ghost:hover{color:var(--ink);background:var(--surface2)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;
  background:var(--faint);flex:none}
.dot.ok{background:var(--ok)} .dot.warn{background:var(--warn)}
.dot.bad{background:var(--bad)} .dot.info{background:var(--info)}
/* a11y: screen-reader-only text + a visible keyboard focus ring (clay, only on
   keyboard focus so mouse clicks stay ringless) */
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
  overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.opt:focus-visible{outline-offset:-2px}

#app{height:100%;display:grid;grid-template-columns:248px 1fr}

/* ── rail ── */
.rail{background:linear-gradient(90deg,#05070d,var(--rail) 60%);
  border-right:1px solid var(--line);box-shadow:inset -1px 0 0 rgba(55,224,245,.10);
  display:flex;flex-direction:column;min-height:0}
.rail .brand{padding:18px 18px 12px;font-weight:700;letter-spacing:.3px;
  font-size:15px;display:flex;align-items:center;gap:8px}
.rail .brand small{color:var(--faint);font-weight:500;font-size:11px;
  letter-spacing:.5px}
.rail .lbl{padding:10px 18px 6px;font-size:11px;letter-spacing:.6px;
  text-transform:uppercase;color:var(--faint)}
.rail .list{flex:1;overflow:auto;padding:0 8px}
.proj{display:flex;align-items:center;gap:10px;padding:9px 10px;
  border-radius:8px;cursor:pointer;color:var(--dim);
  border-left:3px solid transparent;transition:.12s}
.proj:hover{background:var(--surface)}
.proj.active{background:var(--surface2);color:var(--ink);
  box-shadow:inset 0 0 0 1px rgba(55,224,245,.25),0 0 14px -3px var(--glow)}
.proj .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;font-size:13.5px}
.proj .ct{font-size:11px;color:var(--faint)}
.rail .foot{padding:10px 12px;border-top:1px solid var(--line)}
.rail .foot button{width:100%;justify-content:center}
.rail .be{padding:8px 18px;font-size:11px;color:var(--faint);
  border-top:1px solid var(--line)}

/* ── main ── */
.main{min-width:0;display:flex;flex-direction:column;min-height:0}
.empty{margin:auto;color:var(--faint);text-align:center}
.head{display:flex;align-items:center;gap:12px;padding:16px 28px;
  background:linear-gradient(180deg,rgba(55,224,245,.05),transparent 70%),var(--surface);
  border-bottom:1px solid var(--line);box-shadow:0 1px 0 rgba(55,224,245,.12)}
.head .t{font-size:16px;font-weight:650}
.head .sub{font-size:12.5px;color:var(--dim);margin-top:1px}
.head .sp{flex:1}
.head .acts{display:flex;gap:6px}

.scroll{flex:1;overflow:auto}
.col{max-width:740px;margin:0 auto;padding:26px 28px 40px}

/* messages */
.msg{margin-bottom:22px}
.msg .who{font-size:11.5px;letter-spacing:.4px;color:var(--faint);
  margin-bottom:5px;text-transform:uppercase;display:flex;align-items:center;
  gap:7px}
.msg.you .who{color:var(--accent-dim)}
.head .persona{color:var(--accent-dim)}
.msg .body{white-space:pre-wrap;word-break:break-word;color:var(--ink)}
.msg.you .body{color:var(--dim)}
.msg.sys .body{color:var(--faint);font-size:13px}

/* decision card */
/* the decision card = a backlit glass panel: translucent surface, crisp cyan rim
   glow + soft bloom, lifted on a deep drop shadow */
.decision{border:1px solid var(--line2);border-radius:var(--r);
  background:linear-gradient(180deg,rgba(20,32,54,.72),rgba(13,20,34,.74));
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 0 0 1px rgba(55,224,245,.10),
    0 18px 42px -16px rgba(0,0,0,.85),0 0 34px -12px var(--glow);
  overflow:hidden;margin:6px 0 4px}
.decision .dh{padding:16px 18px 4px}
.decision .lead{font-size:11.5px;letter-spacing:.6px;color:var(--accent);
  font-family:var(--mono);text-shadow:0 0 9px rgba(55,224,245,.45);
  text-transform:uppercase;margin-bottom:7px;display:flex;align-items:center;
  gap:8px}
.decision .q{font-size:16px;font-weight:650;line-height:1.4}
.decision .ctx{color:var(--dim);font-size:13.5px;margin-top:8px;
  white-space:pre-wrap}
.opts{padding:10px 14px 4px;display:flex;flex-direction:column;gap:2px}
/* CRPG dialogue table: keycap · conviction-spine · content · outcome */
.opt{border-radius:9px;padding:10px 12px;cursor:pointer;
  display:grid;grid-template-columns:24px 4px 1fr 96px;gap:11px;
  align-items:center;transition:.1s;border-left:2px solid transparent}
/* narrow viewports: drop the fixed 96px outcome track and restack it under the
   content (left-aligned) so the numeric hero never clips at the right edge */
@media (max-width:1040px){
  .opt{grid-template-columns:24px 4px 1fr}
  .opt .outcome{grid-column:3;justify-self:start;text-align:left;
    align-items:flex-start;margin-top:4px;min-width:0}
}
.opt:hover{background:var(--surface2);transform:translateY(-1px)}
.opt.rec{border-left-color:var(--line2)}
/* selected = the row lit from its left edge (neon, not debossed) */
.opt.sel,.opt.sel.rec{background:var(--surface2);border-left-color:var(--accent);
  box-shadow:inset 0 0 0 1px rgba(55,224,245,.16),inset 14px 0 22px -16px var(--glow)}
.opt .k{width:24px;height:24px;border-radius:6px;display:grid;place-items:center;
  font-size:11.5px;font-weight:600;color:var(--dim);border:1px solid var(--line2);
  font-family:var(--mono);background:rgba(55,224,245,.04)}
.opt.sel .k{background:var(--accent);color:var(--ink-on-accent);
  border-color:var(--accent);box-shadow:0 0 12px -2px var(--glow)}
/* conviction spine = a glowing neon bar; color->meaning unchanged */
.spine{width:4px;align-self:stretch;border-radius:2px;background:var(--line2)}
.spine.dogmatic{background:var(--info);box-shadow:0 0 9px -1px var(--info)}
.spine.iconoclast{background:var(--accent);box-shadow:0 0 9px -1px var(--accent)}
.spine.heretic{background:var(--pivot);box-shadow:0 0 9px -1px var(--pivot)}
.opt .cvw{font-size:11px;letter-spacing:.5px;text-transform:uppercase;
  color:var(--faint);margin-bottom:2px}
.opt .lab{font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.opt .star{color:var(--accent);font-size:11.5px;font-weight:600}
.opt .desc{color:var(--dim);font-size:13px;margin-top:2px}
.opt .risk{font-size:11.5px;color:var(--warn);margin-top:3px}
/* the outcome as a NEON CHIP, luminance-ranked so ground truth glows brightest:
   VERIFIED (green, filled + glow + under-rule) > TRUSTED (amber outline) > judged
   (flat, no glow) > none (faint). tampered is the red neon bar (styled in JS). */
.outcome{text-align:right;justify-self:end;line-height:1.1}
.outcome .kick{font-size:11px;letter-spacing:.8px;text-transform:uppercase;
  color:var(--faint);display:block;margin-bottom:2px}
.outcome .num{font:600 22px/1 var(--mono);
  font-variant-numeric:tabular-nums;display:inline-block}
/* VERIFIED — the brightest, only-green, only-under-ruled, glowing chip */
.outcome.verified{display:inline-block;border:1px solid var(--ok);border-radius:7px;
  padding:3px 9px 4px;background:rgba(55,245,166,.08);
  box-shadow:0 0 16px -3px var(--ok-glow),inset 0 0 14px -8px var(--ok-glow);
  animation:vglow 1.2s ease-out 1}
.outcome.verified .kick{color:var(--ok);font-family:var(--mono)}
.outcome.verified .num{color:var(--ok);border-bottom:2px solid var(--ok);
  padding-bottom:2px;text-shadow:0 0 9px var(--ok-glow)}
/* TRUSTED/partial — amber neon OUTLINE chip, dimmer, no under-rule */
.outcome.partial{display:inline-block;border:1px solid var(--warn);border-radius:7px;
  padding:3px 9px 4px;background:rgba(255,194,74,.05)}
.outcome.partial .kick{color:var(--warn);font-family:var(--mono)}
.outcome.partial .num{color:var(--warn);font-size:18px;
  text-shadow:0 0 8px rgba(255,194,74,.4)}
/* judged — flat, cool, NO glow (opinion mustn't catch the light) */
.outcome.judged{display:inline-block}
.outcome.judged .kick{color:var(--warn)}
.outcome.judged .num{color:var(--dim);font-weight:500}
.outcome.none{color:var(--faint);font-size:18px;opacity:.7}
.outcome .oracle{display:block;font-size:10px;color:var(--faint);margin-top:4px;
  background:none;border:none;cursor:pointer;padding:0}
.outcome .oracle:hover{color:var(--accent)}
/* one-shot neon bloom when a VERIFIED chip renders */
@keyframes vglow{0%{box-shadow:0 0 0 0 var(--ok-glow)}
  45%{box-shadow:0 0 28px 3px var(--ok-glow),inset 0 0 16px -6px var(--ok-glow)}
  100%{box-shadow:0 0 16px -3px var(--ok-glow),inset 0 0 14px -8px var(--ok-glow)}}
@media (prefers-reduced-motion:reduce){
  .outcome.verified{animation:none}
  .opt:hover{transform:none}
  .drawer{transition:none} #toast{transition:none}
  button.primary:active{transform:none}}
.cardfoot{padding:0 16px 12px}
.cardfoot button{background:none;border:none;color:var(--faint);font-size:12.5px;
  padding:0;cursor:pointer}
.cardfoot button:hover{color:var(--info)}

.composer{border-top:1px solid var(--line);padding:14px 28px}
/* live generation pane — visually SEPARATE from verified artifacts/decisions;
   honestly labeled generation (not reasoning). thinking-delta styling is the
   reserved-but-dormant upgrade seam (claude_cli never emits it). */
.livegen{border-top:1px solid var(--line2);background:rgba(55,224,245,.04);
  padding:10px 28px;max-height:200px;overflow:auto}
.livegen .lgh{font-size:11.5px;letter-spacing:.5px;text-transform:uppercase;
  color:var(--accent-dim);display:flex;flex-direction:column;gap:2px}
.livegen .lgsub{text-transform:none;letter-spacing:0;color:var(--faint);
  font-size:11px}
.livegen .lgbody{white-space:pre-wrap;word-break:break-word;color:var(--dim);
  font-size:12.5px;margin:6px 0 0}
.livegen .think{color:var(--pivot)}     /* dormant: reserved thinking_delta tier */
.cin{max-width:740px;margin:0 auto;display:flex;gap:9px;align-items:center}
.cin input{flex:1;background:var(--surface);border:1px solid var(--line2);
  color:var(--ink);border-radius:10px;padding:11px 14px;font:inherit;
  box-shadow:inset 0 2px 4px rgba(0,0,0,.45)}
.cin input:focus{outline:none;border-color:var(--accent);
  box-shadow:inset 0 2px 4px rgba(0,0,0,.4),0 0 0 2px rgba(55,224,245,.35),0 0 18px -6px var(--glow)}
.subacts{max-width:740px;margin:7px auto 0;display:flex;gap:14px;
  font-size:12px;color:var(--faint)}
.subacts button{background:none;border:none;color:var(--faint);padding:0;
  font-size:12px}
.subacts button:hover{color:var(--ink);background:none}
.idle-acts{max-width:740px;margin:0 auto;display:flex;gap:9px;align-items:center}
.idle-acts .hint{color:var(--faint);font-size:12.5px;margin-left:4px}

/* details drawer */
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(420px,90vw);
  background:linear-gradient(180deg,rgba(13,20,34,.94),rgba(8,11,19,.94));
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border-left:1px solid var(--line2);
  transform:translateX(100%);transition:transform .2s,visibility 0s .2s;
  visibility:hidden;z-index:20;overflow:auto;padding:18px 20px}
.drawer.show{transform:none;visibility:visible;transition:transform .2s;
  box-shadow:-24px 0 60px rgba(0,0,0,.7),-1px 0 0 var(--glow)}
.drawer .dx{position:absolute;top:14px;right:16px}
.drawer h4{font-size:11px;letter-spacing:.7px;text-transform:uppercase;
  font-family:var(--mono);
  color:var(--faint);margin:18px 0 8px}
.drawer .disp{color:var(--ink);font-size:13.5px;line-height:1.5}
.drawer .rank{display:inline-block;margin-top:6px;font-size:11.5px;
  color:var(--accent);border:1px solid var(--accent-dim);border-radius:999px;
  padding:1px 9px;font-family:var(--mono);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.row{display:flex;gap:9px;align-items:baseline;padding:6px 0;
  border-bottom:1px dashed var(--line);font-size:13px}
.row:last-child{border-bottom:none}
.row .g{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.row .st{font-size:11px;color:var(--faint)}
.lk{background:none;border:none;color:var(--info);padding:0;cursor:pointer;
  font-size:12.5px;text-align:left}
.lk:hover{text-decoration:underline;background:none}
.stats{display:flex;gap:18px;margin:6px 0 2px;color:var(--dim);font-size:13px}
.stats b{color:var(--ink);font-weight:650}

/* modal + toast */
.modal{position:fixed;inset:0;background:rgba(2,4,8,.62);display:none;
  backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);
  align-items:center;justify-content:center;z-index:40}
.modal.show{display:flex}
.sheet{background:linear-gradient(180deg,rgba(20,32,54,.94),rgba(13,20,34,.95));
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  border:1px solid var(--line2);
  box-shadow:0 0 0 1px rgba(55,224,245,.10),0 30px 80px -20px rgba(0,0,0,.85),0 0 44px -16px var(--glow);
  border-radius:12px;width:min(820px,92vw);max-height:84vh;overflow:auto}
.sheet .sh{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;
  gap:10px;align-items:center;position:sticky;top:0;background:var(--surface)}
.sheet .sh .t{font-weight:600}.sheet .sh .sp{flex:1}
.sheet pre{margin:0;padding:18px;white-space:pre-wrap;word-break:break-word;
  font-size:12.5px;color:var(--dim)}
#toast{position:fixed;bottom:84px;left:50%;transform:translateX(-50%);
  background:var(--surface2);border:1px solid var(--line2);border-radius:9px;
  padding:9px 16px;font-size:13px;opacity:0;transition:.2s;z-index:50;
  pointer-events:none;box-shadow:0 0 22px -6px var(--glow)}
#toast.show{opacity:1}
#toast.err{border-color:var(--bad);color:#ffd2da;box-shadow:0 0 22px -5px var(--bad-glow)}
.newform{max-width:520px;margin:8vh auto 0;display:flex;flex-direction:column;
  gap:11px}
.newform h2{font-weight:650;font-size:18px;margin:0 0 4px}
.newform input,.newform textarea{background:var(--surface);
  border:1px solid var(--line2);color:var(--ink);border-radius:9px;
  padding:11px 13px;font:inherit}
.newform textarea{min-height:96px;resize:vertical}
</style>
</head>
<body>
<div id="app">
  <div class="rail">
    <div class="brand">Director <small id="be" aria-live="polite"></small></div>
    <div class="lbl" id="projlbl">Projects</div>
    <div class="list" id="projlist" role="listbox" aria-labelledby="projlbl"></div>
    <div class="foot"><button id="newbtn" onclick="showNew()">+ New project</button></div>
    <div class="be" id="backend">—</div>
  </div>
  <div class="main" id="main">
    <div class="empty">Select a project.</div>
  </div>
</div>
<div class="drawer" id="drawer" role="dialog" aria-modal="true"
  aria-label="Project details"></div>
<div class="modal" id="modal"><div class="sheet" role="dialog" aria-modal="true"
  aria-labelledby="m-title">
  <div class="sh"><span class="t" id="m-title"></span><span class="sp"></span>
    <button class="ghost" onclick="closeModal()">Close</button></div>
  <pre id="m-body" class="mono"></pre></div></div>
<div id="toast"></div>
<div id="live" class="sr-only" aria-live="polite" aria-atomic="true"></div>
<div id="alert" class="sr-only" role="alert" aria-atomic="true"></div>

<script>
const $=s=>document.querySelector(s), api="/api";
let CUR=null, OV=null, DG=null, JN=[], sel={}, pendingNew=false, lastRunning=false;
let CUR_UPDATED=null;   // updated_at of the open project at last render (live-refresh guard)
let focusedPacket=null; // which packet we've already focused/announced (no re-steal)
let lastFocus=null;     // element to restore focus to when a dialog closes

async function jget(u){const r=await fetch(u);const d=await r.json();
  if(!r.ok)throw new Error(d.error||r.status);return d;}
async function jpost(u,b){const r=await fetch(u,{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});
  const d=await r.json();if(!r.ok&&!d.error)throw new Error(r.status);return d;}
function esc(s){return (s==null?"":""+s).replace(/[&<>]/g,
  c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function toast(m,err){const t=$("#toast");t.textContent=m;
  t.className="show"+(err?" err":"");setTimeout(()=>t.className="",2600);
  announce(m,err);}   /* mirror to a live region: errors interrupt (assertive) */
function announce(m,assertive){const el=$(assertive?"#alert":"#live");if(!el)return;
  el.textContent="";setTimeout(()=>{el.textContent=m;},30);}
function tval(x){return (x&&(x.ts||x.created_at||x.answered_at))||"";}
function fmtScore(s){if(s==null||s==="")return"";const n=+s;
  return Number.isFinite(n)?(" "+(n%1?n.toFixed(2):n)):"";}

/* companion avatar — deterministic heraldic emblem from project id only.
   inline SVG via BACKTICKS (a raw newline in a string blanks the page) and
   no namespace attribute (the offline test bans external-URL substrings;
   innerHTML supplies the namespace implicitly). hue from id alone, muted,
   so a column reads as one set; STATUS rides the ring color, never fill. */
const _SIG={};
function _fnv(s){let h=2166136261;for(let i=0;i<(s||"x").length;i++){
  h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return h>>>0;}
function sigil(id,px,ring){
  const key=(id||"x")+"|"+px+"|"+(ring||"");
  if(_SIG[key])return _SIG[key];
  const h=_fnv(id), c=px/2, r=px*0.40, rot=((h>>3)%12)*30, lat=h%6,
    dot=(h>>7)&1, hue=(24+((h%81)-40)+360)%360, fill=`hsl(${hue} 33% 62%)`;
  const pts=(n,rr)=>{let p=[];for(let i=0;i<n;i++){
    const a=(Math.PI*2*i/n)-Math.PI/2+rot*Math.PI/180;
    p.push((c+Math.cos(a)*rr).toFixed(1)+","+(c+Math.sin(a)*rr).toFixed(1));}
    return p.join(" ");};
  const sw=Math.max(1,px*0.07).toFixed(1);
  let sh;
  if(lat===0)sh=`<polygon points="${pts(3,r)}" fill="none" stroke="${fill}" stroke-width="${sw}"/>`;
  else if(lat===1)sh=`<polygon points="${pts(6,r)}" fill="none" stroke="${fill}" stroke-width="${sw}"/>`;
  else if(lat===2)sh=`<polyline points="${pts(3,r)}" fill="none" stroke="${fill}" stroke-width="${sw}" stroke-linejoin="round"/>`;
  else if(lat===3)sh=`<circle cx="${c}" cy="${c}" r="${r.toFixed(1)}" fill="none" stroke="${fill}" stroke-width="${sw}"/><line x1="${(c-r).toFixed(1)}" y1="${c}" x2="${(c+r).toFixed(1)}" y2="${c}" stroke="${fill}" stroke-width="${sw}" transform="rotate(${rot} ${c} ${c})"/>`;
  else if(lat===4)sh=`<line x1="${c}" y1="${(c-r).toFixed(1)}" x2="${c}" y2="${(c+r).toFixed(1)}" stroke="${fill}" stroke-width="${sw}" transform="rotate(${rot} ${c} ${c})"/><line x1="${(c-r).toFixed(1)}" y1="${c}" x2="${(c+r).toFixed(1)}" y2="${c}" stroke="${fill}" stroke-width="${sw}" transform="rotate(${rot} ${c} ${c})"/>`;
  else sh=`<ellipse cx="${c}" cy="${c}" rx="${(r*0.62).toFixed(1)}" ry="${r.toFixed(1)}" fill="none" stroke="${fill}" stroke-width="${sw}" transform="rotate(${rot} ${c} ${c})"/>`;
  const ctr=dot?`<circle cx="${c}" cy="${c}" r="${(px*0.08).toFixed(1)}" fill="${fill}"/>`:"";
  const rg=ring?`<circle cx="${c}" cy="${c}" r="${(px*0.46).toFixed(1)}" fill="none" stroke="${ring}" stroke-width="1.5"/>`:"";
  const svg=`<svg width="${px}" height="${px}" viewBox="0 0 ${px} ${px}" style="flex:none;display:block">${rg}${sh}${ctr}</svg>`;
  _SIG[key]=svg;return svg;
}
const RING={open:"#cf9b7c",finalized:"#6cbf8e",active:"#7fa6cf",idle:"#6a7280"};

/* one canonical TEXT alternative per verification tier — the source of truth for
   both the stamp's aria-label and each option's radio label, so the honesty
   hierarchy reaches screen-reader + colorblind users, not just sighted ones */
function outcomeLabel(o){
  const k=o.check||"none",s=fmtScore(o.check_score).trim();
  if(k==="verified")return "Verified by oracle"+(s?(", score "+s):"")+
    " — ground truth";
  if(k==="verified_partial"){const n=o.sub_claims_verified||0,
    m=o.sub_claims_total||0;
    return "Trusted: "+n+" of "+m+" necessary checks passed — not a full proof";}
  if(k==="judged")return "Judged estimate, no oracle"+(s?(", score "+s):"");
  return "No confidence signal";
}
/* the numeric outcome hero — Verified-N (ground truth) vs Judged-N (guess).
   role=img + aria-label carries the meaning; the bare glyphs are aria-hidden */
function outcomeCell(o){
  const k=o.check||"none",s=fmtScore(o.check_score).trim(),
    lab=esc(outcomeLabel(o));
  if(k==="verified")return `<div class="outcome verified" role="img" aria-label="${lab}"
    title="An external oracle ran and left an artifact backing this score — a real check against ground truth.">
    <span class="kick" aria-hidden="true">Verified</span><span class="num" aria-hidden="true">${s||"✓"}</span>
    ${o.verification_artifact_id?`<button class="oracle" aria-label="View oracle verification artifact" onclick="event.stopPropagation();showArtifact('${o.verification_artifact_id}')"><span aria-hidden="true">✓ oracle</span></button>`:""}</div>`;
  if(k==="verified_partial"){
    const n=o.sub_claims_verified||0,m=o.sub_claims_total||0;
    return `<div class="outcome partial" role="img" aria-label="${lab}"
      title="A TRUSTED necessary-condition checker passed (${n} of ${m}), proven force-to-fail, reference of independent lineage. Necessary conditions only — NOT a truth check. The rest stays Judged.">
      <span class="kick" aria-hidden="true">Trusted</span><span class="num" aria-hidden="true">${n}/${m}</span>
      ${o.verification_artifact_id?`<button class="oracle" aria-label="View trusted-check report" onclick="event.stopPropagation();showArtifact('${o.verification_artifact_id}')"><span aria-hidden="true">checks</span></button>`:""}</div>`;
  }
  if(k==="judged")return `<div class="outcome judged" role="img" aria-label="${lab}"
    title="A model judgement — no ground-truth oracle here. Treat as an estimate.">
    <span class="kick" aria-hidden="true">Judged${o.calibration?" · "+esc(o.calibration):""}</span><span class="num" aria-hidden="true">${s||"~"}</span></div>`;
  return `<div class="outcome none" role="img" aria-label="${lab}" title="No confidence signal."><span aria-hidden="true">—</span></div>`;
}

/* verification health: trusted partial-verified deliverables + the tamper-state
   of their signed reports (an INVALID report = a persisted snapshot was edited) */
function vhealth(ig){
  if(!ig) return "";
  const r=ig.reports||{}, viol=ig.violations||0, pd=ig.partial_deliverables||0,
    okn=r.ok||0;
  const note = viol>0
    ? `<span role="alert" aria-label="Warning: ${viol} signed report${viol>1?"s":""} failed verification — the snapshot was edited outside the engine and can no longer be trusted" style="background:var(--bad);color:var(--ink-on-red);font-family:var(--mono);text-transform:uppercase;font-weight:700;padding:1px 6px;border-radius:2px;display:inline-block;transform:rotate(-.5deg);box-shadow:0 0 10px var(--bad-glow)"><span aria-hidden="true">⚠ ${viol} tampered report${viol>1?"s":""}</span></span>`
    : `<span aria-label="${okn} signed report${okn===1?"":"s"} intact" style="color:var(--faint)">${okn} signed report${okn===1?"":"s"} intact</span>`;
  return `<h4>Verification health</h4>
    <div style="font-size:11.5px;color:var(--dim);line-height:1.5" title="Trusted partial-verified deliverables and the tamper-state of their signed reports. NECESSARY-condition checks, not full proof.">⊨ <b>${pd}</b> trusted deliverable${pd===1?"":"s"} · ${note}</div>`;
}

/* the honesty ladder as a live readout: how the options ON THE TABLE NOW
   distribute across verification tiers (oracle > trusted > judged > none) */
function ladderLine(L){
  if(!L) return "";
  const total=(L.verified||0)+(L.verified_partial||0)+(L.judged||0)+(L.none||0);
  if(!total) return "";
  const seg=(n,c,lbl)=>n?`<span style="color:${c}">${n} ${lbl}</span>`:"";
  const parts=[seg(L.verified,"var(--ok)","verified"),
    seg(L.verified_partial,"var(--warn)","trusted"),
    seg(L.judged,"var(--dim)","judged"),
    seg(L.none,"var(--faint)","none")].filter(Boolean);
  return `<h4>Decision evidence</h4>
    <div style="font-size:11.5px;line-height:1.5" title="Live decisions by honest tier: VERIFIED (an oracle ran) > TRUSTED (necessary checks proven) > judged (model opinion) > none.">${parts.join(" · ")}</div>`;
}

/* a refresh is safe only when it can't clobber an in-progress decision:
   no option selected-but-uncommitted, and the user isn't typing a rationale */
function safeRefresh(){
  if(document.querySelector(".opt.sel"))return false;
  const ae=document.activeElement;
  if(ae&&(ae.tagName==="INPUT"||ae.tagName==="TEXTAREA"))return false;
  return true;
}

/* ── overview / rail ── */
async function loadOverview(){
  OV=await jget(api+"/overview");
  $("#backend").textContent="backend · "+OV.backend;
  // live: if the OPEN project changed underneath us (another operator decided/
  // advanced it via the dual-use API), re-render it — but never mid-decision
  if(CUR && !lastRunning){
    const row=(OV.projects||[]).find(p=>p.id===CUR);
    if(row && row.updated_at && CUR_UPDATED &&
       row.updated_at!==CUR_UPDATED && safeRefresh()){
      loadProject();
    }
  }
  const L=$("#projlist");L.innerHTML="";
  (OV.projects||[]).forEach(p=>{
    const ring=p.open_packets?RING.open:(p.status==="finalized"?RING.finalized:
      (p.status==="active"?RING.active:RING.idle));
    const status=p.open_packets?"decision waiting":(p.status||"idle");
    const d=document.createElement("div");
    d.className="proj"+(p.id===CUR?" active":"");
    d.style.borderLeftColor=ring;   /* status-colored file-tab stub */
    d.setAttribute("role","option");
    d.tabIndex=0;
    d.setAttribute("aria-label",p.name+", "+status);
    if(p.id===CUR)d.setAttribute("aria-current","true");
    d.onclick=()=>openProject(p.id);
    d.onkeydown=ev=>{
      if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();openProject(p.id);}
      else if(ev.key==="ArrowDown"||ev.key==="ArrowUp"){ev.preventDefault();
        const sibs=[...L.children],i=sibs.indexOf(d);
        const nx=sibs[(i+(ev.key==="ArrowDown"?1:sibs.length-1))%sibs.length];
        if(nx)nx.focus();}};
    d.innerHTML=`<span aria-hidden="true">${sigil(p.id,20,ring)}</span>
      <span class="nm">${esc(p.name)}</span>
      <span class="ct" aria-hidden="true">${p.open_packets?"•":""}</span>`;
    L.appendChild(d);
  });
  if(CUR&&DG)renderHead();
}

/* ── project view ── */
async function openProject(id){
  CUR=id;
  await loadProject();
  loadOverview();
}
async function loadProject(){
  if(!CUR)return;
  DG=await jget(api+"/project/"+CUR);
  try{JN=await jget(api+"/project/"+CUR+"/journal?n=200");}catch(e){JN=[];}
  renderProject();
  CUR_UPDATED=DG&&DG.updated_at||CUR_UPDATED;   // mark the rev we've rendered
}
function statusLine(d){
  const s=d.summary||{},bs=s.tasks_by_status||{};
  const open=(d.packets||[]).filter(p=>p.status==="presented").length;
  const bits=[`${s.done||0}/${s.tasks_total||0} done`];
  if(bs.running)bits.push(`${bs.running} running`);
  if(s.blocked)bits.push(`${s.blocked} blocked`);
  if(open)bits.push(`${open} decision${open>1?"s":""} waiting`);
  return bits.join(" · ");
}
function personaLine(d){
  const rk=d.conviction_rank||{};
  if(!rk.rank)return"";
  const read=(d.conviction_read||"").split("—")[0].trim();   // "Trending Iconoclast"
  return (read||rk.conviction)+" · "+rk.rank_name;
}
function renderProject(){
  const d=DG, persona=personaLine(d);
  $("#main").innerHTML=`
    <div class="head">
      ${sigil(d.id,34)}
      <div><div class="t">${esc(d.name)}</div>
        <div class="sub"><span id="subline">${esc(statusLine(d))}</span>${
        persona?` · <span class="persona">${esc(persona)}</span>`:""}</div></div>
      <div class="sp"></div>
      <div class="acts">
        <button class="ghost" onclick="op('advance')">Advance</button>
        <button class="ghost" onclick="op('finalize')">Finalize</button>
        <button class="ghost" onclick="openDrawer()">Details</button>
      </div>
    </div>
    <div class="scroll"><div class="col" id="thread"></div></div>
    <div id="livegen" class="livegen" hidden>
      <div class="lgh">Live generation
        <span class="lgsub">model output as it's written — not hidden reasoning
        (the subscription backend doesn't expose reasoning)</span></div>
      <pre id="livegen-body" class="lgbody mono"></pre></div>
    <div class="composer" id="composer"></div>`;
  renderThread();renderComposer();
}
function renderHead(){const s=$("#subline");if(s)s.textContent=statusLine(DG);}

const SAY={
  "project.created":"A new project begins.",
  "plan.created":"Plan drawn up — modules, tasks, milestones, and the risks I can foresee.",
  "advance.completed":"Work cycle complete.",
  "delta.applied":"Applied to the plan.",
  "decision.blocked":"That conflicts with current state — held back rather than forced.",
  "milestone.reached":"Milestone reached.",
  "project.finalized":"Deliverable synthesized.",
};
function narr(ev){let b=SAY[ev.type]||ev.summary||ev.type;
  if(SAY[ev.type]&&ev.summary&&!b.includes(ev.summary))b+="\n"+ev.summary;
  return b;}
function buildThread(){
  const msgs=[];
  (JN||[]).forEach(ev=>{if(ev.actor==="human")return;
    msgs.push({who:"dir",t:tval(ev),txt:narr(ev)});});
  const pmap={};(DG.packets||[]).forEach(p=>pmap[p.id]=p);
  (DG.decisions||[]).forEach(dec=>{
    const p=pmap[dec.packet_id]||{};
    const o=(p.options||[]).find(x=>x.key===dec.selected_key);
    const rt=(dec.response_type||"").replace(/_/g," ");
    let line=o?o.label:(dec.selected_key?("Option "+dec.selected_key):
      (rt||"decided"));
    msgs.push({who:"you",t:tval(dec),
      txt:line+(dec.rationale?("\n"+dec.rationale):"")});});
  msgs.sort((a,b)=>(a.t||"").localeCompare(b.t||""));
  return msgs;
}
function renderThread(){
  const open=(DG.packets||[]).filter(p=>p.status==="presented");
  let h="";
  const mark=sigil(DG.id,22)+"<span>Director</span>";
  buildThread().forEach(m=>{
    h+=`<div class="msg ${m.who==="you"?"you":""}">
      <div class="who">${m.who==="you"?"You":mark}</div>
      <div class="body">${esc(m.txt)}</div></div>`;});
  if(!h&&!open.length)h=`<div class="msg"><div class="who">${mark}</div>
    <div class="body">Ready. ${esc((DG.charter||{}).objective||"Give the word.")}</div></div>`;
  if(open.length){
    h+=decisionCard(open[0]);
    if(open.length>1)h+=`<div class="msg sys"><div class="body">
      ${open.length-1} more decision${open.length>2?"s":""} after this.</div></div>`;
  }
  $("#thread").innerHTML=h;
  const sc=$(".scroll");if(sc)sc.scrollTop=sc.scrollHeight;
  /* a NEW decision: announce it, and move focus to the first option (but never
     steal focus mid-typing — safeRefresh guards that) */
  if(open.length){const p0=open[0];
    if(focusedPacket!==p0.id){focusedPacket=p0.id;
      announce("Decision waiting: "+p0.title+", "+(p0.options||[]).length+" options");
      if(safeRefresh()){const f=document.querySelector("#dlg-"+p0.id+" .opt");
        if(f)f.focus();}}
  }else{focusedPacket=null;}
}

const CONV={dogmatic:["Dogmatic","conform to the proven baseline"],
  iconoclast:["Iconoclast","exceed the baseline — reform it"],
  heretic:["Heretic","reject the framing — pivot the problem"]};
function decisionCard(p){
  sel[p.id]=sel[p.id]||p.recommendation_key||(p.options[0]||{}).key;
  const coh=p.coherence;
  const cohDot=coh?`<span class="dot ${coh.issues&&coh.issues.length?"bad":
    (coh.warnings&&coh.warnings.length?"warn":"ok")}" title="coherence ${coh.score}${
    coh.warnings&&coh.warnings.length?": "+esc(coh.warnings.join("; ")):""}"></span>`:"";
  let opts="";
  p.options.forEach((o,i)=>{
    const isSel=o.key===sel[p.id], isRec=o.key===p.recommendation_key;
    const cv=CONV[o.conviction], num=i+1;
    const risk=o.risk_impact==="raised"?`<div class="risk">⚠ risk raised</div>`:"";
    const alabel=esc(`Option ${num}, ${cv?cv[0]:"option"}, ${o.label}; `+
      `${outcomeLabel(o)}${isRec?", recommended":""}`);
    opts+=`<div class="opt${isSel?" sel":""}${isRec?" rec":""}" role="radio"
        tabindex="0" aria-checked="${isSel?"true":"false"}" aria-label="${alabel}"
        data-pid="${p.id}" data-key="${o.key}"
        onclick="pick('${p.id}','${o.key}')" onkeydown="optKey(event,'${p.id}','${o.key}')">
      <div class="k" aria-hidden="true">${num}</div>
      <div class="spine ${o.conviction||""}" aria-hidden="true" title="${cv?esc(cv[1]):""}"></div>
      <div>${cv?`<div class="cvw">${cv[0]}</div>`:""}
        <div class="lab">${esc(o.label)}
          ${isRec?'<span class="star">★ recommended</span>':""}</div>
        ${o.description?`<div class="desc">${esc(o.description)}</div>`:""}${risk}</div>
      ${outcomeCell(o)}</div>`;
  });
  return `<div class="decision" id="dlg-${p.id}">
    <div class="dh"><div class="lead">${sigil(DG.id,20)}
      <span>${esc(DG.name)} · Decision</span> ${cohDot}</div>
      <div class="q">${esc(p.title)}</div>
      ${p.context?`<div class="ctx">${esc(p.context)}</div>`:""}</div>
    <div class="opts" role="radiogroup" aria-label="${esc(p.title)}">${opts}</div>
    <div class="cardfoot"><button onclick="showLegend()">Key</button>
      <button onclick="openDrawerAt('${p.id}')">Details →</button></div>
    </div>`;
}
/* selection = class toggle only, never a thread rebuild (avoids commit races) */
function pick(pid,key){sel[pid]=key;const dlg=document.getElementById("dlg-"+pid);
  if(!dlg){renderThread();return;}
  dlg.querySelectorAll(".opt").forEach(el=>{const on=el.getAttribute("data-key")===key;
    el.classList.toggle("sel",on);el.setAttribute("aria-checked",on?"true":"false");});}
/* radio keys: Space selects, Enter selects+commits, arrows move within the group */
function optKey(e,pid,key){
  if(e.key===" "||e.key==="Spacebar"){e.preventDefault();pick(pid,key);}
  else if(e.key==="Enter"){e.preventDefault();pick(pid,key);decide(pid,"select");}
  else if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();
    const els=[...document.querySelectorAll("#dlg-"+pid+" .opt")];
    const i=els.findIndex(el=>el.getAttribute("data-key")===key);
    const nx=els[(i+(e.key==="ArrowDown"?1:els.length-1))%els.length];
    if(nx){nx.focus();pick(pid,nx.getAttribute("data-key"));}}}

function renderComposer(){
  const open=(DG.packets||[]).filter(p=>p.status==="presented");
  const c=$("#composer");
  if(open.length){
    const p=open[0];
    c.innerHTML=`<div class="cin">
      <input id="rin" aria-label="Your reasoning for this decision (optional)"
        placeholder="Add your reasoning (optional), then commit…"
        onkeydown="if(event.key==='Enter')decide('${p.id}','select')">
      <button class="primary" onclick="decide('${p.id}','select')">Commit</button>
    </div>
    <div class="subacts">
      <button onclick="decide('${p.id}','defer')">Defer</button>
      <button onclick="decide('${p.id}','take_command')">Take command</button>
      <button onclick="decide('${p.id}','reject_all')">Reject all</button>
    </div>`;
  }else{
    c.innerHTML=`<div class="idle-acts">
      <button class="primary" onclick="op('advance')">Advance work</button>
      <button onclick="op('finalize')">Finalize</button>
      <span class="hint">No decision pending.</span></div>`;
  }
}

async function decide(pid,response){
  try{
    const txt=(($("#rin")||{}).value||"").trim();
    const body={packet_id:pid,response,option_key:sel[pid]||"",rationale:txt};
    if(response==="select"&&txt)body.modifications=txt;
    const out=await jpost(api+"/project/"+CUR+"/decide",body);
    if(out.error)toast(out.error,true);
    else toast("Committed — "+(out.coherence||"ok")+(out.applied?"":" (held)"));
    await loadProject();loadOverview();
  }catch(e){toast(""+e.message,true);}
}
/* live generation: open an SSE channel and append GENERATION deltas to the
   honestly-labeled pane. A reserved thinking_delta branch is present but dormant
   — claude_cli never emits it (the upgrade seam for an Anthropic-API backend). */
let liveSrc=null;
function openLiveGen(pid){
  if(liveSrc){try{liveSrc.close();}catch(e){}}
  const pane=$("#livegen"),body=$("#livegen-body");
  if(!pane||!body)return;
  body.textContent="";        // OFF byte-identical at the UI: the pane stays
                              // HIDDEN until a REAL delta arrives, so a gate-off
                              // run (no deltas, only the sentinel) shows nothing.
  try{liveSrc=new EventSource(api+"/project/"+pid+"/stream");}
  catch(e){return;}
  liveSrc.onmessage=ev=>{
    let d;try{d=JSON.parse(ev.data);}catch(_){return;}
    if(d.type==="text_delta"){
      pane.hidden=false;                            /* reveal on first generation */
      body.appendChild(document.createTextNode(d.text||""));
      pane.scrollTop=pane.scrollHeight;
    }else if(d.type==="thinking_delta"){            /* dormant reserved tier */
      pane.hidden=false;
      const s=document.createElement("span");s.className="think";
      s.textContent=d.text||"";body.appendChild(s);
      pane.scrollTop=pane.scrollHeight;
    }else if(d.type==="done"){
      try{liveSrc.close();}catch(_){}
      liveSrc=null;
    }
  };
  liveSrc.onerror=()=>{try{liveSrc.close();}catch(_){}liveSrc=null;};
}
async function op(kind,force){
  try{const out=await jpost(api+"/project/"+CUR+"/"+kind,{force:!!force});
    if(out.error)toast(out.error,true);else toast(kind+" started…");pollOp();
  }catch(e){toast(""+e.message,true);}
}
async function approve(tid){
  try{await jpost(api+"/project/"+CUR+"/approve",{task_id:tid});
    toast("Approved");await loadProject();}catch(e){toast(""+e.message,true);}
}
async function pollOp(){
  try{const o=await jget(api+"/op");const be=$("#be");
    if(o.running){be.textContent="· "+o.kind+" "+(o.elapsed_s|0)+"s";
      lastRunning=true;}
    else{be.textContent="·";
      if(lastRunning){lastRunning=false;
        if(pendingNew&&o.result&&o.result.project){pendingNew=false;
          toast("Project ready");await loadOverview();openProject(o.result.project);return;}
        toast(o.error?("failed: "+o.error):"Cycle complete",!!o.error);
        if(CUR)await loadProject();loadOverview();}}
  }catch(e){}
}

/* details drawer */
let drawerPacket=null;
/* keep Tab inside an open dialog (focus trap) */
function trapKey(e,box){if(e.key!=="Tab")return;
  const f=[...box.querySelectorAll('button,input,textarea,a[href],[tabindex]:not([tabindex="-1"])')]
    .filter(el=>el.offsetParent!==null);
  if(!f.length)return;const a=f[0],z=f[f.length-1];
  if(e.shiftKey&&document.activeElement===a){e.preventDefault();z.focus();}
  else if(!e.shiftKey&&document.activeElement===z){e.preventDefault();a.focus();}}
function openDrawer(){lastFocus=document.activeElement;drawerPacket=null;renderDrawer();
  const dw=$("#drawer");dw.classList.add("show");dw.onkeydown=e=>trapKey(e,dw);
  const c=dw.querySelector(".dx");if(c)c.focus();}
function openDrawerAt(pid){lastFocus=document.activeElement;drawerPacket=pid;renderDrawer();
  const dw=$("#drawer");dw.classList.add("show");dw.onkeydown=e=>trapKey(e,dw);
  const c=dw.querySelector(".dx");if(c)c.focus();}
function closeDrawer(){$("#drawer").classList.remove("show");
  if(lastFocus&&lastFocus.focus)lastFocus.focus();}
function packetDetail(){
  if(!drawerPacket)return"";
  const p=(DG.packets||[]).find(x=>x.id===drawerPacket);
  if(!p)return"";
  let h=`<h4>This decision · ${esc(p.title)}</h4>`;
  p.options.forEach(o=>{
    const tr=(o.tradeoffs||[]).map(t=>`<li>± ${esc(t)}</li>`).join("");
    const co=(o.consequences||[]).map(c=>`<li>→ ${esc(c)}</li>`).join("");
    const dk=Object.keys(o.state_delta||{});
    h+=`<div style="margin:8px 0 10px"><div style="font-weight:600">${esc(o.label)}</div>
      <ul style="margin:4px 0 0;padding-left:16px;color:var(--dim);font-size:12.5px">
      ${tr}${co}${dk.length?`<li style="color:var(--faint)">steers: ${esc(dk.join(", "))}</li>`:""}</ul></div>`;
  });
  return h;
}
function renderDrawer(){
  const d=DG,s=d.summary||{},bs=s.tasks_by_status||{},rk=d.conviction_rank||{};
  let h=`<button class="ghost dx" onclick="closeDrawer()">Close</button>
    ${packetDetail()}
    <h4>Disposition</h4>
    <div class="disp">${esc(d.conviction_read||"Unformed.")}</div>
    ${rk.rank?`<span class="rank">${esc(rk.conviction)} · ${esc(rk.rank_name)} (rank ${rk.rank})</span>`:""}
    ${d.conviction_calibration?`<div style="font-size:11.5px;color:var(--faint);margin-top:6px;line-height:1.45" title="A track record, not a verification: how often picks of each conviction later cleared a trusted check. Necessary outcomes only.">${esc(d.conviction_calibration)}</div>`:""}
    <div class="stats"><span><b>${s.done||0}</b> done</span>
      <span><b>${bs.running||0}</b> running</span>
      <span><b>${s.blocked||0}</b> blocked</span>
      <span><b>${d.artifacts.length}</b> artifacts</span></div>
    ${vhealth(d.integrity)}
    ${ladderLine(d.ladder)}
    <h4>Milestones</h4>`;
  (d.milestones||[]).forEach(m=>h+=`<div class="row"><span class="g">${esc(m.name)}</span>
    <span class="st">${esc(m.status)}${m.blockers&&m.blockers.length?
    ` · ${m.blockers.length} blocker`:""}</span></div>`);
  h+=`<h4>Tasks</h4>`;
  (d.tasks||[]).forEach(t=>{
    const av=t.artifact_ids.map(a=>`<button class="lk" aria-label="${esc("Open artifact from: "+t.title)}" onclick="showArtifact('${a}')"><span aria-hidden="true">▤</span></button>`).join(" ");
    h+=`<div class="row"><span class="g">${esc(t.title)}</span>
      <span class="st">${esc(t.status)}</span>${av}
      ${t.status==="needs_verify"?`<button class="lk" onclick="approve('${t.id}')">approve</button>`:""}</div>`;});
  h+=`<h4>Artifacts</h4>`;
  (d.artifacts||[]).forEach(a=>{
    const pc=(a.partial&&a.partial.checks&&a.partial.checks.length)?a.partial.checks.join(", "):"necessary conditions";
    const pv=a.partial?`<span class="st" style="color:var(--warn)"
      title="Trusted checks that passed: ${pc} (${a.partial.n_passed}/${a.partial.n_total}), force-to-fail proven, independent-lineage reference. These are NECESSARY conditions only — not proof the deliverable is correct.">⊨ ${pc} · ${a.partial.n_passed}/${a.partial.n_total} trusted</span>`:"";
    const rs=a.report_status==="INVALID"?`<span class="st" role="alert" aria-label="Warning: this signed report failed verification — the snapshot was edited outside the engine and is no longer trusted" style="background:var(--bad);color:var(--ink-on-red);font-family:var(--mono);text-transform:uppercase;font-weight:700;padding:1px 6px;border-radius:2px;transform:rotate(-.5deg);display:inline-block;box-shadow:0 0 10px var(--bad-glow)" title="This signed report FAILED signature verification — the snapshot was edited outside the engine. Its badge is no longer trusted."><span aria-hidden="true">⚠ tampered</span></span>`:"";
    h+=`<div class="row">
      <button class="lk g" onclick="showArtifact('${a.id}')">${esc(a.title)}</button>
      ${pv}${rs}<span class="st">${a.chars}c</span></div>`;});
  if(d.risks&&d.risks.length){h+=`<h4>Risks</h4>`;
    d.risks.slice(0,8).forEach(r=>h+=`<div class="row"><span class="g">${esc(r.title||r.statement||"")}</span>
      <span class="st">${esc(r.level||"")}</span></div>`);}
  h+=`<h4>Log</h4><button class="lk" onclick="showJournal()">View full chronicle →</button>`;
  $("#drawer").innerHTML=h;
}

function openModal(){lastFocus=document.activeElement;const m=$("#modal");
  m.classList.add("show");const sh=m.querySelector(".sheet");
  sh.onkeydown=e=>trapKey(e,sh);
  const c=m.querySelector(".sh .ghost");if(c)c.focus();}
async function showArtifact(aid){
  try{const a=await jget(api+"/project/"+CUR+"/artifact/"+aid);
    $("#m-title").textContent=a.title;$("#m-body").textContent=a.content;
    openModal();}catch(e){toast(""+e.message,true);}}
async function showJournal(){
  try{const j=await jget(api+"/project/"+CUR+"/journal?n=200");
    $("#m-title").textContent="Chronicle";
    $("#m-body").textContent=j.map(e=>`${(tval(e)||"").slice(0,19)}  ${e.type}  ${e.summary||""}`).join("\n");
    openModal();}catch(e){toast(""+e.message,true);}}
/* first-run legend: what the conviction colors and verification tiers MEAN */
function showLegend(){
  $("#m-title").textContent="Key — convictions & verification";
  const row=(c,t,d)=>`<div style="margin:3px 0"><span aria-hidden="true" style="display:inline-block;width:11px;height:11px;border-radius:2px;background:${c};margin-right:8px;vertical-align:middle"></span><b style="color:${c}">${t}</b> — ${d}</div>`;
  const cap=t=>`<div style="color:var(--faint);text-transform:uppercase;letter-spacing:.6px;font-size:11px;margin:12px 0 5px">${t}</div>`;
  $("#m-body").innerHTML=`<div style="white-space:normal;line-height:1.6">
    ${cap("Convictions — the stance a pick takes vs the proven baseline")}
    ${row("var(--info)","Dogmatic","conform to the proven baseline")}
    ${row("var(--accent)","Iconoclast","exceed the baseline — reform it")}
    ${row("var(--pivot)","Heretic","reject the framing — pivot the problem")}
    ${cap("Verification — how much ground truth backs an option")}
    ${row("var(--ok)","Verified","an external oracle ran — ground truth (green stamp)")}
    ${row("var(--warn)","Trusted N/M","necessary-condition checks passed — NOT a full proof (amber stamp)")}
    ${row("var(--dim)","Judged","a model estimate, no oracle (a leaning pencil note)")}
    ${row("var(--faint)","none","no confidence signal")}
    ${row("var(--bad)","Tampered","a signed report failed verification — do not trust (red bar)")}
  </div>`;
  openModal();
}
function closeModal(){$("#modal").classList.remove("show");
  if(lastFocus&&lastFocus.focus)lastFocus.focus();}

/* new project */
function showNew(){
  $("#main").innerHTML=`<div class="newform">
    <h2>New project</h2>
    <input id="nf-name" placeholder="Name">
    <textarea id="nf-obj" placeholder="Objective — what should this project achieve?"></textarea>
    <div style="display:flex;gap:9px"><button class="primary" onclick="createProject()">Create</button>
      <button onclick="loadProject()">Cancel</button></div>
    <div class="hint" style="color:var(--faint);font-size:12px">Planning is a live model call — it may take a moment.</div>
  </div>`;
}
async function createProject(){
  const name=($("#nf-name")||{}).value||"",obj=($("#nf-obj")||{}).value||"";
  if(!name.trim()||!obj.trim()){toast("Name and objective required",true);return;}
  try{const out=await jpost(api+"/new",{name,objective:obj});
    if(out.error){toast(out.error,true);return;}
    pendingNew=true;toast("Planning…");
    $("#main").innerHTML=`<div class="newform"><h2>Drawing up the plan…</h2>
      <div id="livegen" class="livegen" hidden>
        <div class="lgh">Live generation
          <span class="lgsub">model output as it's written — not hidden reasoning
          (the subscription backend doesn't expose reasoning)</span></div>
        <pre id="livegen-body" class="lgbody mono"></pre></div></div>`;
    openLiveGen("new");
    pollOp();
  }catch(e){toast(""+e.message,true);}
}

document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){closeModal();closeDrawer();return;}
  const tag=((document.activeElement||{}).tagName||"");
  if(/INPUT|TEXTAREA/.test(tag))return;          // don't hijack typing
  if(!(CUR&&DG))return;
  const open=(DG.packets||[]).filter(p=>p.status==="presented");
  if(!open.length)return;
  const ae=document.activeElement||{};
  if(e.key==="Enter"){                            // bare Enter commits the pick
    if(ae.getAttribute&&ae.getAttribute("role")==="radio")return;  // radio's own
    e.preventDefault();decide(open[0].id,"select");return;}
  let idx=-1;                                      // 1-9 or A-Z select an option
  if(/^[1-9]$/.test(e.key))idx=+e.key-1;
  else if(/^[a-zA-Z]$/.test(e.key))idx=e.key.toUpperCase().charCodeAt(0)-65;
  if(idx>=0){const o=open[0].options[idx];
    if(o){pick(open[0].id,o.key);
      const el=document.querySelector("#dlg-"+open[0].id+" .opt[data-key=\""+o.key+"\"]");
      if(el)el.focus();}}});

setInterval(pollOp,2500);
setInterval(loadOverview,9000);
loadOverview();
</script>
</body>
</html>
"""
