import os, re, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, request, Response

try:
    import yt_dlp
    YTDLP = True
except ImportError:
    yt_dlp = None
    YTDLP = False

app = Flask(__name__)
pool = ThreadPoolExecutor(max_workers=4)
lock = threading.RLock()
cache = {}
TRENDING = ["Nepali rap hits","Lil Buddha rap","Sacar rap","Vten hip hop","Uniq Poet","Yama Buddha","Chirag Khadka rap","Nepali hip hop new"]
VID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")

def get(key, ttl):
    with lock:
        x = cache.get(key)
        if not x: return None
        if time.time()-x["at"] > ttl:
            cache.pop(key, None); return None
        return x["value"]

def put(key, value):
    with lock:
        cache[key] = {"at":time.time(),"value":value}
        if len(cache)>500:
            for k,_ in sorted(cache.items(),key=lambda z:z[1]["at"])[:100]: cache.pop(k,None)

def opts(flat=False):
    d={"quiet":True,"no_warnings":True,"noplaylist":True,"socket_timeout":12,"retries":1,"extractor_retries":1}
    if flat: d.update(skip_download=True,extract_flat=True,default_search="ytsearch")
    else: d.update(skip_download=True,format="bestaudio[ext=m4a]/bestaudio/best",extractor_args={"youtube":{"player_client":["android"]}})
    return d

def search(q, limit=20):
    q=(q or "").strip()[:160]
    if not q or not YTDLP: return []
    key=f"s:{q.casefold()}:{limit}"
    old=get(key,600)
    if old is not None: return old
    try:
        with yt_dlp.YoutubeDL(opts(True)) as y: info=y.extract_info(f"ytsearch{limit}:{q}",download=False) or {}
        out=[]
        for e in info.get("entries") or []:
            if not e: continue
            vid=str(e.get("id") or "")
            if not VID.fullmatch(vid): continue
            thumbs=sorted([t for t in e.get("thumbnails",[]) if t.get("url")],key=lambda t:t.get("width") or 0,reverse=True)
            out.append({"id":vid,"title":e.get("title") or "Untitled","artist":e.get("uploader") or e.get("channel") or "YouTube","duration":e.get("duration"),"thumbnail":thumbs[0]["url"] if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"})
        put(key,out); return out
    except Exception:
        app.logger.exception("Search failed"); return []

def trending():
    jobs=[pool.submit(search,q,12) for q in TRENDING]
    out=[]; seen=set()
    for job in as_completed(jobs):
        try:
            for t in job.result():
                if t["id"] not in seen: seen.add(t["id"]); out.append(t)
        except Exception: app.logger.exception("Trending task failed")
    return out[:80]

def resolve(vid):
    if not VID.fullmatch(vid or ""): return None
    key="a:"+vid; old=get(key,1200)
    if old: return old
    if not YTDLP: return None
    try:
        with yt_dlp.YoutubeDL(opts()) as y: info=y.extract_info("https://www.youtube.com/watch?v="+vid,download=False) or {}
        url=info.get("url")
        if not url:
            for f in info.get("formats") or []:
                if f.get("url") and f.get("acodec") not in (None,"none") and f.get("vcodec") in (None,"none"):
                    url=f["url"]; break
        if url: put(key,url)
        return url
    except Exception:
        app.logger.exception("Resolve failed"); return None

@app.after_request
def headers(r):
    r.headers.setdefault("X-Content-Type-Options","nosniff")
    r.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    return r

@app.get("/")
def home(): return Response(HTML,mimetype="text/html")

@app.get("/api/health")
def health(): return jsonify(ok=True,yt_dlp=YTDLP,cache=len(cache))

@app.get("/api/search")
def api_search():
    if not YTDLP: return jsonify(ok=False,error="yt-dlp is not installed"),500
    q=(request.args.get("q") or "").strip()
    if not q: return jsonify(ok=False,error="Enter a song or artist"),400
    try: limit=max(1,min(int(request.args.get("limit",30)),40))
    except ValueError: limit=30
    rows=search(q,limit)
    return jsonify(ok=True,results=rows,count=len(rows))

@app.get("/api/trending")
def api_trending():
    if not YTDLP: return jsonify(ok=False,error="yt-dlp is not installed"),500
    rows=get("trending",1800)
    if rows is None: rows=trending(); put("trending",rows)
    return jsonify(ok=True,results=rows,count=len(rows))

@app.get("/api/resolve")
def api_resolve():
    vid=(request.args.get("id") or "").strip()
    if not VID.fullmatch(vid): return jsonify(ok=False,error="Invalid video ID"),400
    url=resolve(vid)
    if not url: return jsonify(ok=False,error="Could not prepare audio. Update yt-dlp and try another track."),502
    # Browser streams media directly; no long-lived Vercel proxy request.
    return jsonify(ok=True,url=url)

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1"/>
<meta name="theme-color" content="#07070a"/>
<meta name="apple-mobile-web-app-capable" content="yes"/>
<meta name="mobile-web-app-capable" content="yes"/>
<title>CKRPRO MUSIC</title>
<style>
:root{
  color-scheme:dark;
  --bg:#07070a;
  --card:#12121a;
  --card2:#1a1a26;
  --text:#f7f7ff;
  --muted:#9a9ab0;
  --accent:#d6ff4a;
  --accent2:#ff4ecd;
  --cyan:#3de7ff;
  --ink:#0a0a10;
  --wa:#25D366;
  --yt:#FF0000;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{background:var(--bg);color:var(--text);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;min-height:100%}
body{padding-bottom:calc(96px + env(safe-area-inset-bottom));overflow-x:hidden}
button,input{font:inherit;border:0;outline:0;background:none;color:inherit}
button{cursor:pointer}
.wrap{width:min(100%,720px);margin:0 auto;padding:20px 16px 28px;position:relative;z-index:1}

/* soft animated dots (no glow lines) */
.dots{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.dots span{position:absolute;width:4px;height:4px;border-radius:50%;background:var(--accent);opacity:.35;animation:float 7s ease-in-out infinite}
.dots span:nth-child(2){background:var(--accent2);animation-duration:8.5s;opacity:.3}
.dots span:nth-child(3){background:var(--cyan);animation-duration:6.5s;opacity:.28}
.dots span:nth-child(4){background:var(--accent);animation-duration:9s;opacity:.22}
.dots span:nth-child(5){background:var(--accent2);animation-duration:7.8s;opacity:.25}
.dots span:nth-child(6){background:var(--cyan);animation-duration:10s;opacity:.2}
.dots span:nth-child(7){background:var(--accent);animation-duration:8s;opacity:.3}
.dots span:nth-child(8){background:var(--accent2);animation-duration:6s;opacity:.22}
.dots span:nth-child(9){background:var(--cyan);animation-duration:9.5s;opacity:.26}
.dots span:nth-child(10){background:var(--accent);animation-duration:7.2s;opacity:.24}
.dots span:nth-child(11){background:var(--accent2);animation-duration:8.8s;opacity:.2}
.dots span:nth-child(12){background:var(--cyan);animation-duration:6.8s;opacity:.28}
@keyframes float{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-18px) scale(1.35)}}

.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;animation:in .45s ease both}
.logo{font-weight:800;letter-spacing:.14em;font-size:14px}
.logo span{display:block;margin-top:3px;font-size:9px;font-weight:600;letter-spacing:.2em;color:var(--muted);text-transform:uppercase}
.social{display:flex;gap:8px}
.social a{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;background:var(--card);transition:transform .15s ease}
.social a:active{transform:scale(.9)}
.social a svg{width:16px;height:16px;display:block}

.hero{background:var(--card);border-radius:18px;padding:18px 16px;margin-bottom:16px;animation:in .5s ease .05s both}
.hero .tag{font-size:10px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}
.hero h1{font-size:clamp(22px,5.5vw,30px);line-height:1.15;font-weight:800;letter-spacing:-.02em}
.hero h1 em{font-style:normal;color:var(--cyan)}
.hero p{margin-top:8px;color:var(--muted);font-size:12px;line-height:1.45}

.search{display:flex;align-items:center;gap:10px;height:50px;padding:0 14px;border-radius:14px;background:var(--card);margin-bottom:18px;animation:in .5s ease .1s both}
.search svg{width:16px;height:16px;opacity:.5;flex-shrink:0}
.search input{flex:1;height:100%;font-size:14px;background:transparent}
.search input::placeholder{color:var(--muted)}

.sec{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;animation:in .5s ease .12s both}
.sec b{font-size:11px;letter-spacing:.12em;text-transform:uppercase}
.sec span{font-size:11px;color:var(--muted)}
.list{display:flex;flex-direction:column;gap:5px}
.row{display:flex;align-items:center;gap:11px;padding:9px;border-radius:14px;min-width:0;animation:rowin .35s ease both;transition:background .15s,transform .12s}
.row:active{transform:scale(.985);background:var(--card)}
.row.on{background:var(--card)}
.row.on .t{color:var(--accent)}
.thumb{width:48px;height:48px;border-radius:11px;background:var(--card2) center/cover no-repeat;flex-shrink:0}
.meta{flex:1;min-width:0}
.t{font-size:13px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.a{font-size:11px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dur{font-size:10px;color:var(--muted)}
.pb{width:34px;height:34px;border-radius:999px;background:var(--card2);display:grid;place-items:center;flex-shrink:0;transition:transform .12s}
.row.on .pb{background:var(--accent);color:var(--ink)}
.pb svg{width:13px;height:13px;fill:currentColor}
.empty{text-align:center;padding:40px 12px;color:var(--muted);font-size:13px;line-height:1.55}

.bar{position:fixed;left:0;right:0;bottom:0;z-index:20;padding:10px 12px calc(10px + env(safe-area-inset-bottom));background:rgba(10,10,14,.97);transform:translateY(110%);transition:transform .25s cubic-bezier(.2,.8,.2,1)}
.bar.show{transform:translateY(0)}
.barline{position:absolute;left:0;right:0;top:0;height:2px;background:#1e1e28}
.barline i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--cyan));transition:width .08s linear}
.barin{width:min(100%,720px);margin:0 auto;display:flex;align-items:center;gap:8px}
.bart{width:42px;height:42px;border-radius:10px;background:var(--card2) center/cover no-repeat;flex-shrink:0}
.barm{flex:1;min-width:0}
.barm .t{font-size:12px}.barm .a{font-size:10px;margin-top:2px}
.icon{width:36px;height:36px;border-radius:999px;display:grid;place-items:center;color:var(--muted);transition:transform .12s}
.icon:active{transform:scale(.88)}
.icon svg{width:17px;height:17px;fill:currentColor}
.icon.main{width:42px;height:42px;background:var(--accent);color:var(--ink)}
.icon.main svg{width:17px;height:17px}

.sheet{position:fixed;inset:0;z-index:30;background:var(--bg);transform:translateY(105%);transition:transform .3s cubic-bezier(.2,.8,.2,1);overflow:auto}
.sheet.show{transform:translateY(0)}
.sheetin{width:min(100%,520px);margin:0 auto;min-height:100%;padding:16px 20px calc(28px + env(safe-area-inset-bottom));display:flex;flex-direction:column}
.shead{height:44px;display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.shead b{font-size:10px;letter-spacing:.16em;color:var(--muted);text-transform:uppercase}
.x{width:38px;height:38px;border-radius:999px;background:var(--card);font-size:20px;color:var(--muted);display:grid;place-items:center}
.cover{width:min(72vw,300px);aspect-ratio:1;margin:6px auto 18px;border-radius:16px;background:var(--card) center/cover no-repeat;animation:pulse 4s ease-in-out infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.02)}}
.nt{text-align:center;font-size:18px;font-weight:750}
.na{text-align:center;color:var(--muted);font-size:12px;margin:6px 0 16px}
.seek{height:26px;display:flex;align-items:center;position:relative;touch-action:none}
.seek .bg{position:absolute;left:0;right:0;height:4px;border-radius:99px;background:#252532}
.seek .fg{position:absolute;left:0;height:4px;border-radius:99px;background:linear-gradient(90deg,var(--accent),var(--cyan));width:0}
.seek .dot{position:absolute;top:50%;width:12px;height:12px;border-radius:99px;background:var(--text);transform:translate(-50%,-50%);left:0}
.times{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:4px}
.ctrls{display:flex;justify-content:center;align-items:center;gap:16px;margin:18px 0 8px}
.ctrls .icon{width:44px;height:44px}
.ctrls .main{width:60px;height:60px}
.ctrls .main svg{width:20px;height:20px}
.vol{display:flex;align-items:center;gap:10px;margin-top:6px;color:var(--muted);font-size:12px}
.vol input{flex:1;accent-color:var(--accent)}
.toast{position:fixed;left:50%;bottom:110px;transform:translateX(-50%) translateY(8px);background:var(--card);color:var(--text);padding:10px 14px;border-radius:12px;font-size:12px;opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;z-index:40}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
@keyframes in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes rowin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
</style>
</head>
<body>
<div class="dots" id="dots" aria-hidden="true"></div>
<div class="wrap">
  <div class="topbar">
    <div class="logo">CKRPRO<span>MUSIC</span></div>
    <div class="social">
      <a href="https://wa.me/" target="_blank" rel="noopener" aria-label="WhatsApp" data-sfx>
        <svg viewBox="0 0 24 24"><path fill="#25D366" d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
      </a>
      <a href="https://www.youtube.com/" target="_blank" rel="noopener" aria-label="YouTube" data-sfx>
        <svg viewBox="0 0 24 24"><path fill="#FF0000" d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814z"/><path fill="#fff" d="M9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
      </a>
    </div>
  </div>

  <div class="hero">
    <div class="tag">ENJOY EVERYONE</div>
    <h1>Play anything.<br><em>Stay in flow.</em></h1>
    <p></p>
  </div>

  <div class="search">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
    <input id="q" type="search" placeholder="Search songs" enterkeyhint="search" autocomplete="off"/>
  </div>

  <div class="sec"><b id="sec-title">Trending</b><span id="sec-count">0</span></div>
  <div class="list" id="list"><div class="empty">Loading…</div></div>
</div>

<div class="bar" id="bar">
  <div class="barline"><i id="mini-p"></i></div>
  <div class="barin">
    <div class="bart" id="mini-art"></div>
    <div class="barm" id="open-full">
      <div class="t" id="mini-title">—</div>
      <div class="a" id="mini-artist">—</div>
    </div>
    <button class="icon" id="btn-prev" data-sfx aria-label="Previous"><svg viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg></button>
    <button class="icon main" id="btn-play" data-sfx aria-label="Play"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button>
    <button class="icon" id="btn-next" data-sfx aria-label="Next"><svg viewBox="0 0 24 24"><path d="M16 6h2v12h-2zm-11 6 8.5 6V6z"/></svg></button>
  </div>
</div>

<div class="sheet" id="sheet">
  <div class="sheetin">
    <div class="shead"><b>Now playing</b><button class="x" id="close" data-sfx>×</button></div>
    <div class="cover" id="cover"></div>
    <div class="nt" id="ftitle">—</div>
    <div class="na" id="fartist">—</div>
    <div class="seek" id="seek"><div class="bg"></div><div class="fg" id="fg"></div><div class="dot" id="dot"></div></div>
    <div class="times"><span id="cur">0:00</span><span id="dur">0:00</span></div>
    <div class="ctrls">
      <button class="icon" id="fprev" data-sfx><svg viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z"/></svg></button>
      <button class="icon main" id="fplay" data-sfx><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button>
      <button class="icon" id="fnext" data-sfx><svg viewBox="0 0 24 24"><path d="M16 6h2v12h-2zm-11 6 8.5 6V6z"/></svg></button>
    </div>
    <div class="vol"><span>Vol</span><input id="vol" type="range" min="0" max="1" step="0.01" value="0.9"/></div>
  </div>
</div>

<div class="toast" id="toast"></div>
<audio id="audio" playsinline webkit-playsinline></audio>

<script>
/* animated dots */
(function(){
  const box=document.getElementById('dots');
  if(!box) return;
  for(let i=0;i<28;i++){
    const s=document.createElement('span');
    s.style.left=(Math.random()*100)+'%';
    s.style.top=(Math.random()*100)+'%';
    s.style.animationDelay=(Math.random()*4)+'s';
    s.style.width=s.style.height=(2+Math.random()*4)+'px';
    box.appendChild(s);
  }
})();

const $ = id => document.getElementById(id);
const audio = $('audio');
audio.setAttribute('playsinline','');
audio.setAttribute('webkit-playsinline','');
audio.preload = 'auto';

let tracks=[], current=-1, reqId=0, shuffle=false, repeat='all', wakeLock=null;

/* LOUD UI click SFX via WebAudio */
let actx=null;
function ensureAudio(){
  if(!actx){ try{ actx=new (window.AudioContext||window.webkitAudioContext)(); }catch(e){} }
  if(actx && actx.state==='suspended') actx.resume();
  return actx;
}
function clickSound(type){
  const ctx=ensureAudio(); if(!ctx) return;
  const t0=ctx.currentTime;
  const o=ctx.createOscillator();
  const g=ctx.createGain();
  o.connect(g); g.connect(ctx.destination);
  if(type==='play'){
    o.type='square'; o.frequency.setValueAtTime(520,t0); o.frequency.exponentialRampToValueAtTime(880,t0+.06);
    g.gain.setValueAtTime(0.0001,t0); g.gain.exponentialRampToValueAtTime(0.55,t0+.01); g.gain.exponentialRampToValueAtTime(0.0001,t0+.12);
  } else if(type==='nav'){
    o.type='triangle'; o.frequency.setValueAtTime(360,t0);
    g.gain.setValueAtTime(0.0001,t0); g.gain.exponentialRampToValueAtTime(0.4,t0+.008); g.gain.exponentialRampToValueAtTime(0.0001,t0+.09);
  } else {
    o.type='sine'; o.frequency.setValueAtTime(240,t0);
    g.gain.setValueAtTime(0.0001,t0); g.gain.exponentialRampToValueAtTime(0.35,t0+.008); g.gain.exponentialRampToValueAtTime(0.0001,t0+.08);
  }
  o.start(t0); o.stop(t0+.14);
}
document.addEventListener('pointerdown', e=>{
  const el=e.target.closest('[data-sfx],button,.row,.social a');
  if(!el) return;
  if(el.id==='btn-play'||el.id==='fplay') clickSound('play');
  else if(el.id==='btn-next'||el.id==='fnext'||el.id==='btn-prev'||el.id==='fprev') clickSound('nav');
  else clickSound('tap');
}, true);

const ICO={
  play:'<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
  pause:'<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>'
};
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('show');clearTimeout(toast._t);toast._t=setTimeout(()=>t.classList.remove('show'),2200);}
function fmt(s){if(!Number.isFinite(s)||s<0)return'0:00';s=Math.floor(s);return Math.floor(s/60)+':'+(s%60).toString().padStart(2,'0');}
function esc(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function setIcons(playing){const h=playing?ICO.pause:ICO.play;$('btn-play').innerHTML=h;$('fplay').innerHTML=h;}

function renderList(){
  $('sec-count').textContent=tracks.length;
  if(!tracks.length){$('list').innerHTML='<div class="empty">No tracks.<br>Try another search.</div>';return;}
  $('list').innerHTML=tracks.map((t,i)=>`
    <div class="row ${i===current?'on':''}" data-i="${i}" style="animation-delay:${Math.min(i,12)*0.03}s">
      <div class="thumb" style="background-image:url('${esc(t.thumbnail)}')"></div>
      <div class="meta"><div class="t">${esc(t.title)}</div><div class="a">${esc(t.artist)}</div></div>
      <div class="dur">${t.duration?fmt(t.duration):''}</div>
      <div class="pb">${i===current&&!audio.paused?ICO.pause:ICO.play}</div>
    </div>`).join('');
}

function showNow(t){
  if(!t) return;
  $('bar').classList.add('show');
  $('mini-title').textContent=t.title; $('mini-artist').textContent=t.artist;
  $('ftitle').textContent=t.title; $('fartist').textContent=t.artist;
  $('mini-art').style.backgroundImage=`url('${t.thumbnail}')`;
  $('cover').style.backgroundImage=`url('${t.thumbnail}')`;
  if('mediaSession' in navigator){
    try{navigator.mediaSession.metadata=new MediaMetadata({title:t.title,artist:t.artist,album:'CKRPRO MUSIC',artwork:[{src:t.thumbnail,sizes:'512x512',type:'image/jpeg'}]});}catch(e){}
  }
}
async function keepAwake(on){
  try{
    if(on){ if('wakeLock' in navigator && !wakeLock){ wakeLock=await navigator.wakeLock.request('screen'); wakeLock.addEventListener('release',()=>{wakeLock=null;}); } }
    else if(wakeLock){ await wakeLock.release(); wakeLock=null; }
  }catch(e){}
}

async function playTrack(i){
  if(i<0||i>=tracks.length) return;
  const id=++reqId; current=i; const t=tracks[i];
  showNow(t); renderList();
  audio.pause(); audio.removeAttribute('src'); audio.load();
  toast('Loading…');
  try{
    const r=await fetch('/api/resolve?id='+encodeURIComponent(t.id));
    const d=await r.json();
    if(id!==reqId) return;
    if(!r.ok||!d.ok||!d.url) throw new Error(d.error||'Unavailable');
    audio.src=d.url; audio.load(); await audio.play();
    $('toast').classList.remove('show'); keepAwake(true);
  }catch(e){ toast(e.message||'Play failed'); }
}
function toggle(){ if(current<0){ if(tracks.length) playTrack(0); return; } if(audio.paused) audio.play().catch(()=>toast('Tap play')); else audio.pause(); }
function next(ended=false){
  if(!tracks.length) return;
  if(repeat==='one'&&ended){ audio.currentTime=0; audio.play().catch(()=>{}); return; }
  if(shuffle&&tracks.length>1){ let n=current; while(n===current) n=Math.floor(Math.random()*tracks.length); playTrack(n); return; }
  if(current+1<tracks.length) playTrack(current+1); else if(repeat==='all') playTrack(0); else if(ended) audio.pause();
}
function prev(){
  if(current<0) return;
  if(audio.currentTime>3){ audio.currentTime=0; return; }
  if(current>0) playTrack(current-1); else if(repeat==='all') playTrack(tracks.length-1); else audio.currentTime=0;
}

if('mediaSession' in navigator){
  try{
    navigator.mediaSession.setActionHandler('play',()=>audio.play().catch(()=>{}));
    navigator.mediaSession.setActionHandler('pause',()=>audio.pause());
    navigator.mediaSession.setActionHandler('nexttrack',()=>next());
    navigator.mediaSession.setActionHandler('previoustrack',prev);
  }catch(e){}
}
document.addEventListener('visibilitychange',()=>{});

audio.addEventListener('play',()=>{ setIcons(true); keepAwake(true); });
audio.addEventListener('pause',()=>setIcons(false));
audio.addEventListener('ended',()=>next(true));
audio.addEventListener('loadedmetadata',()=>$('dur').textContent=fmt(audio.duration));
audio.addEventListener('timeupdate',()=>{
  if(!Number.isFinite(audio.duration)||audio.duration<=0) return;
  const p=audio.currentTime/audio.duration*100;
  $('fg').style.width=p+'%'; $('dot').style.left=p+'%'; $('mini-p').style.width=p+'%';
  $('cur').textContent=fmt(audio.currentTime);
});
audio.addEventListener('error',()=>{ if(audio.src) toast('Stream error'); });
$('vol').addEventListener('input',e=>audio.volume=+e.target.value); audio.volume=.9;

(function(){
  const el=$('seek');
  function pos(ev){ const r=el.getBoundingClientRect(); const x=(ev.touches?ev.touches[0].clientX:ev.clientX)-r.left; return Math.min(1,Math.max(0,x/r.width)); }
  function seek(ev){ if(!Number.isFinite(audio.duration)||audio.duration<=0) return; audio.currentTime=pos(ev)*audio.duration; }
  el.addEventListener('pointerdown',e=>{ el.setPointerCapture(e.pointerId); seek(e); });
  el.addEventListener('pointermove',e=>{ if(el.hasPointerCapture(e.pointerId)) seek(e); });
})();

$('list').addEventListener('click',e=>{ const row=e.target.closest('.row'); if(!row) return; playTrack(+row.dataset.i); });
$('btn-play').onclick=toggle; $('fplay').onclick=toggle;
$('btn-next').onclick=()=>next(); $('fnext').onclick=()=>next();
$('btn-prev').onclick=prev; $('fprev').onclick=prev;
$('open-full').onclick=()=>$('sheet').classList.add('show');
$('mini-art').onclick=()=>$('sheet').classList.add('show');
$('close').onclick=()=>$('sheet').classList.remove('show');

let st=null;
async function loadTrending(){
  $('sec-title').textContent='Trending';
  try{ const r=await fetch('/api/trending'); const d=await r.json(); if(!d.ok) throw new Error(d.error||'Failed'); tracks=d.results||[]; renderList(); }
  catch(e){ $('list').innerHTML='<div class="empty">'+esc(e.message)+'</div>'; }
}
async function doSearch(q){
  if(st) st.abort(); st=new AbortController();
  $('sec-title').textContent='Results'; $('list').innerHTML='<div class="empty">Searching…</div>';
  try{
    const r=await fetch('/api/search?q='+encodeURIComponent(q)+'&limit=30',{signal:st.signal});
    const d=await r.json(); if(!d.ok) throw new Error(d.error||'Search failed'); tracks=d.results||[]; renderList();
  }catch(e){ if(e.name==='AbortError') return; $('list').innerHTML='<div class="empty">'+esc(e.message)+'</div>'; }
}
let timer=null;
$('q').addEventListener('input',()=>{ clearTimeout(timer); const v=$('q').value.trim(); timer=setTimeout(()=>{ if(v) doSearch(v); else loadTrending(); },400); });
$('q').addEventListener('keydown',e=>{ if(e.key==='Enter'){ e.preventDefault(); const v=$('q').value.trim(); if(v) doSearch(v); }});
loadTrending();
</script>
</body>
</html>
"""
