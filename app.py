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

# 🔥 Vercel मा Cookies ह्यान्डल गर्ने फंक्शन
def setup_cookies():
    cookie_content = os.environ.get("YT_COOKIES", "").strip()
    if cookie_content:
        try:
            with open("/tmp/cookies.txt", "w", encoding="utf-8") as f:
                f.write(cookie_content)
            print("✅ Cookies written to /tmp/cookies.txt")
        except Exception as e:
            print(f"❌ Failed to write cookies: {e}")
    else:
        print("⚠️ WARNING: YT_COOKIES env var is empty. YouTube bot check will likely fail.")

# स्टार्टअपमा कुकीज लोड गर्ने
setup_cookies()

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

# 🔥 अपडेट गरिएको opts फंक्शन (Cookies र iOS/Web Player सहित)
def opts(flat=False):
    d = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "socket_timeout": 12, "retries": 1, "extractor_retries": 1,
        # Android लाई हटाएर iOS र Web राखिएको छ
        "extractor_args": {"youtube": {"player_client": ["ios", "web"]}}
    }
    
    # यदि कुकीज फाइल बनेको छ भने प्रयोग गर्ने
    cookie_file = "/tmp/cookies.txt"
    if os.path.exists(cookie_file):
        d["cookiefile"] = cookie_file

    if flat:
        d.update(skip_download=True, extract_flat=True, default_search="ytsearch")
    else:
        # ffmpeg नचाहिने format मात्र राखिएको छ
        d.update(skip_download=True, format="bestaudio[ext=m4a]/bestaudio/best")
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
    except Exception as e:
        print(f"Search failed: {e}")
        return []

def trending():
    jobs=[pool.submit(search,q,12) for q in TRENDING]
    out=[]; seen=set()
    for job in as_completed(jobs):
        try:
            for t in job.result():
                if t["id"] not in seen: seen.add(t["id"]); out.append(t)
        except Exception: pass
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
    except Exception as e:
        print(f"Resolve failed for {vid}: {e}")
        return None

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
    return jsonify(ok=True,url=url)

HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#090b10"><title>CKRPRO MUSIC</title>
<style>
:root{color-scheme:dark;--bg:#090b10;--panel:#151b25;--panel2:#202a37;--txt:#f5f7fa;--muted:#8792a3;--lime:#d4fb72;--ink:#111609}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--bg);color:var(--txt);font-family:Inter,system-ui,sans-serif;min-height:100vh;padding-bottom:100px}
button,input{font:inherit}button{border:0;background:none;color:inherit;cursor:pointer}
.page{width:min(100%,760px);margin:auto;padding:25px 18px 35px}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:25px}
.brand{font-size:19px;font-weight:1000;letter-spacing:1.5px}.sub{font-size:9px;color:var(--muted);font-weight:900;letter-spacing:2px;margin-top:4px}
.links{display:flex;gap:9px}.link{width:40px;height:40px;display:grid;place-items:center;border-radius:13px;background:var(--panel);color:var(--muted)}.link svg{width:19px;height:19px;fill:currentColor}
.hero{padding:26px 22px;border-radius:23px;background:linear-gradient(135deg,#1d2935,#151b25);margin-bottom:20px}
.eyebrow{font-size:10px;color:var(--lime);font-weight:950;letter-spacing:2px;margin-bottom:11px}
h1{font-size:clamp(30px,7vw,42px);line-height:1.03;letter-spacing:-1.7px;font-weight:1000}.hero p{margin-top:12px;color:#aab3c0;font-size:12px;line-height:1.6}
.search{height:54px;display:flex;align-items:center;background:var(--panel);border-radius:15px;padding:0 15px;margin-bottom:25px;gap:10px}
.search input{width:100%;height:100%;background:none;border:0;outline:0;color:var(--txt);font-size:14px}.search input::placeholder{color:var(--muted)}
.clear{display:none;color:var(--muted);font-size:20px}.clear.show{display:block}
.head{display:flex;justify-content:space-between;margin-bottom:11px}.head b{font-size:12px;letter-spacing:1.2px;text-transform:uppercase}.count{font-size:11px;color:var(--muted)}
.track{display:flex;align-items:center;gap:12px;padding:9px;border-radius:14px;min-width:0;cursor:pointer}.track:active,.track.active{background:#1b2519}
.art{width:54px;height:54px;flex-shrink:0;border-radius:11px;background:var(--panel2) center/cover no-repeat}
.info{flex:1;min-width:0}.title{font-size:13px;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:5px}.track.active .title{color:var(--lime)}
.artist{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.duration{font-size:10px;color:var(--muted)}.playbtn{width:36px;height:36px;border-radius:50%;background:var(--panel2);display:grid;place-items:center}.playbtn svg{width:14px;height:14px;fill:currentColor}
.track.active .playbtn{background:var(--lime);color:var(--ink)}
.empty{text-align:center;padding:45px 10px;color:var(--muted);font-size:13px;line-height:1.7}
.player{position:fixed;z-index:5;bottom:0;left:0;right:0;padding:10px 14px calc(10px + env(safe-area-inset-bottom));background:rgba(17,22,30,.97);backdrop-filter:blur(14px);transform:translateY(110%);transition:.22s}
.player.show{transform:translateY(0)}.progress{position:absolute;top:0;left:0;right:0;height:2px;background:#303b49}.progress span{display:block;width:0;height:100%;background:var(--lime)}
.playerin{width:min(100%,760px);margin:auto;display:flex;align-items:center;gap:8px}
.miniart{width:42px;height:42px;flex-shrink:0;border-radius:9px;background:var(--panel2) center/cover no-repeat}
.miniinfo{flex:1;min-width:0}.minititle,.miniartist{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.minititle{font-size:11px;font-weight:850}.miniartist{font-size:10px;color:var(--muted);margin-top:4px}
.ctrl{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;color:var(--muted)}.ctrl svg{width:17px;height:17px;fill:currentColor}
.primary{width:41px;height:41px;background:var(--lime);color:var(--ink)}.primary svg{width:17px;height:17px}
.full{position:fixed;z-index:10;inset:0;background:var(--bg);overflow:auto;transform:translateY(105%);transition:.28s}.full.show{transform:translateY(0)}
.fullin{width:min(100%,540px);min-height:100%;margin:auto;padding:18px 25px calc(25px + env(safe-area-inset-bottom));display:flex;flex-direction:column}
.top{height:44px;display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.top b{font-size:10px;letter-spacing:2px;color:var(--muted)}
.close{width:38px;height:38px;border-radius:50%;background:var(--panel);font-size:22px;color:var(--muted)}
.album{width:min(76vw,330px);aspect-ratio:1;margin:0 auto 25px;border-radius:18px;background:var(--panel) center/cover no-repeat}
.nowtitle{text-align:center;font-size:19px;font-weight:950}.nowartist{text-align:center;color:var(--muted);font-size:12px;margin:8px 0 22px}
.seek{height:28px;display:flex;align-items:center;position:relative;touch-action:pan-y}.seekbg{height:4px;width:100%;background:#303b49;border-radius:8px;overflow:hidden}.seekfill{height:100%;width:0;background:var(--lime)}.dot{position:absolute;left:0;top:50%;width:11px;height:11px;border-radius:50%;background:var(--lime);transform:translate(-50%,-50%)}
.times{display:flex;justify-content:space-between;color:var(--muted);font-size:10px}.controls{display:flex;justify-content:space-between;align-items:center;margin:20px 0}.controls .ctrl{width:43px;height:43px}.controls .primary{width:60px;height:60px}
.selected{color:var(--lime)!important}.volume{display:flex;gap:12px;align-items:center;margin:4px 0 20px}.volume input{flex:1;accent-color:var(--lime)}.queue{text-align:center;color:var(--muted);font-size:10px;letter-spacing:1.4px}
.toast{position:fixed;z-index:20;left:50%;bottom:100px;transform:translate(-50%,10px);opacity:0;pointer-events:none;background:#303b49;padding:10px 15px;border-radius:12px;font-size:12px;transition:.18s}.toast.show{opacity:1;transform:translate(-50%,0)}
@media(min-width:650px){.page{padding-top:35px}.hero{padding:32px}.track{padding:11px}}
</style></head><body>
<main class="page">
<header><div><div class="brand">CKRPRO MUSIC</div><div class="sub">MUSIC STREAM</div></div><div class="links">
<a class="link" href="https://wa.me/9779840825493" target="_blank" rel="noopener" aria-label="WhatsApp">W</a>
<a class="link" href="https://youtube.com/@ckrunknown" target="_blank" rel="noopener" aria-label="YouTube">▶</a>
</div></header>
<section class="hero"><div class="eyebrow">YOUR MUSIC. YOUR MOMENT.</div><h1>Find your next<br>favourite track.</h1><p>DISCOVER NEPALI RAP, HIP-HOP & THE SOUNDS YOU LOVE.</p></section>
<div class="search"><input id="search" placeholder="Search songs, artists, albums..." autocomplete="off"><button id="clear" class="clear">×</button></div>
<div class="head"><b id="section">Trending for you</b><span class="count" id="count"></span></div><section id="list"></section></main>
<div class="player" id="player"><div class="progress"><span id="mini-progress"></span></div><div class="playerin">
<div class="miniart" id="mini-art"></div><div class="miniinfo" id="mini-info"><div class="minititle" id="mini-title">—</div><div class="miniartist" id="mini-artist">—</div></div>
<button class="ctrl" id="prev-mini">|◀</button><button class="ctrl primary" id="play-mini">▶</button><button class="ctrl" id="next-mini">▶|</button>
</div></div>
<section class="full" id="full"><div class="fullin"><div class="top"><button class="close" id="close">⌄</button><b>NOW PLAYING</b><span></span></div>
<div class="album" id="album"></div><div class="nowtitle" id="now-title">—</div><div class="nowartist" id="now-artist">—</div>
<div class="seek" id="seek"><div class="seekbg"><div class="seekfill" id="seek-fill"></div></div><div class="dot" id="seek-dot"></div></div>
<div class="times"><span id="elapsed">0:00</span><span id="duration">0:00</span></div>
<div class="controls"><button class="ctrl" id="shuffle">⇄</button><button class="ctrl" id="prev">|◀</button><button class="ctrl primary" id="play-full">▶</button><button class="ctrl" id="next">▶|</button><button class="ctrl" id="repeat">↻</button></div>
<div class="volume">− <input id="volume" type="range" min="0" max="1" step=".01" value=".9"> +</div><div class="queue" id="queue">CKRPRO MUSIC</div></div></section>
<audio id="audio" preload="none" playsinline></audio><div class="toast" id="toast"></div>
<script>
'use strict';
const $=id=>document.getElementById(id),audio=$('audio');
let tracks=[],current=-1,shuffle=false,repeat='off',timer=0,ctl=null,requestNo=0,toastTimer=0,ctx=null,lastClick=0;
function sound(){
 try{const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;if(!ctx)ctx=new AC();if(ctx.state==='suspended')ctx.resume();
 const n=ctx.currentTime;if(n-lastClick<.05)return;lastClick=n;
 [[1050,.7,0],[1550,.2,.008]].forEach(([f,v,o])=>{const a=ctx.createOscillator(),g=ctx.createGain();a.type='triangle';a.frequency.setValueAtTime(f,n+o);a.frequency.exponentialRampToValueAtTime(f*.58,n+o+.075);g.gain.setValueAtTime(.0001,n+o);g.gain.exponentialRampToValueAtTime(v,n+o+.006);g.gain.exponentialRampToValueAtTime(.0001,n+o+.095);a.connect(g);g.connect(ctx.destination);a.start(n+o);a.stop(n+o+.1);});
 }catch(e){}
}
document.addEventListener('click',e=>{if(e.target.closest('button,.track,.link'))sound();},true);
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmt(s){if(s==null||!Number.isFinite(Number(s)))return '—';s=Math.floor(s);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
function toast(s){$('toast').textContent=s;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),2300);}
function loading(){ $('list').innerHTML=Array.from({length:7},()=>'<div class="track"><div class="art"></div><div class="info"><div class="title">Loading…</div><div class="artist">Please wait</div></div></div>').join('');}
function render(){
 $('count').textContent=tracks.length?tracks.length+' tracks':'';
 if(!tracks.length){$('list').innerHTML='<div class="empty">No tracks found.<br>Try another search.</div>';return;}
 $('list').innerHTML=tracks.map((t,i)=>`<article class="track ${i===current?'active':''}" data-i="${i}"><div class="art" style="background-image:url('${esc(t.thumbnail)}')"></div><div class="info"><div class="title">${esc(t.title)}</div><div class="artist">${esc(t.artist)}</div></div><span class="duration">${fmt(t.duration)}</span><button class="playbtn">▶</button></article>`).join('');
 $('list').querySelectorAll('.track').forEach(el=>el.addEventListener('click',()=>playTrack(+el.dataset.i)));
}
function active(){document.querySelectorAll('.track').forEach((e,i)=>e.classList.toggle('active',i===current));}
async function trending(){
 $('section').textContent='Trending for you';loading();
 try{const r=await fetch('/api/trending');const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Trending unavailable');tracks=d.results||[];current=-1;render();}
 catch(e){$('list').innerHTML='<div class="empty">'+esc(e.message)+'<br>Refresh and try again.</div>';}
}
async function search(q){
 if(ctl)ctl.abort();if(!q){trending();return;}const c=new AbortController();ctl=c;$('section').textContent='Search results';loading();
 try{const r=await fetch('/api/search?q='+encodeURIComponent(q)+'&limit=35',{signal:c.signal});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Search failed');if(ctl!==c)return;tracks=d.results||[];current=-1;render();}
 catch(e){if(e.name!=='AbortError'&&ctl===c)$('list').innerHTML='<div class="empty">'+esc(e.message)+'</div>';}
}
function info(t,i){
 $('mini-art').style.backgroundImage=`url("${t.thumbnail}")`;$('album').style.backgroundImage=`url("${t.thumbnail}")`;
 $('mini-title').textContent=t.title;$('mini-artist').textContent=t.artist;$('now-title').textContent=t.title;$('now-artist').textContent=t.artist;
 $('queue').textContent=`QUEUE · ${i+1} / ${tracks.length}`;$('player').classList.add('show');
 if('mediaSession'in navigator&&'MediaMetadata'in window)try{navigator.mediaSession.metadata=new MediaMetadata({title:t.title,artist:t.artist,album:'CKRPRO MUSIC',artwork:[{src:t.thumbnail,sizes:'512x512',type:'image/jpeg'}]});}catch(e){}
}
async function playTrack(i){
 if(i<0||i>=tracks.length)return;const id=++requestNo;current=i;const t=tracks[i];info(t,i);active();audio.pause();audio.removeAttribute('src');audio.load();toast('Preparing audio…');
 try{const r=await fetch('/api/resolve?id='+encodeURIComponent(t.id));const d=await r.json();if(id!==requestNo)return;if(!r.ok||!d.ok||!d.url)throw Error(d.error||'Audio unavailable');audio.src=d.url;audio.load();await audio.play();$('toast').classList.remove('show');}
 catch(e){if(id===requestNo){toast('Unable to play this track. Try another.');active();}}
}
function toggle(){if(current<0){if(tracks.length)playTrack(0);return;}if(audio.paused)audio.play().catch(()=>toast('Tap play to start'));else audio.pause();}
function next(ended=false){if(!tracks.length)return;if(repeat==='one'&&ended){audio.currentTime=0;audio.play().catch(()=>{});return;}if(shuffle&&tracks.length>1){let n=current;while(n===current)n=Math.floor(Math.random()*tracks.length);playTrack(n);return;}if(current+1<tracks.length)playTrack(current+1);else if(repeat==='all')playTrack(0);else if(ended)audio.pause();}
function prev(){if(current<0)return;if(audio.currentTime>3){audio.currentTime=0;return;}if(current>0)playTrack(current-1);else if(repeat==='all')playTrack(tracks.length-1);else audio.currentTime=0;}
function icons(on){$('play-mini').textContent=on?'Ⅱ':'▶';$('play-full').textContent=on?'Ⅱ':'▶';active();if('mediaSession'in navigator)try{navigator.mediaSession.playbackState=on?'playing':'paused';}catch(e){}}
if('mediaSession'in navigator)try{navigator.mediaSession.setActionHandler('play',()=>audio.play().catch(()=>{}));navigator.mediaSession.setActionHandler('pause',()=>audio.pause());navigator.mediaSession.setActionHandler('nexttrack',()=>next());navigator.mediaSession.setActionHandler('previoustrack',prev);}catch(e){}
audio.addEventListener('play',()=>icons(true));audio.addEventListener('pause',()=>icons(false));audio.addEventListener('ended',()=>next(true));
audio.addEventListener('loadedmetadata',()=>$('duration').textContent=fmt(audio.duration));
audio.addEventListener('timeupdate',()=>{if(!Number.isFinite(audio.duration)||audio.duration<=0)return;let p=audio.currentTime/audio.duration*100;$('seek-fill').style.width=p+'%';$('seek-dot').style.left=p+'%';$('mini-progress').style.width=p+'%';$('elapsed').textContent=fmt(audio.currentTime);});
audio.addEventListener('error',()=>{if(audio.src)toast('Audio stream error. Try another track.');});
$('volume').addEventListener('input',e=>audio.volume=+e.target.value);audio.volume=.9;
function seek(x){if(!Number.isFinite(audio.duration)||audio.duration<=0)return;let r=$('seek').getBoundingClientRect();audio.currentTime=Math.max(0,Math.min(1,(x-r.left)/r.width))*audio.duration;}
let dragging=false;$('seek').addEventListener('pointerdown',e=>{dragging=true;$('seek').setPointerCapture(e.pointerId);seek(e.clientX);});$('seek').addEventListener('pointermove',e=>{if(dragging)seek(e.clientX);});$('seek').addEventListener('pointerup',()=>dragging=false);$('seek').addEventListener('pointercancel',()=>dragging=false);
$('search').addEventListener('input',e=>{let q=e.target.value.trim();$('clear').classList.toggle('show',!!q);clearTimeout(timer);timer=setTimeout(()=>search(q),300);});
$('search').addEventListener('keydown',e=>{if(e.key==='Enter'){clearTimeout(timer);search(e.target.value.trim());e.target.blur();}});
$('clear').addEventListener('click',()=>{$('search').value='';$('clear').classList.remove('show');search('');});
$('mini-info').addEventListener('click',()=>$('full').classList.add('show'));$('close').addEventListener('click',()=>$('full').classList.remove('show'));
['prev-mini','prev'].forEach(id=>$(id).addEventListener('click',prev));['next-mini','next'].forEach(id=>$(id).addEventListener('click',()=>next()));
['play-mini','play-full'].forEach(id=>$(id).addEventListener('click',toggle));
$('shuffle').addEventListener('click',()=>{shuffle=!shuffle;$('shuffle').classList.toggle('selected',shuffle);toast(shuffle?'Shuffle on':'Shuffle off');});
$('repeat').addEventListener('click',()=>{repeat=({off:'all',all:'one',one:'off'})[repeat];$('repeat').classList.toggle('selected',repeat!=='off');toast('Repeat '+repeat);});
document.addEventListener('keydown',e=>{if(e.target.matches('input'))return;if(e.code==='Space'){e.preventDefault();toggle();}if(e.code==='ArrowRight'&&Number.isFinite(audio.duration))audio.currentTime=Math.min(audio.duration,audio.currentTime+10);if(e.code==='ArrowLeft'&&Number.isFinite(audio.duration))audio.currentTime=Math.max(0,audio.currentTime-10);if(e.key==='Escape')$('full').classList.remove('show');});
trending();
</script></body></html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5003")), debug=False, threaded=True)