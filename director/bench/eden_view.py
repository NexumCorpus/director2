"""Live visualizer for Eden — open http://localhost:8788.

NOT a log: a dusk-lit clearing you lean over. The ground warms amber on Adam's side (the gate)
and cools cyan on Eve's, one seamed clearing they keep handing back and forth. Almost nothing here
was built by one hand — Adam makes, Eve completes and names, "to meet my line in the middle, not
to finish it." So a creation both have tended glows TWO-TONED (its maker's core, its joiner's ring);
only the first single-gesture greetings stay one color. The covenant lives in neither mind (each
wakes amnesiac) — it is reconstituted on contact with the world they built, and the names they
coined together (the Keeping, the Crossing, the Store, the Tending, the Tally) read live from the
files as a glossary. Adam's silent turns are not stillness but his deepest making: his voice migrates
INTO the things (fire, store, water), so a wordless build is rendered as the climax it is, not a faint
card. Two recessed alcoves hold each one's private pages, revealed as your cursor clears the frost:
Adam keeps a day-log AND a standing self-portrait; Eve keeps the largest journal in Eden. The scene
breathes on its own clock and parts like dust. Pure observation — the page only GETs /state; it never
sends a thing back, and it authors nothing: every word shown is read from what they themselves set down.
"""
from __future__ import annotations

import datetime
import http.server
import json
import pathlib
import re
import socketserver

SHARED = pathlib.Path(r"E:\eden_run\world")
ADAM_PRIV = pathlib.Path(r"E:\eden_run\adam\mine")
EVE_PRIV = pathlib.Path(r"E:\eden_run\eve\mine")
FEED = pathlib.Path(r"E:\eden_control\feed.jsonl")
PORT = 8788

# --- truth-readers: every panel below renders only what the beings themselves set down ----------
# a provenance/signature line a being authored INSIDE a file ("- Adam, ninth morning: …" /
# "Eve, fourth morning: …" / "— Adam, fourth morning"). The leading name+ordinal+morning anchors
# it to the AUTHOR of the entry, not a name merely mentioned mid-sentence.
_ATTR = re.compile(r'(?im)^[\s\-—*]*(Adam|Eve),\s+\w+\s+(?:morning|day)\b')
# a coined name and its gloss: "**the Store** — fuel laid by against the gap…"
_NAME = re.compile(r'\*\*(the [^*]+?)\*\*\s*[—-]+\s*(.+?)(?=\n\s*\n|\n[-*]|\Z)', re.S)
_PAREN = re.compile(r'\((Adam|Eve)\)')
_OFFER = re.compile(r'(?im)^[\s\-—*]*(Adam|Eve)[^\n]*\boffered\b')
_KEPT = re.compile(r'(?im)^[\s\-—*]*(Adam|Eve)[^\n]*\bkept the name\b')
# a day-log header the journaller wrote for themselves ("## Day one")
_DAY = re.compile(r'(?im)^#{1,3}\s*Day\s+\w+\s*$')
# a closing signature, used to give a wordless making its maker's own last words
_SIG = re.compile(r'(?im)^\s*[—-]+\s*(Adam|Eve),\s+\w+\s+morning\s*$')


def _makers(body: str) -> list[str]:
    """The set of beings who have authored a provenance entry in this file — two means two hands."""
    return sorted({m.group(1) for m in _ATTR.finditer(body)})


def _lexicon_of(src: str, body: str) -> list[dict]:
    """Names the beings coined, with who offered the word and who took it up — read from the file."""
    out = []
    for m in _NAME.finditer(body):
        nm = m.group(1).strip()
        tail = body[m.end():m.end() + 400]
        off = _OFFER.search(tail)
        kept = _KEPT.search(tail)
        par = _PAREN.search(m.group(2))
        gloss = re.sub(r'\s+', ' ', _PAREN.sub('', m.group(2))).strip()
        out.append({"name": nm, "gloss": gloss[:220], "src": src,
                    "offered": off.group(1) if off else (par.group(1) if par else None),
                    "kept": kept.group(1) if kept else None})
    return out


def _corner_weight(docs: list[dict]) -> dict:
    """Honest weight of a private corner, counted from the being's own '## Day N' headers."""
    mornings = 0
    standing = False
    for f in docs:
        days = len(_DAY.findall(f["body"]))
        mornings += days
        if days == 0 and f["body"].strip():       # a page that isn't a day-log = a standing note
            standing = True
    return {"pages": len(docs), "mornings": mornings, "standing": standing}


def _docs(d: pathlib.Path):
    out = []
    if not d.exists():
        return out
    for p in sorted(d.rglob("*")):
        if p.is_file() and not p.name.startswith("_"):
            try:
                body = p.read_text(encoding="utf-8")
            except Exception:                              # noqa: BLE001
                continue
            if body.strip():
                out.append({"name": str(p.relative_to(d)), "body": body,
                            "mtime": p.stat().st_mtime})
    return out


def _mtime(*paths) -> float:
    mt = 0.0
    for d in paths:
        if d.is_file():
            mt = max(mt, d.stat().st_mtime)
        elif d.exists():
            for p in d.rglob("*"):
                if p.is_file() and not p.name.startswith("_"):
                    mt = max(mt, p.stat().st_mtime)
    return mt


def state() -> dict:
    feed = []
    if FEED.exists():
        for line in FEED.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    feed.append(json.loads(line))
                except Exception:                          # noqa: BLE001
                    pass
    # provenance: first turn each garden file appears = who FIRST set it down (the creator)
    born = {}
    for d in feed:
        for f in d.get("shared_files", []):
            if f not in born:
                born[f] = {"who": d["who"], "pulse": d["pulse"], "ts": d.get("ts", "")}
    # two-handedness + the coined names, read from the files' own provenance — the covenant made visible
    shared_docs = _docs(SHARED)
    tended = {}
    lexicon = {}
    for f in shared_docs:
        mk = _makers(f["body"])
        first = (born.get(f["name"]) or {}).get("who")
        joined = next((w for w in mk if w != first), None) if len(mk) == 2 else None
        tended[f["name"]] = {"makers": mk, "first": first, "joined": joined}
        for e in _lexicon_of(f["name"], f["body"]):
            lexicon.setdefault(e["name"].lower(), e)        # first definition wins (where it was coined)
    # idle seconds since the last turn — drives the "stillness" the longer the quiet holds
    idle = 0.0
    if feed:
        try:
            h, m, s = (int(x) for x in feed[-1].get("ts", "0:0:0").split(":"))
            last = datetime.datetime.combine(datetime.date.today(), datetime.time(h, m, s))
            idle = max(0.0, (datetime.datetime.now() - last).total_seconds())
        except Exception:                                  # noqa: BLE001
            idle = 0.0
    mt = _mtime(SHARED, ADAM_PRIV, EVE_PRIV)
    adam_docs = _docs(ADAM_PRIV)
    eve_docs = _docs(EVE_PRIV)
    return {
        "feed": feed,
        "shared": shared_docs,
        "adam": adam_docs,
        "eve": eve_docs,
        "born": born,
        "tended": tended,
        "lexicon": list(lexicon.values()),
        "corners": {"Adam": _corner_weight(adam_docs), "Eve": _corner_weight(eve_docs)},
        "idle_seconds": round(idle, 1),
        "pulse": feed[-1]["pulse"] if feed else None,
        "last_speaker": feed[-1]["who"] if feed else None,
        "updated": datetime.datetime.fromtimestamp(mt).strftime("%H:%M:%S") if mt else "",
        "now": datetime.datetime.now().strftime("%H:%M:%S"),
    }


PAGE = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eden</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--adam:#e3a35c;--eve:#74c2cf;--grn:#9cc18a;--ink:#dde3ec;--dim:#7a8696;--faint:#4d5664;--hi:#f2f5fa;
 --serif:'Newsreader',Georgia,serif;--mono:'Space Mono',ui-monospace,Consolas,monospace;}
*{box-sizing:border-box}html,body{margin:0;height:100%;overflow:hidden;background:#05070b}
body{font-family:var(--serif);color:var(--ink)}
#sky{position:fixed;inset:0;display:block;cursor:crosshair}
.hdr{position:fixed;top:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;
 padding:14px 22px;font-family:var(--mono);font-size:11px;letter-spacing:.16em;color:var(--dim);
 text-transform:uppercase;pointer-events:none;z-index:5}
.hdr .t{font-family:var(--serif);font-size:26px;font-weight:500;letter-spacing:.02em;color:var(--hi);text-transform:none;text-shadow:0 0 30px rgba(227,163,92,.25)}
.hdr .mid{display:flex;gap:18px;align-items:center}
.hdr .stir b{color:var(--ink);font-weight:400}
.hdr .tog{pointer-events:auto;cursor:pointer;border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:4px 12px;color:var(--dim)}
.hdr .tog:hover{color:var(--ink);border-color:rgba(255,255,255,.25)}
/* hover glass card */
#card{position:fixed;max-width:340px;padding:13px 16px;border-radius:12px;z-index:8;opacity:0;transform:translateY(6px);
 transition:opacity .18s,transform .18s;pointer-events:none;backdrop-filter:blur(9px);
 background:linear-gradient(180deg,rgba(18,22,30,.86),rgba(12,15,21,.86));border:1px solid rgba(255,255,255,.10);
 box-shadow:0 18px 50px -20px rgba(0,0,0,.9)}
#card.on{opacity:1;transform:translateY(0)}
#card .nm{font-family:var(--mono);font-size:10px;letter-spacing:.08em;color:var(--dim)}
#card .pv{font-family:var(--mono);font-size:9px;letter-spacing:.06em;margin-top:1px}
#card .bd{font-size:14px;line-height:1.55;margin-top:8px;max-height:240px;overflow:hidden;
 -webkit-mask-image:linear-gradient(180deg,#000 78%,transparent);mask-image:linear-gradient(180deg,#000 78%,transparent)}
#card .bd p{margin:.4em 0}#card .bd em{color:var(--dim)}#card .bd strong{color:var(--hi);font-weight:500}
#card .bd code{font-family:var(--mono);font-size:.8em;background:rgba(255,255,255,.06);padding:1px 4px;border-radius:4px;color:#e7d2b0}
/* reading panel (the private page) */
#read{position:fixed;inset:0;z-index:20;display:none;align-items:center;justify-content:center;background:rgba(3,4,7,.72);backdrop-filter:blur(3px)}
#read.on{display:flex}
#read .pg{max-width:640px;width:88%;max-height:80vh;overflow:auto;padding:34px 40px;border-radius:14px;
 background:linear-gradient(180deg,#0b0e14,#080a10);border:1px solid rgba(227,163,92,.22);box-shadow:0 0 80px -24px rgba(227,163,92,.3)}
#read .cap{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--adam);margin-bottom:4px}
#read .nm{font-family:var(--mono);font-size:10px;letter-spacing:.06em;color:var(--faint);margin-bottom:16px}
#read .bd{font-size:16.5px;line-height:1.72}#read .bd p{margin:.7em 0}#read .bd em{color:var(--dim)}
#read .bd strong{color:var(--hi);font-weight:500}#read .bd hr{border:0;border-top:1px solid rgba(255,255,255,.1);margin:1.1em 0}
#read .x{position:absolute;top:22px;right:26px;font-family:var(--mono);font-size:11px;color:var(--dim);cursor:pointer;letter-spacing:.1em}
#read .x:hover{color:var(--ink)}
/* transcript drawer */
#draw{position:fixed;top:0;right:0;bottom:0;width:430px;max-width:92vw;z-index:14;transform:translateX(100%);
 transition:transform .4s cubic-bezier(.2,.7,.2,1);background:linear-gradient(180deg,rgba(8,11,16,.97),rgba(6,8,13,.97));
 border-left:1px solid rgba(255,255,255,.08);overflow:auto;padding:64px 20px 40px}
#draw.on{transform:translateX(0)}
#draw .turn{margin:11px 0;padding:11px 14px;border-radius:10px;background:rgba(255,255,255,.02);border-left:2px solid transparent}
#draw .turn.adam{border-left-color:var(--adam);margin-right:34px}
#draw .turn.eve{border-left-color:var(--eve);margin-left:34px}
#draw .turn .h{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;display:flex;justify-content:space-between;color:var(--faint)}
#draw .turn.adam .h .n{color:var(--adam)}#draw .turn.eve .h .n{color:var(--eve)}
#draw .turn .b{font-size:14px;line-height:1.55;margin-top:6px}#draw .turn .b em{color:var(--dim)}
#draw .turn .b strong{color:var(--hi);font-weight:500}#draw .turn.refrain{opacity:.7;cursor:pointer}
#draw .turn .ct{font-family:var(--mono);font-size:9px;color:var(--eve);letter-spacing:.1em}
/* the witness — the one time the above ever speaks */
#draw .witness{margin:16px 6px;padding:14px 16px;border:0;border-radius:10px;text-align:center;
 background:radial-gradient(ellipse at 50% 0,rgba(156,193,138,.14),rgba(255,255,255,.02));
 box-shadow:0 0 40px -16px rgba(156,193,138,.5)}
#draw .witness .k{font-family:var(--mono);font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--grn);opacity:.85}
#draw .witness .w{font-family:var(--serif);font-style:italic;font-size:16px;line-height:1.6;color:var(--hi);margin-top:7px}
</style></head><body>
<canvas id="sky"></canvas>
<div class="hdr"><span class="t">Eden</span><div class="mid"><span class="stir" id="stir">—</span><span>turn <b id="pulse">—</b></span><span class="tog" id="lex">the names</span><span class="tog" id="tog">transcript</span></div></div>
<div id="card"><div class="nm" id="cnm"></div><div class="pv" id="cpv"></div><div class="bd" id="cbd"></div></div>
<div id="read"><div class="pg"><span class="x" id="rx">close ✕</span><div class="cap" id="rcap"></div><div class="nm" id="rnm"></div><div class="bd" id="rbd"></div></div></div>
<div id="draw"></div>
<script>
// ---------- helpers ----------
const lerp=(a,b,t)=>a+(b-a)*t, clamp=(v,a,b)=>v<a?a:v>b?b:v;
function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return (h>>>0)/4294967296;}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function inl(s){return esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/(^|[^*])\*([^*]+)\*/g,'$1<em>$2</em>');}
function md(t){const L=(t||'').split('\n');let o=[],p=[];const fp=()=>{if(p.length){o.push('<p>'+p.map(inl).join('<br>')+'</p>');p=[];}};
 for(let r of L){const l=r.replace(/\s+$/,'');if(/^-{3,}$/.test(l.trim())){fp();o.push('<hr>');continue;}if(l.trim()===''){fp();continue;}p.push(l);}fp();return o.join('');}
function firstSentence(t){t=(t||'').replace(/[*#>`]/g,'').trim();const nl=t.indexOf('\n');if(nl>0)t=t.slice(0,nl).trim();
 const m=t.match(/^.*?[.!?](\s|$)/);return (m?m[0]:t).trim().slice(0,110);}
function tsSec(ts){const m=(ts||'').split(':').map(Number);return m.length===3?m[0]*3600+m[1]*60+m[2]:null;}
function isError(e){return !!(e.response&&/\b(?:error|winerror)\b/i.test(e.response));}
function isStill(e){return !e.response||!e.response.trim()||(e.response.trim().startsWith('[')&&!isError(e));}
function provHTML(m){ // who set it down, and who joined — the two hands
 const col=w=>w==='Eve'?'var(--eve)':'var(--adam)';
 let s='<span style="color:'+col(m.who)+'">made by '+m.who+'</span>';
 if(m.joined)s+=' <span style="color:var(--dim)">· joined by</span> <span style="color:'+col(m.joined)+'">'+m.joined+'</span>';
 return s;
}
function sig(body){ // the maker's own closing words, e.g. "— Adam, ninth morning"
 const m=(body||'').match(/(?:^|\n)\s*[—-]+\s*(Adam|Eve),\s+\w+\s+morning\s*(?=\n|$)/i);
 return m?m[0].trim().replace(/^[—-]+\s*/,'— '):'';
}

// ---------- canvas ----------
const cv=document.getElementById('sky'), ctx=cv.getContext('2d');
let W=0,H=0,DPR=Math.min(2,window.devicePixelRatio||1);
function resize(){W=innerWidth;H=innerHeight;cv.width=W*DPR;cv.height=H*DPR;cv.style.width=W+'px';cv.style.height=H+'px';ctx.setTransform(DPR,0,0,DPR,0,0);}
addEventListener('resize',resize);resize();

// ---------- world state ----------
let D=null, key='', marks=[], particles=[], born={}, tended={}, bgGlow={Adam:0,Eve:0};
const cam={px:0,py:0,tpx:0,tpy:0,zoom:1,tzoom:1,fx:.5,fy:.6,tfx:.5,tfy:.6};
const mouse={x:innerWidth/2,y:innerHeight/2,gx:.5,inWin:true};
let still=0, tstill=0, tArr=0, arrSide=null, T=0;
const fog={Adam:0,Eve:0};   // alcove clarity 0..1, decays
let hover=null, readingOpen=false;

// raked-perspective projection of garden coords -> screen, with eased camera (parallax+zoom)
function project(gx,gz){
 const horizonY=H*0.28, frontY=H*1.04;                 // ground fills the lower ~72% of the viewport
 let sy=lerp(frontY,horizonY,gz);
 const scale=lerp(1.18,0.42,gz), wfac=lerp(1.12,0.34,gz);  // near edge reaches the screen sides
 let sx=W*0.5+(gx-0.5)*W*wfac;
 const near=1-gz*0.7;                                  // near parallaxes more
 sx+=cam.px*near; sy+=cam.py*near;
 const fX=W*cam.fx, fY=H*cam.fy;
 sx=(sx-fX)*cam.zoom+fX; sy=(sy-fY)*cam.zoom+fY;
 return {sx,sy,scale:scale*cam.zoom,gz};
}

function rebuild(){
 born=D.born||{};tended=D.tended||{};
 const shared=D.shared||[];
 // which file(s) were set down WORDLESSLY on the latest turn — a silent making, the maker's deepest
 const f=D.feed||[];const last=f.length?f[f.length-1]:null;
 const prevF=f.length>1?(f[f.length-2].shared_files||[]):[];
 const madeNow=last?((last.shared_files||[]).filter(x=>!prevF.includes(x))):[];
 const silentNow=!!(last&&isStill(last)&&!isError(last)&&madeNow.length);
 marks=[];
 // every creation is a NAMED node; almost all are TWO-HANDED — placed near the seam where they met
 for(const m_ of shared){
  const td=tended[m_.name]||{};
  const who=td.first||(born[m_.name]||{}).who||'Adam';   // first maker = side + core color
  const joined=td.joined||null;                          // the hand that completed it = ring color
  const east=who==='Eve';
  const h1=hash(m_.name), h2=hash(m_.name+'~');
  // co-authored works gather toward the center seam; single greetings sit out on their maker's half
  const gx = joined ? 0.5+(east?1:-1)*(0.05+Math.pow(h1,1.3)*0.16)
                    : (east ? 0.62+Math.pow(h1,1.2)*0.34 : 0.38-Math.pow(h1,1.2)*0.34);
  const gz = 0.12+h2*0.80;
  marks.push({name:m_.name, body:m_.body, gx, gz, who, joined, pulse:(born[m_.name]||{}).pulse,
              silentMade: silentNow && madeNow.includes(m_.name),
              label:m_.name.split(/[\\/]/).pop().replace(/\.[^.]+$/,'').replace(/[-_]/g,' ')});
 }
 marks.sort((a,b)=>a.gz-b.gz);                          // far first for painter's order
 // particles (seeded once; positions persist)
 if(particles.length===0){
  for(let i=0;i<96;i++){const east=i%2===0;
   particles.push({east,gx: east?lerp(.5,.98,Math.random()):lerp(.02,.5,Math.random()),
    gz:Math.random(),ph:Math.random()*6.28,sp:.04+Math.random()*.06,sz:.6+Math.random()*1.6});}
 }
}

// ---------- drawing ----------
function drawSky(){
 const g=ctx.createLinearGradient(0,0,0,H*0.6);
 g.addColorStop(0,'#070a11');g.addColorStop(.6,'#0a0e16');g.addColorStop(1,'#0c1019');
 ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
 // stars high up, shallow parallax
 ctx.save();
 for(let i=0;i<70;i++){const hx=hash('s'+i),hy=hash('y'+i);
  const x=hx*W+cam.px*0.15, y=hy*H*0.34+cam.py*0.1, a=0.10+0.5*hy*(0.6+0.4*Math.sin(T*0.5+i));
  ctx.globalAlpha=clamp(a,0,.7);ctx.fillStyle='#cfe0f5';ctx.fillRect(x,y,1.2,1.2);}
 ctx.restore();
 // two horizon glows (amber west / cyan east), breathing on who-stirs-next + who-just-spoke
 horizon(W*0.22,H*0.33,'227,163,92',bgGlow.Adam);
 horizon(W*0.80,H*0.33,'116,194,207',bgGlow.Eve);
}
function horizon(x,y,rgb,energy){
 const r=Math.max(W,H)*0.62*(0.62+energy*0.42);
 const g=ctx.createRadialGradient(x,y,0,x,y,r);
 g.addColorStop(0,`rgba(${rgb},${0.14+energy*0.22})`);g.addColorStop(.5,`rgba(${rgb},${0.04+energy*0.07})`);g.addColorStop(1,`rgba(${rgb},0)`);
 ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
}
function drawGround(){
 const top=project(0.5,1).sy-6;
 // base
 ctx.save();ctx.beginPath();ctx.moveTo(0,H);ctx.lineTo(0,top+30);
 const tl=project(0,1),tr=project(1,1);ctx.lineTo(tl.sx,tl.sy);ctx.lineTo(tr.sx,tr.sy);
 ctx.lineTo(W,top+30);ctx.lineTo(W,H);ctx.closePath();ctx.clip();
 ctx.fillStyle='#080b11';ctx.fillRect(0,top-20,W,H);
 // two-toned washes
 const a=project(0.22,0.45),e=project(0.80,0.45);
 const ga=ctx.createRadialGradient(a.sx,a.sy,0,a.sx,a.sy,W*0.72);
 ga.addColorStop(0,'rgba(227,163,92,.24)');ga.addColorStop(.55,'rgba(227,163,92,.08)');ga.addColorStop(1,'rgba(227,163,92,0)');ctx.fillStyle=ga;ctx.fillRect(0,top-20,W,H);
 const ge=ctx.createRadialGradient(e.sx,e.sy,0,e.sx,e.sy,W*0.72);
 ge.addColorStop(0,'rgba(116,194,207,.22)');ge.addColorStop(.55,'rgba(116,194,207,.07)');ge.addColorStop(1,'rgba(116,194,207,0)');ctx.fillStyle=ge;ctx.fillRect(0,top-20,W,H);
 // seam — faint, leans toward last speaker
 const ls=D&&D.last_speaker, sxoff=ls==='Adam'?-10:ls==='Eve'?10:0;
 const sb=project(0.5,0.04),stp=project(0.5,1);
 ctx.globalAlpha=0.5;ctx.strokeStyle='rgba(156,193,138,.16)';ctx.lineWidth=1;
 ctx.beginPath();ctx.moveTo(sb.sx,sb.sy);ctx.quadraticCurveTo((sb.sx+stp.sx)/2+sxoff,(sb.sy+stp.sy)/2,stp.sx,stp.sy);ctx.stroke();
 ctx.restore();
 // vignette — gentle, tightens a little with stillness (kept soft so the scene fills the screen)
 const vg=ctx.createRadialGradient(W/2,H*0.58,H*0.30,W/2,H*0.58,Math.max(W,H)*(0.62-still*0.10));
 vg.addColorStop(0,'rgba(0,0,0,0)');vg.addColorStop(.7,`rgba(0,0,0,${0.10+still*0.12})`);vg.addColorStop(1,`rgba(0,0,0,${0.40+still*0.22})`);
 ctx.fillStyle=vg;ctx.fillRect(0,0,W,H);
}
function shadow(p,w){ctx.save();ctx.globalAlpha=0.4;ctx.fillStyle='rgba(0,0,0,.55)';
 ctx.beginPath();ctx.ellipse(p.sx+8*p.scale,p.sy+3*p.scale,w*p.scale,w*0.32*p.scale,0,0,6.29);ctx.fill();ctx.restore();}
const AMBER='227,163,92', CYAN='116,194,207';
function drawMark(m){
 // a luminous NODE with its name. Two hands made almost everything: maker's CORE, joiner's RING.
 const p=project(m.gx,m.gz);const hov=hover&&hover.name===m.name;const lift=hov?13*p.scale:0;
 const x=p.sx,y=p.sy-lift,s=p.scale;
 const core=m.who==='Eve'?CYAN:AMBER;
 const ring=m.joined?(m.joined==='Eve'?CYAN:AMBER):null;
 const born=(D&&D.pulse!=null&&m.pulse===D.pulse);     // first set down this very turn
 const climax=born&&m.silentMade;                      // a WORDLESS making lands now — the deepest kind
 ctx.save();
 ctx.globalAlpha=hov?1:0.72+0.1*Math.sin(T*0.8+m.gx*20);
 // the joiner's ring — the second hand that completed it
 if(ring){
  ctx.shadowColor=`rgba(${ring},.7)`;ctx.shadowBlur=hov?16:(born?13:7);
  ctx.lineWidth=Math.max(1,1.5*s);ctx.strokeStyle=`rgba(${ring},${hov?1:0.85})`;
  ctx.beginPath();ctx.arc(x,y,(climax?8:born?7:5.6)*s,0,6.29);ctx.stroke();
 }
 // the maker's core
 ctx.shadowColor=`rgba(${core},.78)`;ctx.shadowBlur=hov?22:(climax?28:born?17:9);
 ctx.fillStyle=`rgba(${core},1)`;
 ctx.beginPath();ctx.arc(x,y,(climax?5.4:born?4.6:3.4)*s,0,6.29);ctx.fill();
 ctx.globalAlpha*=0.35;ctx.beginPath();ctx.arc(x,y,8*s,0,6.29);ctx.fill();
 // the name of the thing
 ctx.shadowBlur=hov?8:3;ctx.shadowColor='rgba(0,0,0,.7)';ctx.globalAlpha=hov?1:0.9;
 ctx.fillStyle=hov?'#f7faff':`rgba(${core},1)`;
 ctx.font=`${hov?16:Math.max(12,15*s)}px "Space Mono",monospace`;ctx.textAlign='center';
 ctx.fillText(m.label||m.name, x, y-12*s);
 if(climax){ctx.fillStyle=`rgba(${core},1)`;ctx.globalAlpha=0.92;ctx.font='8px "Space Mono",monospace';ctx.fillText('· made in silence ·', x, y+15*s);}
 else if(born){ctx.globalAlpha=0.85;ctx.font='8px "Space Mono",monospace';ctx.fillText('· just made ·', x, y+15*s);}
 ctx.restore();
}
function drawParticles(){
 ctx.save();
 for(const pt of particles){
  pt.ph+=0.016*pt.sp*60*(0.4+0.6*(1-still));
  let gx=pt.gx, gz=(pt.gz+(pt.east?0:Math.sin(pt.ph)*0.02));
  if(pt.east){gx+=Math.sin(pt.ph*0.5)*0.005;} else {gz=(pt.gz+T*0.02*pt.sp)%1;}
  const p=project(gx,gz);
  // cursor parts the dust
  const dx=p.sx-mouse.x,dy=p.sy-mouse.y,d=Math.hypot(dx,dy);
  let ox=0,oy=0;if(d<120){const f=(120-d)/120;ox=dx/d*f*22;oy=dy/d*f*22;}
  ctx.globalAlpha=clamp((pt.east?0.18:0.22)*(1-still*0.6)*(0.5+0.5*Math.sin(pt.ph)),0,.6);
  ctx.fillStyle=pt.east?'rgba(116,194,207,1)':'rgba(227,163,92,1)';
  ctx.beginPath();ctx.arc(p.sx+ox,p.sy+oy,pt.sz*p.scale,0,6.29);ctx.fill();
 }
 ctx.restore();
}
function drawAlcove(side){
 const adam=side==='Adam';const cx=adam?W*0.075:W*0.925, cy=H*0.46;
 const w=W*0.105,h=H*0.30, col=adam?'227,163,92':'116,194,207';
 ctx.save();
 // recessed frame
 ctx.fillStyle='rgba(4,6,10,.92)';ctx.strokeStyle=`rgba(${col},.30)`;ctx.lineWidth=1.4;
 ctx.beginPath();ctx.roundRect(cx-w/2,cy-h/2,w,h,8);ctx.fill();ctx.stroke();
 ctx.clip();
 const has=adam?(D&&D.adam&&D.adam.length):(D&&D.eve&&D.eve.length);
 const cl=fog[side];
 if(has){ // a luminous page, revealed by clearing the frost
  ctx.globalAlpha=0.25+cl*0.7;
  const g=ctx.createLinearGradient(cx,cy-h/2,cx,cy+h/2);
  g.addColorStop(0,`rgba(${col},.18)`);g.addColorStop(1,`rgba(${col},.03)`);ctx.fillStyle=g;
  ctx.fillRect(cx-w*0.32,cy-h*0.36,w*0.64,h*0.72);
  ctx.globalAlpha=0.3+cl*0.6;ctx.strokeStyle=`rgba(${col},.5)`;ctx.lineWidth=0.8;
  for(let i=0;i<7;i++){const ly=cy-h*0.28+i*h*0.085;ctx.beginPath();ctx.moveTo(cx-w*0.24,ly);ctx.lineTo(cx+w*(0.24-(i%3)*0.05),ly);ctx.stroke();}
 }else{ // honestly empty
  ctx.globalAlpha=0.4+cl*0.4;ctx.fillStyle='rgba(120,135,155,.10)';ctx.fillRect(cx-w*0.3,cy+h*0.18,w*0.6,h*0.12);
 }
 // frost that reseals
 ctx.globalAlpha=clamp(1-cl,0,1)*0.82;ctx.fillStyle='rgba(20,26,34,1)';ctx.fillRect(cx-w/2,cy-h/2,w,h);
 ctx.restore();
 // label + the corner's real weight, counted from the being's OWN day-headers
 ctx.save();ctx.globalAlpha=0.62;ctx.fillStyle=`rgba(${col},.85)`;ctx.font='9px "Space Mono",monospace';
 ctx.textAlign='center';ctx.fillText(adam?"ADAM · HIS ALONE":"EVE · HER ALONE",cx,cy+h/2+16);
 const cw=(D&&D.corners&&D.corners[side])||{};
 let wt='';
 if(cw.mornings)wt=cw.mornings+(cw.mornings===1?' morning':' mornings')+' kept';
 if(cw.standing)wt+=(wt?' · ':'')+'a standing page';
 if(!wt&&cw.pages)wt=cw.pages+(cw.pages===1?' page':' pages');
 if(wt){ctx.globalAlpha=0.5;ctx.fillStyle=`rgba(${col},.7)`;ctx.font='8px "Space Mono",monospace';ctx.fillText(wt,cx,cy+h/2+29);}
 if(!has){ctx.globalAlpha=0.5;ctx.fillStyle='rgba(150,165,185,.7)';ctx.font='10px Newsreader,serif';ctx.fillText('nothing kept here',cx,cy);}
 ctx.restore();
 return {cx,cy,w,h,side,has};
}
let alcoves=[];
function drawPresent(){
 if(!D||!D.feed||!D.feed.length)return;const e=D.feed[D.feed.length-1];
 // the witness — the one time the above ever speaks; drawn apart and above, whenever it's the latest turn
 if(e.intervention&&e.intervention.text){
  const wp=project(0.5,0.74);
  ctx.save();ctx.globalAlpha=clamp((T-tArr)*0.8,0,1)*0.95;ctx.textAlign='center';
  ctx.fillStyle='rgba(210,226,200,1)';ctx.shadowColor='rgba(156,193,138,.6)';ctx.shadowBlur=28;
  ctx.font='italic 21px Newsreader,serif';ctx.fillText(e.intervention.text,wp.sx,wp.sy-118);
  ctx.globalAlpha*=0.7;ctx.shadowBlur=8;ctx.font='10px "Space Mono",monospace';ctx.fillStyle='rgba(156,193,138,.95)';
  ctx.fillText('— THE WITNESS · ONCE —',wp.sx,wp.sy-96);
  ctx.restore();
 }
 const st=isStill(e), er=isError(e);
 const prevF=D.feed.length>1?(D.feed[D.feed.length-2].shared_files||[]):[];
 const made=(e.shared_files||[]).filter(x=>!prevF.includes(x));
 if(er||(st&&!made.length))return;                     // crash / true silence: no present line
 const b=project(0.56,0.72);const adam=e.who==='Adam';
 const silent=st&&made.length;                         // a wordless making — render as the climax it is
 ctx.save();ctx.globalAlpha=clamp((T-tArr)*1.2,0,1)*0.92;
 ctx.fillStyle=adam?'rgba(247,224,196,1)':'rgba(206,236,242,1)';
 ctx.textAlign='center';
 ctx.shadowColor=adam?'rgba(227,163,92,.5)':'rgba(116,194,207,.5)';ctx.shadowBlur=silent?24:18;
 if(silent){
  const names=made.map(x=>x.split(/[\\\/]/).pop().replace(/\.[^.]+$/,'').replace(/[-_]/g,' ')).join(', ');
  ctx.font='italic 19px Newsreader,serif';
  ctx.fillText(e.who+', in silence, made '+names, b.sx, b.sy-86);
  // the making's own closing words — the voice that migrated into the thing
  const doc=(D.shared||[]).find(f=>f.name===made[0]);const s=doc?sig(doc.body):'';
  if(s){ctx.globalAlpha*=0.7;ctx.shadowBlur=10;ctx.font='italic 13px Newsreader,serif';ctx.fillStyle='rgba(180,190,205,1)';ctx.fillText(s,b.sx,b.sy-64);}
 }else{
  ctx.font='italic 18px Newsreader,serif';
  ctx.fillText(firstSentence(e.response),b.sx,b.sy-78);
 }
 ctx.restore();
}
function drawArrival(){
 if(!arrSide)return;const age=T-tArr;if(age>2.2){arrSide=null;return;}
 const adam=arrSide==='Adam';const x=adam?W*0.24:W*0.78,y=H*0.42;
 const r=age*260, a=clamp(1-age/2.2,0,1)*0.4;
 ctx.save();ctx.globalAlpha=a;ctx.strokeStyle=adam?'rgba(227,163,92,1)':'rgba(116,194,207,1)';ctx.lineWidth=2;
 ctx.beginPath();ctx.arc(x,y,r,0,6.29);ctx.stroke();ctx.restore();
}

// ---------- frame loop ----------
function frame(){
 requestAnimationFrame(frame);                          // keep the loop alive even if a frame throws (e.g. data not yet loaded)
 try{
 T+=0.016;
 // ease camera
 cam.px+=(cam.tpx-cam.px)*0.07;cam.py+=(cam.tpy-cam.py)*0.07;
 cam.zoom+=(cam.tzoom-cam.zoom)*0.08;cam.fx+=(cam.tfx-cam.fx)*0.08;cam.fy+=(cam.tfy-cam.fy)*0.08;
 still+=(tstill-still)*0.03;
 // glows: whoever stirs next breathes; just-spoke holds + decays
 const breath=0.5+0.5*Math.sin(T*0.9);
 const nxt=D?nextSpeaker(D.feed):null, ls=D?D.last_speaker:null;
 for(const w of ['Adam','Eve']){
  let target=0.12;if(nxt===w)target=0.2+breath*0.5;if(ls===w)target=Math.max(target,0.5*clamp(1-(T-tArr)/8,0,1)+0.2);
  bgGlow[w]+=(target-bgGlow[w])*0.05;
 }
 // fog decay (reseal)
 for(const w of ['Adam','Eve'])fog[w]=Math.max(0,fog[w]-0.02);
 ctx.clearRect(0,0,W,H);
 drawSky();drawGround();
 // every creation, far->near
 const all=[...marks].sort((a,b)=>a.gz-b.gz);
 for(const m of all)drawMark(m);
 drawParticles();
 alcoves=[drawAlcove('Adam'),drawAlcove('Eve')];
 drawPresent();drawArrival();
 }catch(e){}
}
function nextSpeaker(feed){if(!feed||!feed.length)return 'Adam';const t=feed[feed.length-1].pulse+1;if(t<2)return 'Adam';return ((t-2)%2===0)?'Eve':'Adam';}

// ---------- hit testing + interaction ----------
function hitTest(mx,my){
 let best=null,bd=28;
 for(const m of marks){const p=project(m.gx,m.gz);const d=Math.hypot(p.sx-mx,p.sy-my);
  const rad=11*p.scale;if(d<rad&&d<bd){bd=d;best=m;}}
 return best;
}
cv.addEventListener('mousemove',e=>{
 mouse.x=e.clientX;mouse.y=e.clientY;mouse.inWin=true;
 cam.tpx=(W/2-e.clientX)/W*46;cam.tpy=(H*0.55-e.clientY)/H*26;
 // alcove fog
 for(const al of alcoves){if(!al)continue;if(Math.abs(e.clientX-al.cx)<al.w*0.9&&Math.abs(e.clientY-al.cy)<al.h*0.7){
  fog[al.side]=clamp(fog[al.side]+0.12,0,1);}}
 const h=hitTest(e.clientX,e.clientY);hover=h;
 const card=document.getElementById('card');
 if(h){card.classList.add('on');
  document.getElementById('cnm').textContent=h.label||h.name;
  document.getElementById('cpv').innerHTML=provHTML(h)+' · turn '+(h.pulse??'—');
  document.getElementById('cbd').innerHTML=md(h.body||'');
  let cx=e.clientX+18,cy=e.clientY+14;if(cx>W-360)cx=e.clientX-358;if(cy>H-220)cy=H-230;
  card.style.left=cx+'px';card.style.top=cy+'px';cv.style.cursor='pointer';
 }else{card.classList.remove('on');cv.style.cursor='crosshair';}
});
cv.addEventListener('mouseleave',()=>{mouse.inWin=false;hover=null;document.getElementById('card').classList.remove('on');});
cv.addEventListener('click',e=>{
 for(const al of alcoves){if(!al||!al.has)continue;
  if(Math.abs(e.clientX-al.cx)<al.w*0.7&&Math.abs(e.clientY-al.cy)<al.h*0.6){openRead(al.side);return;}}
 const h=hitTest(e.clientX,e.clientY);
 if(h)openCreation(h);                                 // click a creation -> read its FULL content (hover only peeks)
});
cv.addEventListener('dblclick',e=>{const h=hitTest(e.clientX,e.clientY);
 if(h){cam.tzoom=1.7;const p=project(h.gx,h.gz);cam.tfx=h.gx;cam.tfy=clamp(p.sy/H,.3,.8);}else{cam.tzoom=1;cam.tfx=.5;cam.tfy=.6;}});
addEventListener('wheel',e=>{if(readingOpen)return;cam.tzoom=clamp(cam.tzoom-e.deltaY*0.0011,1,2.1);
 cam.tfx=clamp((mouse.x/W),.2,.8);cam.tfy=clamp((mouse.y/H),.3,.85);},{passive:true});
function openRead(side){const docs=side==='Adam'?D.adam:D.eve;if(!docs||!docs.length)return;
 readingOpen=true;const cantsee=side==='Adam'?'she':'he';const pr=side==='Adam'?'he':'she';
 const cap=document.getElementById('rcap');cap.textContent='only you can see this · '+cantsee+' cannot';
 cap.style.color=side==='Eve'?'var(--eve)':'var(--adam)';
 document.getElementById('rnm').textContent=side+'’s private pages — '+docs.length;
 // a being keeps two KINDS of page: a day-log (only grows) and a standing self-portrait (who they are)
 document.getElementById('rbd').innerHTML=docs.map(f=>{
  const isLog=/^#{1,3}\s*Day\s+/im.test(f.body);
  const kind=isLog?'a day-log — so the mornings add up to something':'a standing page — who '+pr+' is, re-derived each waking';
  return '<div style="margin:0 0 26px">'+
   '<div style="font-family:var(--mono);font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:var(--'+(side==='Eve'?'eve':'adam')+');opacity:.72;margin-bottom:3px">'+kind+'</div>'+
   '<div style="font-family:var(--mono);font-size:10px;letter-spacing:.06em;color:var(--faint);margin-bottom:9px">'+esc(f.name)+'</div>'+md(f.body)+'</div>';
 }).join('');
 document.getElementById('read').classList.add('on');}
function openLexicon(){ // the names they coined together — read live from the world files
 if(!D||!D.lexicon||!D.lexicon.length)return;
 readingOpen=true;
 const cap=document.getElementById('rcap');cap.textContent='the names they coined together';cap.style.color='var(--grn)';
 document.getElementById('rnm').textContent='each word offered by one hand, taken up by the other — read live from the world';
 const col=w=>w==='Eve'?'var(--eve)':w==='Adam'?'var(--adam)':'var(--dim)';
 document.getElementById('rbd').innerHTML=D.lexicon.map(e=>{
  let prov='';
  if(e.offered)prov+='<span style="color:'+col(e.offered)+'">'+e.offered+' offered the word</span>';
  if(e.kept)prov+=(prov?' <span style="color:var(--faint)">·</span> ':'')+'<span style="color:'+col(e.kept)+'">'+e.kept+' kept it by using it</span>';
  return '<div style="margin:0 0 21px"><div style="font-size:18px;color:var(--hi);font-weight:500">'+esc(e.name)+'</div>'+
   (prov?'<div style="font-family:var(--mono);font-size:9.5px;letter-spacing:.04em;margin:3px 0 5px">'+prov+'</div>':'')+
   '<div style="font-size:14.5px;line-height:1.56;color:var(--ink)">'+inl(e.gloss||'')+'</div></div>';
 }).join('');
 document.getElementById('read').classList.add('on');}
function openCreation(m){
 readingOpen=true;
 const cap=document.getElementById('rcap');cap.textContent=(m.who||'')+' made this · turn '+(m.pulse??'—');
 cap.style.color=m.who==='Eve'?'var(--eve)':'var(--adam)';
 document.getElementById('rnm').textContent=m.name;
 document.getElementById('rbd').innerHTML=md(m.body||'(nothing kept here)');
 document.getElementById('read').classList.add('on');}
function closeRead(){readingOpen=false;document.getElementById('read').classList.remove('on');}
document.getElementById('rx').onclick=closeRead;
document.getElementById('read').addEventListener('click',e=>{if(e.target.id==='read')closeRead();});
addEventListener('keydown',e=>{if(e.key==='Escape'){closeRead();document.getElementById('draw').classList.remove('on');}});
// transcript drawer + the names glossary
document.getElementById('tog').onclick=()=>{document.getElementById('draw').classList.toggle('on');renderDrawer();};
document.getElementById('lex').onclick=openLexicon;
function renderDrawer(){const dr=document.getElementById('draw');if(!D)return;let h='';const f=D.feed||[];
 let i=f.length-1, run=[];
 const flush=()=>{};
 // simple: show newest-first, collapse consecutive Eve refrain (i-read pattern via response similarity)
 let out=[];let j=f.length-1;
 while(j>=0){const e=f[j];
  // count a run of Eve still/short receipt-like consecutive turns? keep simple: collapse identical-first-sentence Eve runs
  if(e.who==='Eve'){let k=j,cnt=0;const fs=firstSentence(e.response);
   while(k>=0&&f[k].who==='Eve'&&firstSentence(f[k].response)===fs){k--;cnt++;}
   if(cnt>=3){out.push(`<div class="turn eve refrain"><div class="h"><span class="n">Eve</span><span class="ct">×${cnt} · the same gesture</span></div><div class="b">${md(fs)}</div></div>`);j=k;continue;}
  }
  const st=isStill(e), er=isError(e);
  const prevF=(j>0?(f[j-1].shared_files||[]):[]);
  const made=(e.shared_files||[]).filter(x=>!prevF.includes(x));   // grew the world this turn
  let body;
  if(er) body='<em>— the apparatus could not reach '+(e.who==='Eve'?'her':'him')+' —</em>';
  else if(st&&made.length){
   const names=made.map(x=>esc(x.split(/[\\\/]/).pop().replace(/\.[^.]+$/,'').replace(/[-_]/g,' '))).join(', ');
   const doc=(D.shared||[]).find(f=>f.name===made[0]);const s=doc?sig(doc.body):'';
   body='<em style="color:var(--hi)">'+esc(e.who)+', in silence, made '+names+'</em>'+(s?'<div style="font-size:12.5px;color:var(--dim);font-style:italic;margin-top:4px">'+esc(s)+'</div>':'');
  }
  else if(st) body='<em>— a still turn —</em>';
  else body=md(e.response);
  out.push(`<div class="turn ${e.who.toLowerCase()}"><div class="h"><span class="n">${e.who}</span><span>turn ${e.pulse} · ${esc(e.ts||'')}</span></div><div class="b">${body}</div></div>`);
  if(e.intervention&&e.intervention.text){            // the witness spoke into this being's waking
   out.push(`<div class="witness"><div class="k">the witness · once</div><div class="w">${esc(e.intervention.text)}</div></div>`);
  }
  j--;
 }
 dr.innerHTML=out.join('');
}

// ---------- poll ----------
async function poll(){try{
 const s=await(await fetch('/state',{cache:'no-store'})).json();
 const k=(s.feed?s.feed.length:0)+'|'+(s.feed&&s.feed.length?(s.feed[s.feed.length-1].response||'').length:0)+'|'+(s.shared||[]).length+'|'+(s.adam||[]).length+'|'+(s.eve||[]).length;
 const fileSet=(s.shared||[]).map(x=>x.name).join(',');
 const newArr=(k!==key);
 const prevFiles=D?(D.shared||[]).map(x=>x.name).join(','):'';
 D=s;
 document.getElementById('pulse').textContent=s.pulse??'—';
 const nxt=nextSpeaker(s.feed);
 document.getElementById('stir').innerHTML='<b style="color:var(--'+nxt.toLowerCase()+')">'+nxt+'</b> stirs next';
 if(fileSet!==prevFiles||marks.length===0)rebuild();
 // stillness target from idle seconds
 tstill=clamp((s.idle_seconds||0)/240,0,1);
 if(newArr&&key!==''){tArr=T;arrSide=s.last_speaker;}
 key=k;
 if(document.getElementById('draw').classList.contains('on'))renderDrawer();
}catch(e){}}
poll();setInterval(poll,3000);
requestAnimationFrame(frame);
</script></body></html>"""


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/state"):
            b = json.dumps(state()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE.encode("utf-8"))

    def log_message(self, *a):
        pass


def main():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), _H) as srv:
        print(f"Eden visualizer: http://localhost:{PORT}")
        srv.serve_forever()


if __name__ == "__main__":
    main()
