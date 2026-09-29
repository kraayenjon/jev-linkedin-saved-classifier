"""The live board: watch the classifier sort saved posts into their categories.

Data comes only from what the classifier already produces: the primary category, Jev's
confidence, the per-tag probabilities, and the per-post model/latency/cost. Nothing here
invents a metric.

The server owns a small publish/subscribe bus. The reading loop calls publish() once per
classified post; every open browser receives those events over server-sent events, so the
page animates while the run happens.
"""

import json
import queue
import sys
import threading
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_HEADLINE = "your saved posts, sorted"


class Server(ThreadingHTTPServer):
    """Quiet when a browser tab closes mid-request; that is normal, not an error."""

    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


class Bus:
    """Fan-out of JSON events to every connected browser, replayed to newcomers."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers = set()
        self._history = []

    def subscribe(self):
        channel = queue.Queue()
        with self._lock:
            self._subscribers.add(channel)
            history = list(self._history)
        for event in history:
            channel.put(event)
        return channel

    def unsubscribe(self, channel):
        with self._lock:
            self._subscribers.discard(channel)

    def publish(self, event):
        # a named SSE frame, so the page's addEventListener(type) fires
        payload = f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        with self._lock:
            self._history.append(payload)
            subscribers = list(self._subscribers)
        for channel in subscribers:
            channel.put(payload)


def post_card(row, index):
    """The compact shape the board needs for one classified post."""
    jev = row.get("_jev") or {}
    return {
        "i": index,
        "urn": row.get("activity_urn"),
        "author": row.get("author") or "",
        "author_url": row.get("author_url"),
        "author_headline": row.get("author_headline") or "",
        "post_age": (row.get("post_age") or "").rstrip(" •"),
        "post_text": row.get("post_text") or "",
        "post_url": row.get("post_url") or "",
        "media_type": row.get("media_type") or "none",
        "media_thumb_url": row.get("media_thumb_url"),
        "avatar_url": row.get("avatar_url"),
        "category": row.get("category") or "(not classified)",
        "confidence": row.get("confidence"),
        "cost": jev.get("cost") or 0,
        "ms": jev.get("latency_ms", 0),
    }


def summary_event(rows, elapsed_ms, cost, model=None, board_url=None):
    """The closing slide: what the library looks like after the run."""
    named = [r for r in rows if r.get("category") and r.get("category") != "(not classified)"]
    counts = Counter(r["category"] for r in named)
    top = counts.most_common(1)[0] if counts else (None, 0)
    confidences = [r["confidence"] for r in rows if isinstance(r.get("confidence"), (int, float))]
    return {
        "type": "summary",
        "posts": len(rows),
        "classified": len(named),
        "categories_used": len(counts),
        "top_category": {"name": top[0], "count": top[1]} if top[0] else None,
        "mean_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "failed": sum(1 for r in rows if r.get("category") == "(failed)"),
        "elapsed_ms": elapsed_ms,
        "cost_usd": round(cost, 6),
        "model": model,
        "distribution": dict(counts.most_common()),
        "board_url": board_url,
    }


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__HEADLINE__</title>
<style>
:root {
  --bg:#d9d9d9; --ink:#101010; --line:#bdbdbd; --card:#f4f4f2; --white:#fff;
  --muted:#6f6f6f; --risk:#c43a1e;
  --mono:"SFMono-Regular", ui-monospace, "Roboto Mono", Menlo, monospace;
  --disp:-apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
}
* { box-sizing:border-box; }
html,body { margin:0; height:100%; }
body { background:var(--bg); color:var(--ink); font:14px/1.4 var(--disp); overflow:hidden; }
.stage { height:100vh; padding:22px 26px 26px; display:flex; flex-direction:column; gap:16px; }

.headline { font-size:56px; line-height:.98; letter-spacing:-.03em; font-weight:700; margin:0; }
.subtitle { color:var(--muted); font-size:15px; margin-top:6px; }

.kpis { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }
.tile { border:1px solid var(--ink); background:var(--white); padding:8px 12px 10px; min-height:74px; }
.tile.dark { background:var(--ink); color:var(--white); }
.tile .k { font:10px/1 var(--mono); letter-spacing:.14em; text-transform:uppercase; opacity:.62; }
.tile .v { font-size:40px; line-height:1.02; font-weight:700; letter-spacing:-.02em; margin-top:6px;
  font-variant-numeric:tabular-nums; white-space:nowrap; }
.tile .v .tail { color:#b9b9b9; }
.tile.dark .v .tail { color:#5d5d5d; }

.panels { flex:1; min-height:0; display:grid; grid-template-columns:1.5fr 1fr; gap:16px; }
.panel { border:1px solid var(--ink); background:var(--white); display:flex; flex-direction:column; min-height:0; }
.panel > header { display:flex; justify-content:space-between; align-items:baseline;
  font:10px/1 var(--mono); letter-spacing:.16em; text-transform:uppercase; padding:8px 10px;
  border-bottom:1px solid var(--line); color:var(--muted); }
.panel > header .n { color:var(--ink); }

/* Flex-wrap so tiles append left to right and a new row starts below the last. */
.grid { flex:1; min-height:0; overflow:auto; padding:10px; display:flex; flex-wrap:wrap;
  align-content:flex-start; gap:8px; }
.grid .cell { width:84px; flex:0 0 84px; }
/* Post media is mostly portrait, so the cell is portrait too and the image is not cropped. */
.cell { position:relative; aspect-ratio:3/4; border:1px solid var(--line); background:#efefec;
  overflow:hidden; opacity:0; transform:scale(.88); animation:pop .34s ease-out forwards; }
.cell img { width:100%; height:100%; object-fit:contain; display:block; }
.cell .txt { padding:6px; font-size:9px; line-height:1.3; color:#3a3a3a; overflow:hidden; height:100%; }
.cell .cat { position:absolute; left:0; right:0; bottom:0; font:8px/1.2 var(--mono); text-transform:uppercase;
  letter-spacing:.05em; color:#fff; padding:3px 4px; }
@keyframes pop { to { opacity:1; transform:scale(1); } }

.right { display:flex; flex-direction:column; gap:16px; min-height:0; }
.detail { flex:0 0 52%; min-height:0; }
.dt-body { flex:1; min-height:0; overflow:hidden; display:grid; grid-template-columns:180px 1fr; gap:14px; padding:12px; }
.dt-creative { border:1px solid var(--line); background:#efefec; overflow:hidden; position:relative; }
.dt-creative img { width:100%; height:100%; object-fit:cover; }
.dt-creative .fallback { padding:10px; font-size:11px; line-height:1.4; color:#4a4a4a; overflow:hidden; }
.dt-meta { min-width:0; display:flex; flex-direction:column; gap:3px; }
.dt-author { font-weight:600; font-size:15px; }
.dt-hl { color:var(--muted); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.dt-line { color:var(--muted); font:11px/1.5 var(--mono); }
.dt-text { margin-top:6px; font-size:12px; color:#333; overflow:hidden; max-height:6.4em; }
.bars { flex:1; min-height:0; overflow:auto; padding:12px 14px; display:flex; flex-direction:column; gap:9px; }
.bars .barhead { font:9px/1 var(--mono); letter-spacing:.16em; text-transform:uppercase; color:var(--muted); }
.bar { display:grid; grid-template-columns:150px 1fr 46px; align-items:center; gap:10px; }
.bar .name { font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar .track { height:7px; background:#e6e6e3; position:relative; }
.bar .fill { position:absolute; inset:0 auto 0 0; width:0; transition:width .4s ease; }
.bar .val { font:10px/1 var(--mono); text-align:right; color:var(--muted); }
.bar.pick .name { font-weight:700; }

.library { flex:1; min-height:0; }
.library .pool { flex:1; min-height:0; overflow:auto; padding:12px 14px; display:flex; flex-direction:column; gap:10px; }
.group .ghead { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }
.group .gname { font:10px/1 var(--mono); letter-spacing:.12em; text-transform:uppercase; color:var(--ink); }
.group .gcount { font:9px/1 var(--mono); color:var(--muted); }
.group .gbar { height:4px; background:#e6e6e3; position:relative; margin-bottom:6px; }
.group .gbar .gfill { position:absolute; inset:0 auto 0 0; width:0; transition:width .5s ease; }
.group .chips { display:flex; flex-wrap:wrap; gap:4px; }
.chip { font:8px/1.4 var(--mono); letter-spacing:.04em; border:1px solid var(--line); padding:2px 5px;
  color:#444; background:#fafaf8; opacity:0; animation:pop .3s ease-out forwards; }

.closing { position:fixed; inset:0; background:var(--bg); display:none; flex-direction:column;
  align-items:center; justify-content:center; gap:26px; z-index:20; }
.closing.on { display:flex; }
.closing .cards { display:grid; grid-template-columns:1fr 1fr; gap:14px; width:min(1080px,92vw); }
.closing .c { border:1px solid var(--ink); background:var(--white); padding:18px 20px; }
.closing .c .k { font:10px/1 var(--mono); letter-spacing:.16em; text-transform:uppercase; color:var(--muted); }
.closing .c .v { font-size:34px; font-weight:700; letter-spacing:-.02em; margin-top:10px; }
.closing .c .d { font:11px/1.4 var(--mono); color:var(--muted); margin-top:6px; }
.closing .sum { width:min(1080px,92vw); font-size:42px; line-height:1.04; letter-spacing:-.03em; font-weight:700; }
.closing .sum .muted { color:var(--muted); }
.empty { color:var(--muted); font-size:13px; padding:14px; }
.closing .open { align-self:flex-start; margin-left:max(4vw, calc(50vw - 540px)); background:var(--ink); color:var(--white);
  font-size:20px; font-weight:700; padding:14px 22px; text-decoration:none; }
.closing .open:hover { background:#333; }
</style></head><body>
<div class="stage">
  <div>
    <h1 class="headline">__HEADLINE__</h1>
    <div class="subtitle" id="subtitle">__SUBTITLE__</div>
  </div>

  <div class="kpis">
    <div class="tile dark"><div class="k">Saved posts read</div><div class="v" id="k-read">0</div></div>
    <div class="tile dark"><div class="k">Classified</div><div class="v" id="k-class">0</div></div>
    <div class="tile"><div class="k">Categories used</div><div class="v" id="k-cats">0</div></div>
    <div class="tile"><div class="k">Cost so far</div><div class="v" id="k-cost">$0.0000</div></div>
    <div class="tile"><div class="k">Elapsed</div><div class="v" id="k-elapsed">0.0<span class="tail">s</span></div></div>
  </div>

  <div class="panels">
    <section class="panel">
      <header><span>Saved posts</span><span class="n" id="ads-n">0</span></header>
      <div class="grid" id="grid"></div>
    </section>

    <div class="right">
      <section class="panel detail">
        <header><span>Last classified</span><span class="n" id="dt-ms">—</span></header>
        <div class="dt-body">
          <div class="dt-creative" id="dt-creative"><div class="fallback">waiting for the first post…</div></div>
          <div class="dt-meta">
            <div class="dt-author" id="dt-author">—</div>
            <div class="dt-hl" id="dt-hl"></div>
            <div class="dt-line" id="dt-line"></div>
            <div class="dt-text" id="dt-text"></div>
          </div>
        </div>
        <div class="bars" id="bars">
          <div class="barhead">Jev probability across your categories</div>
          <div class="empty" id="bars-empty">waiting…</div>
        </div>
      </section>

      <section class="panel library">
        <header><span>Your library</span><span class="n" id="lib-n">0 posts</span></header>
        <div class="pool" id="pool"><div class="empty">sorting…</div></div>
      </section>
    </div>
  </div>
</div>

<div class="closing" id="closing">
  <div class="cards" id="closing-cards"></div>
  <div class="sum" id="closing-sum"></div>
  <a class="open" id="closing-open" href="/board" hidden>Open your board: sort, filter, preview →</a>
</div>

<script>
const state = {
  read:0, classified:0, counts:{}, started:performance.now(), cost:0,
  order:[], conf:[], failed:0, frozen:false, frozenMs:0,
};
const $ = id => document.getElementById(id);

function kpi(el, text, tail) {
  if (tail) el.innerHTML = text + '<span class="tail">' + tail + '</span>';
  else el.textContent = text;
}
function elapsedSeconds() {
  return state.frozen ? state.frozenMs / 1000 : (performance.now() - state.started) / 1000;
}
function tick() {
  const elapsed = elapsedSeconds();
  kpi($('k-read'), state.read.toLocaleString());
  kpi($('k-class'), state.classified.toLocaleString());
  kpi($('k-cats'), Object.keys(state.counts).length.toLocaleString());
  kpi($('k-cost'), '$' + state.cost.toFixed(4));
  kpi($('k-elapsed'), state.frozen ? elapsed.toFixed(1) : elapsed.toFixed(1), 's');
}
setInterval(tick, 200);
tick();

function color(name) {
  let h = 0; for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h} 52% 42%)`;
}

function addCell(post) {
  const cell = document.createElement('div');
  cell.className = 'cell';
  if (post.media_thumb_url) {
    const img = document.createElement('img');
    img.loading = 'lazy'; img.src = post.media_thumb_url; img.alt = '';
    img.onerror = () => img.remove();
    cell.appendChild(img);
  } else {
    const txt = document.createElement('div');
    txt.className = 'txt';
    txt.textContent = (post.post_text || post.author || post.media_type || '').slice(0, 150);
    cell.appendChild(txt);
  }
  const cat = document.createElement('div');
  cat.className = 'cat';
  cat.textContent = post.category;
  cat.style.background = color(post.category);
  cell.appendChild(cat);
  const grid = $('grid');
  grid.appendChild(cell);
  grid.scrollTop = grid.scrollHeight;  // keep the newest row in view
  $('ads-n').textContent = state.read + ' / ' + state.read;
}

function renderDetail(post, ms, probs) {
  $('dt-ms').textContent = ms ? ms + ' ms' : '—';
  const creative = $('dt-creative'); creative.innerHTML = '';
  if (post.media_thumb_url) {
    const img = document.createElement('img'); img.src = post.media_thumb_url; img.alt = '';
    img.onerror = () => { creative.innerHTML = '<div class="fallback"></div>';
      creative.firstChild.textContent = (post.post_text || '').slice(0, 320); };
    creative.appendChild(img);
  } else {
    const fb = document.createElement('div'); fb.className = 'fallback';
    fb.textContent = (post.post_text || post.author || '').slice(0, 320);
    creative.appendChild(fb);
  }
  $('dt-author').textContent = post.author || '—';
  $('dt-hl').textContent = post.author_headline || '';
  $('dt-line').textContent = [post.post_age, post.media_type, post.category].filter(Boolean).join('  ·  ');
  $('dt-text').textContent = (post.post_text || '').slice(0, 240);

  const bars = $('bars'); bars.innerHTML = '<div class="barhead">Jev probability across your categories</div>';
  const entries = Object.entries(probs || {}).filter(([,v]) => v > 0).sort((a,b) => b[1]-a[1]).slice(0, 9);
  if (!entries.length) {
    bars.innerHTML += '<div class="empty">no distribution reported</div>';
    return;
  }
  for (const [name, p] of entries) {
    const row = document.createElement('div');
    row.className = 'bar' + (name === post.category ? ' pick' : '');
    row.innerHTML = `<div class="name">${name}</div>
      <div class="track"><div class="fill" style="background:${name === post.category ? color(name) : '#9a9a97'}"></div></div>
      <div class="val">${Math.round(p*100)}%</div>`;
    bars.appendChild(row);
    requestAnimationFrame(() => row.querySelector('.fill').style.width = Math.round(p*100) + '%');
  }
}

// ---- the library: one group per category, chips fill in as posts land ----
function renderLibrary() {
  const pool = $('pool');
  pool.innerHTML = '';
  const rows = state.order.filter(c => state.counts[c]);
  if (!rows.length) { pool.innerHTML = '<div class="empty">sorting…</div>'; return; }
  const max = Math.max(...rows.map(c => state.counts[c]));
  for (const name of rows) {
    const n = state.counts[name];
    const group = document.createElement('div'); group.className = 'group';
    group.innerHTML = `<div class="ghead"><span class="gname">${name}</span>
        <span class="gcount">${n} post${n === 1 ? '' : 's'} · ${Math.round(n/state.read*100)}%</span></div>
      <div class="gbar"><div class="gfill" style="background:${color(name)};width:${Math.round(n/max*100)}%"></div></div>
      <div class="chips"></div>`;
    const chips = group.querySelector('.chips');
    for (const chip of state.chips[name] || []) {
      const el = document.createElement('span'); el.className = 'chip';
      el.style.borderColor = color(name); el.style.color = color(name);
      el.textContent = chip;
      chips.appendChild(el);
    }
    pool.appendChild(group);
  }
  $('lib-n').textContent = state.read + ' posts · ' + Object.keys(state.counts).length + ' categories';
}
state.chips = {};

function onPost(d) {
  const post = d.post;
  state.read++;
  state.cost += post.cost || 0;
  state.chips[post.category] = state.chips[post.category] || [];
  const label = (post.author || '').split(' ')[0] || post.media_type;
  state.chips[post.category].push(label);
  if (!state.counts[post.category]) { state.counts[post.category] = 0; state.order.push(post.category); }
  state.counts[post.category]++;
  if (post.category !== '(failed)' && post.category !== '(not classified)') {
    state.classified++;
    if (typeof post.confidence === 'number') state.conf.push(post.confidence);
  }
  if (post.category === '(failed)') state.failed++;
  addCell(post);
  renderDetail(post, d.ms, d.probabilities || {});
  renderLibrary();
  tick();
}

function onSummary(s) {
  // Stop the clock on the last classified post; keep it if the run already froze.
  if (!state.frozen) { state.frozen = true; state.frozenMs = performance.now() - state.started; }
  tick();
  const card = (k, v, d) => `<div class="c"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`;
  const secs = (state.frozenMs / 1000).toFixed(1);
  const cards = [];
  if (s.top_category) cards.push(card('Where most of it lands', s.top_category.name,
    s.top_category.count + ' of ' + s.posts + ' posts'));
  if (s.mean_confidence != null) cards.push(card('Mean confidence', s.mean_confidence.toFixed(2),
    'across ' + s.classified + ' classified posts'));
  cards.push(card('Categories used', s.categories_used + ' of your tags',
    s.failed ? (s.failed + ' failed to classify') : 'none failed'));
  cards.push(card('What it cost', '$' + state.cost.toFixed(4),
    secs + ' seconds · ' + (s.model || 'jev')));
  $('closing-cards').innerHTML = cards.join('');
  $('closing-sum').innerHTML =
    `<span class="muted">your saved post can now be found.</span><br>` +
    `${s.posts} posts read · ${s.classified} classified · ${secs}s · $${state.cost.toFixed(4)}`;
  if (s.board_url) { $('closing-open').href = s.board_url; $('closing-open').hidden = false; }
  $('closing').classList.add('on');
  // Stay on the end frame; click anywhere to dismiss.
  $('closing').addEventListener('click', e => { if (!e.target.closest('a')) $('closing').classList.remove('on'); });
}

const es = new EventSource('/events');
es.addEventListener('post', e => onPost(JSON.parse(e.data)));
es.addEventListener('summary', e => onSummary(JSON.parse(e.data)));
es.addEventListener('end', () => es.close());
es.onerror = () => {};
</script>
</body></html>"""


def render_page(headline, subtitle):
    return PAGE.replace("__HEADLINE__", headline).replace("__SUBTITLE__", subtitle)


def serve(bus, tags, port, headline=DEFAULT_HEADLINE, subtitle=None, open_browser=True):
    """Serve the board and the event stream. Returns the ThreadingHTTPServer."""
    subtitle = subtitle or ("reading your saved posts and sorting them into "
                            + str(len(tags)) + " categories")
    page = render_page(headline, subtitle).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the run output clean
            pass

        def do_GET(self):
            if self.path.startswith("/events"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                channel = bus.subscribe()
                try:
                    while True:
                        try:
                            payload = channel.get(timeout=15)
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                            continue
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                except ConnectionError:
                    pass
                finally:
                    bus.unsubscribe(channel)
                return
            if self.path == "/board" and self.server.board:
                body = self.server.board.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return
            self.send_response(404)
            self.end_headers()

    try:
        server = Server(("127.0.0.1", port), Handler)
    except OSError as error:
        raise SystemExit(f"port {port} is busy ({error}); try --port {port + 1}") from None
    server.board = None  # set to the board html path once the run is written
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"\nlive dashboard: {url}")
    if open_browser:
        webbrowser.open(url)
    return server


def write_static(path: Path, rows, tags, elapsed_ms, cost, model=None, headline=DEFAULT_HEADLINE,
                 duration_s=None):
    """A self-contained replay of a finished run, for a recording or a share.

    duration_s compresses the whole replay into that many seconds (--demo uses 15), so a
    viewer sees the full 234-post run without waiting 103s. None keeps the real pace.
    """
    subtitle = "reading your saved posts and sorting them into " + str(len(tags)) + " categories"
    events = []
    for index, row in enumerate(rows, 1):
        jev = row.get("_jev") or {}
        events.append({
            "type": "post",
            "post": post_card(row, index),
            "probabilities": row.get("probabilities") or {},
            "ms": jev.get("latency_ms", 0) or 300,
        })
    events.append(summary_event(rows, elapsed_ms, cost, model))

    # A fixed gap per post when compressing; otherwise each post's own latency.
    if duration_s and rows:
        gap = max(int(duration_s * 1000 / len(rows)), 1)
    else:
        gap = None

    timeline = [json.dumps(e, ensure_ascii=False, default=str) for e in events]
    page = render_page(headline, subtitle).replace(
        "const es = new EventSource('/events');",
        "const HANDLERS = {};\n"
        "const es = { addEventListener:(t,f)=>{ (HANDLERS[t] ||= []).push(f); }, close:()=>{} };\n"
        "function checkpoint(ev){ for(const f of (HANDLERS[ev.type] || [])) f({data: JSON.stringify(ev)}); }")
    # Replay driver: deliver one event per post on a timer, so the counters and the clock
    # climb instead of jumping to the end. The summary event is last and stops the clock.
    gap_expr = "GAP" if gap is not None else "((ev.post && ev.post.ms) || 300)"
    driver = (
        "const TIMELINE = [" + ",".join(timeline) + "];\n"
        f"const GAP = {gap if gap is not None else 0};\n"
        "let ti = 0;\n"
        "function playNext(){ if (ti >= TIMELINE.length) return; const ev = TIMELINE[ti++];"
        " checkpoint(ev);"
        " const last = ev.type === 'summary';"
        f" setTimeout(playNext, last ? 0 : {gap_expr}); }}\n"
        "setTimeout(playNext, 400);")
    # The replay driver must run after every handler is registered, so it goes last.
    page = page.replace("</script>\n</body></html>", "\n" + driver + "\n</script>\n</body></html>")
    path.write_text(page, encoding="utf-8")
    return path
