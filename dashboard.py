"""
Star Wars Timeline Dashboard — Canon + Legends
────────────────────────────────────────────────
Run:   python dashboard.py
Open:  http://localhost:5000
"""

from flask import Flask, jsonify, render_template_string, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone
import sqlite3, os, subprocess, threading, atexit

app = Flask(__name__)
DB_PATH      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "starwars_timeline.db")
CRAWLER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "./sw_crawler")

limiter = Limiter(get_remote_address, app=app,
                  default_limits=["300 per minute"], storage_uri="memory://")

crawl_lock   = threading.Lock()
crawl_status = {"running": False, "last_run": None, "last_result": None, "message": ""}


def run_crawler():
    if not crawl_lock.acquire(blocking=False):
        return
    crawl_status["running"] = True
    crawl_status["message"] = "Crawling…"
    try:
        result = subprocess.run([CRAWLER_PATH], capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            crawl_status["last_result"] = "ok"
            crawl_status["message"]     = "Crawl succeeded."
        else:
            crawl_status["last_result"] = "error"
            crawl_status["message"]     = result.stderr.strip() or "Crawler exited with error."
    except FileNotFoundError:
        crawl_status["last_result"] = "error"
        crawl_status["message"]     = f"Crawler binary not found at {CRAWLER_PATH}. Run 'make' first."
    except subprocess.TimeoutExpired:
        crawl_status["last_result"] = "error"
        crawl_status["message"]     = "Crawler timed out after 120 s."
    except Exception as e:
        crawl_status["last_result"] = "error"
        crawl_status["message"]     = str(e)
    finally:
        crawl_status["running"]  = False
        crawl_status["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        crawl_lock.release()


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(run_crawler, trigger="interval", hours=24, id="auto_crawl")
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.route("/api/entries")
def api_entries():
    rows = get_db().execute(
        "SELECT * FROM timeline WHERE active = 1 ORDER BY id"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/toggle/<int:eid>", methods=["POST"])
@limiter.limit("60 per minute")
def api_toggle(eid):
    conn = get_db()
    row  = conn.execute(
        "SELECT progress FROM timeline WHERE id = ? AND active = 1", (eid,)
    ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    new_progress = "" if row["progress"] == "Complete" else "Complete"
    completed_at = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if new_progress == "Complete" else None
    )
    conn.execute(
        "UPDATE timeline SET progress = ?, completed_at = ? WHERE id = ?",
        (new_progress, completed_at, eid),
    )
    conn.commit()
    return jsonify({"id": eid, "progress": new_progress, "completed_at": completed_at})


@app.route("/api/refresh", methods=["POST"])
@limiter.limit("6 per hour")
def api_refresh():
    if crawl_status["running"]:
        return jsonify({"status": "already_running"}), 409
    threading.Thread(target=run_crawler, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/crawl-status")
def api_crawl_status():
    return jsonify(crawl_status)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Galactic Media Archive</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Inconsolata:wght@300;400;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:        ##ffffff;
    --surface:   #f0f0ed;
    --border:    rgba(185,140,40,0.18);
    --gold:      #dbd6cf;
    --gold-hi:   #dbd6cf;
    --gold-dim:  rgba(201,144,42,0.35);
    --text:      #4e4b45;
    --muted:     #5a5648;
    --complete:  #3dba6f;
    --legends:   #a78bfa;
    --legends-d: rgba(167,139,250,0.3);
    --font-head: 'Rajdhani', sans-serif;
    --font-data: 'Inconsolata', monospace;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-data);
    font-size: 14px;
    min-height: 100vh;
    overflow-x: hidden;
  }

  body::before {
    content: '';
    position: fixed; inset: 0; z-index: 0;
    background-image:
      radial-gradient(1px 1px at 10% 15%,  rgba(255,255,255,0.55) 0%,transparent 100%),
      radial-gradient(1px 1px at 25% 60%,  rgba(255,255,255,0.35) 0%,transparent 100%),
      radial-gradient(1px 1px at 40% 30%,  rgba(255,255,255,0.45) 0%,transparent 100%),
      radial-gradient(1px 1px at 55% 80%,  rgba(255,255,255,0.30) 0%,transparent 100%),
      radial-gradient(1px 1px at 70% 10%,  rgba(255,255,255,0.50) 0%,transparent 100%),
      radial-gradient(1px 1px at 80% 50%,  rgba(255,255,255,0.40) 0%,transparent 100%),
      radial-gradient(1px 1px at 90% 70%,  rgba(255,255,255,0.30) 0%,transparent 100%),
      radial-gradient(1px 1px at 15% 85%,  rgba(255,255,255,0.25) 0%,transparent 100%),
      radial-gradient(1px 1px at 60% 45%,  rgba(255,255,255,0.35) 0%,transparent 100%),
      radial-gradient(1px 1px at 35% 92%,  rgba(255,255,255,0.20) 0%,transparent 100%),
      radial-gradient(1.5px 1.5px at 48% 22%, rgba(255,255,255,0.60) 0%,transparent 100%),
      radial-gradient(1.5px 1.5px at 77% 35%, rgba(255,255,255,0.55) 0%,transparent 100%),
      radial-gradient(2px 2px at 5%  50%,  rgba(255,255,255,0.70) 0%,transparent 100%),
      radial-gradient(2px 2px at 93% 20%,  rgba(255,255,255,0.65) 0%,transparent 100%);
    pointer-events: none;
  }

  .page-wrap {
    position: relative; z-index: 1;
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 24px 80px;
  }

  /* ── Header ── */
  header {
    position: sticky; top: 0; z-index: 100;
    background: bg;
    padding: 28px 0 0;
  }

  .header-inner {
    display: flex; align-items: flex-end;
    justify-content: space-between; gap: 24px; flex-wrap: wrap;
  }

  .brand { display: flex; flex-direction: column; gap: 4px; }

  .brand-sub {
    font-family: var(--font-data); font-size: 10px;
    letter-spacing: 0.3em; color: var(--gold);
    text-transform: uppercase; opacity: 0.8;
  }

  .brand-title {
    font-family: var(--font-head);
    font-size: clamp(24px,4vw,40px); font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--gold-hi);
    text-shadow: 0 0 40px rgba(240,192,64,0.3),0 0 80px rgba(240,192,64,0.1);
    line-height: 1;
  }

  .progress-block {
    display: flex; flex-direction: column; align-items: flex-end; gap: 6px;
    min-width: 200px;
  }

  .progress-label {
    font-family: var(--font-head); font-size: 13px;
    letter-spacing: 0.15em; color: var(--gold); text-transform: uppercase;
  }

  .progress-bar-outer {
    width: 200px; height: 4px;
    background: var(--border); border-radius: 2px; overflow: hidden;
  }

  .progress-bar-inner {
    height: 100%;
    background: linear-gradient(90deg, var(--gold), var(--gold-hi));
    border-radius: 2px; transition: width 0.4s ease;
    box-shadow: 0 0 8px rgba(240,192,64,0.4);
  }

  .progress-count {
    font-family: var(--font-data); font-size: 11px;
    color: var(--muted); letter-spacing: 0.1em;
  }

  /* ── Universe tabs ── */
  .universe-tabs {
    display: flex; gap: 0; margin-top: 20px;
    border-bottom: 1px solid var(--border);
  }

  .utab {
    font-family: var(--font-head); font-size: 13px; font-weight: 600;
    letter-spacing: 0.15em; text-transform: uppercase;
    padding: 10px 22px 9px;
    border: none; background: transparent;
    color: var(--muted); cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color 0.15s, border-color 0.15s;
  }
  .utab:hover { color: var(--text); }
  .utab.active-canon   { color: var(--gold-hi);  border-bottom-color: var(--gold-hi); }
  .utab.active-legends { color: var(--legends);  border-bottom-color: var(--legends); }
  .utab.active-both    { color: var(--text);     border-bottom-color: var(--text); }

  .divider { border: none; border-top: 1px solid var(--border); margin: 0 0 20px; }

  /* ── Controls ── */
  .controls {
    display: flex; align-items: center;
    gap: 10px; flex-wrap: wrap; margin-bottom: 20px;
  }

  .search-wrap {
    position: relative; flex: 1; min-width: 200px; max-width: 320px;
  }

  .search-wrap svg {
    position: absolute; left: 10px; top: 50%;
    transform: translateY(-50%); color: var(--muted); pointer-events: none;
  }

  .search-input {
    width: 100%; background: var(--surface);
    border: 1px solid var(--border); border-radius: 4px;
    color: var(--text); font-family: var(--font-data); font-size: 13px;
    padding: 7px 12px 7px 32px; outline: none; transition: border-color 0.2s;
  }
  .search-input:focus { border-color: var(--gold-dim); }
  .search-input::placeholder { color: var(--muted); }

  /* Type filter pills — multi-select: active = SHOWN, inactive = hidden */
  .type-filters { display: flex; gap: 5px; flex-wrap: wrap; }

  .pill {
    font-family: var(--font-head); font-size: 11px; font-weight: 600;
    letter-spacing: 0.1em; text-transform: uppercase;
    padding: 4px 10px; border-radius: 2px;
    border: 1px solid var(--border); background: transparent;
    color: var(--muted); cursor: pointer; transition: all 0.15s;
    white-space: nowrap; user-select: none;
  }
  /* Active = included in view */
  .pill.on { background: var(--gold-dim); border-color: var(--gold); color: var(--gold-hi); }
  .pill:hover { border-color: var(--gold-dim); color: var(--gold); }
  .pill:disabled { opacity: 0.4; cursor: not-allowed; }

  .ctrl-pill {
    font-family: var(--font-head); font-size: 11px; font-weight: 600;
    letter-spacing: 0.1em; text-transform: uppercase;
    padding: 4px 10px; border-radius: 2px;
    border: 1px solid var(--border); background: transparent;
    color: var(--muted); cursor: pointer; transition: all 0.15s;
    white-space: nowrap;
  }
  .ctrl-pill:hover { border-color: var(--gold-dim); color: var(--gold); }
  .ctrl-pill.active { background: var(--gold-dim); border-color: var(--gold); color: var(--gold-hi); }

  /* Refresh */
  .refresh-btn {
    font-family: var(--font-head); font-size: 11px; font-weight: 600;
    letter-spacing: 0.1em; text-transform: uppercase;
    padding: 4px 12px; border-radius: 2px;
    border: 1px solid rgba(61,186,111,0.35); background: transparent;
    color: var(--complete); cursor: pointer; transition: all 0.15s;
    display: flex; align-items: center; gap: 5px;
  }
  .refresh-btn:hover:not(:disabled) { background: rgba(61,186,111,0.1); border-color: var(--complete); }
  .refresh-btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .refresh-btn.spinning svg { animation: spin 0.8s linear infinite; }

  /* ── Crawl banner ── */
  .crawl-banner {
    font-size: 11px; letter-spacing: 0.08em;
    padding: 7px 14px; border-radius: 3px;
    margin-bottom: 14px; border: 1px solid; display: none;
  }
  .crawl-banner.show    { display: block; }
  .crawl-banner.running { color: var(--gold);    border-color: var(--gold-dim);       background: rgba(201,144,42,0.07); }
  .crawl-banner.ok      { color: var(--complete); border-color: rgba(61,186,111,0.3); background: rgba(61,186,111,0.07); }
  .crawl-banner.error   { color: #e06c75;         border-color: rgba(224,108,117,0.3);background: rgba(224,108,117,0.07); }

  /* ── Stats ── */
  .stats-strip { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }

  .stat-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 4px; padding: 10px 16px;
    display: flex; flex-direction: column; gap: 2px;
  }

  .stat-value {
    font-family: var(--font-head); font-size: 22px; font-weight: 700;
    color: var(--gold-hi); line-height: 1;
  }

  .stat-label {
    font-size: 10px; letter-spacing: 0.2em;
    text-transform: uppercase; color: var(--muted);
  }

  /* ── Table ── */
  .table-wrap {
    border: 1px solid var(--border); border-radius: 6px;
    overflow: hidden; background: var(--surface);
  }

  table { width: 100%; border-collapse: collapse; }

  thead th {
    font-family: var(--font-head); font-size: 11px; font-weight: 600;
    letter-spacing: 0.2em; text-transform: uppercase;
    color: var(--gold); text-align: left;
    padding: 11px 14px;
    background: rgba(201,144,42,0.05);
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }

  thead th.col-check  { width: 48px; text-align: center; }
  thead th.col-num    { width: 48px; }
  thead th.col-univ   { width: 90px; }
  thead th.col-year   { width: 170px; }
  thead th.col-type   { width: 96px; }
  thead th.col-rel    { width: 130px; }

  /* Sortable header */
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: var(--gold-hi); }
  th.sortable .sort-icon { margin-left: 4px; opacity: 0.4; font-style: normal; }
  th.sortable.asc  .sort-icon::after { content: '↑'; opacity: 1; }
  th.sortable.desc .sort-icon::after { content: '↓'; opacity: 1; }
  th.sortable:not(.asc):not(.desc) .sort-icon::after { content: '↕'; }

  tbody tr {
    border-bottom: 1px solid rgba(185,140,40,0.07);
    transition: background 0.15s, opacity 0.2s;
  }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover  { background: rgba(201,144,42,0.04); }
  tbody tr.done   { opacity: 0.45; }

  td {
    padding: 8px 14px; vertical-align: middle;
    font-size: 13px; color: var(--text);
  }

  td.col-num  { color: var(--muted); font-size: 11px; }
  td.col-year { color: var(--muted); font-size: 12px; }
  td.col-rel  { color: var(--muted); font-size: 12px; white-space: nowrap; }
  td.col-check { text-align: center; }
  td.col-title { max-width: 400px; }

  .title-cell { display: flex; flex-direction: column; gap: 2px; }
  .title-text {
    display: block; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; max-width: 400px;
  }
  .done .title-text { text-decoration: line-through; }
  .completed-on { font-size: 10px; color: var(--complete); opacity: 0.7; }

  /* ── Universe badge ── */
  .univ-badge {
    font-family: var(--font-head); font-size: 9px; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase;
    padding: 1px 5px; border-radius: 2px; border: 1px solid;
  }
  .univ-canon   { color: var(--gold);    border-color: var(--gold-dim);   background: rgba(201,144,42,0.07); }
  .univ-legends { color: var(--legends); border-color: var(--legends-d);  background: rgba(167,139,250,0.07); }

  /* ── Type badge ── */
  .badge {
    display: inline-block; font-family: var(--font-head);
    font-size: 10px; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; padding: 2px 6px;
    border-radius: 2px; border: 1px solid; white-space: nowrap;
  }
  .badge-TV { color:#60a5fa; border-color:rgba(96,165,250,0.3);  background:rgba(96,165,250,0.07); }
  .badge-F  { color:var(--gold-hi); border-color:var(--gold-dim); background:rgba(240,192,64,0.07); }
  .badge-N  { color:#c084fc; border-color:rgba(192,132,252,0.3); background:rgba(192,132,252,0.07); }
  .badge-C  { color:#fb923c; border-color:rgba(251,146,60,0.3);  background:rgba(251,146,60,0.07); }
  .badge-SS { color:#2dd4bf; border-color:rgba(45,212,191,0.3);  background:rgba(45,212,191,0.07); }
  .badge-VG { color:#4ade80; border-color:rgba(74,222,128,0.3);  background:rgba(74,222,128,0.07); }
  .badge-A  { color:#f472b6; border-color:rgba(244,114,182,0.3); background:rgba(244,114,182,0.07); }
  .badge-JR { color:#7dd3fc; border-color:rgba(125,211,252,0.3); background:rgba(125,211,252,0.07); }
  .badge-   { color:var(--muted); border-color:var(--border); background:transparent; }

  /* ── Check button ── */
  .check-btn {
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px; border-radius: 4px;
    border: 1.5px solid var(--border); background: transparent;
    cursor: pointer; color: transparent;
    transition: border-color 0.15s, background 0.15s, color 0.15s;
  }
  .check-btn:hover { border-color: var(--complete); }
  .check-btn.checked {
    background: rgba(61,186,111,0.12);
    border-color: var(--complete); color: var(--complete);
  }
  .check-btn svg { width: 13px; height: 13px; stroke-width: 2.5; }

  /* ── States ── */
  .state-row td {
    text-align: center; padding: 60px 20px;
    color: var(--muted); letter-spacing: 0.1em; font-size: 13px;
  }

  .spinner {
    display: inline-block; width: 18px; height: 18px;
    border: 2px solid var(--border); border-top-color: var(--gold);
    border-radius: 50%; animation: spin 0.7s linear infinite;
    vertical-align: middle; margin-right: 8px;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  tbody tr { animation: row-in 0.2s ease both; }
  @keyframes row-in { from { opacity:0; transform:translateY(3px); } to { opacity:1; transform:none; } }
  tbody tr.done { animation: none; }

  footer {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: linear-gradient(0deg,#05060c 70%,transparent 100%);
    padding: 14px 24px; z-index: 50; pointer-events: none;
  }
  .footer-inner {
    max-width: 1400px; margin: 0 auto; font-size: 10px;
    letter-spacing: 0.15em; color: rgba(90,86,72,0.6);
    text-transform: uppercase; display: flex;
    justify-content: space-between; align-items: center;
  }
</style>
</head>
<body>
<div class="page-wrap">

  <!-- Header -->
  <header>
    <div class="header-inner">
      <div class="brand">
        <span class="brand-sub">Holonet Records — Galactic Standard Calendar</span>
        <h1 class="brand-title">Canon &amp; Legends Archive</h1>
      </div>
      <div class="progress-block">
        <span class="progress-label">Mission Progress</span>
        <div class="progress-bar-outer">
          <div class="progress-bar-inner" id="progressBar" style="width:0%"></div>
        </div>
        <span class="progress-count" id="progressCount">—</span>
      </div>
    </div>

    <!-- Universe tabs -->
    <div class="universe-tabs">
      <button class="utab active-canon" data-universe="canon">Canon</button>
      <button class="utab" data-universe="legends">Legends</button>
      <button class="utab" data-universe="both">Both</button>
    </div>
  </header>

  <!-- Stats -->
  <div class="stats-strip" style="margin-top:20px">
    <div class="stat-card"><span class="stat-value" id="statTotal">—</span><span class="stat-label">Shown</span></div>
    <div class="stat-card"><span class="stat-value" id="statDone">—</span><span class="stat-label">Completed</span></div>
    <div class="stat-card"><span class="stat-value" id="statLeft">—</span><span class="stat-label">Remaining</span></div>
  </div>

  <!-- Controls -->
  <div class="controls">
    <div class="search-wrap">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
      </svg>
      <input class="search-input" type="text" id="searchInput" placeholder="Search titles…">
    </div>

    <!-- Type filter pills (multi-select) -->
    <div class="type-filters" id="typeFilters">
      <button class="pill on" data-type="TV">Series</button>
      <button class="pill on" data-type="F">Film</button>
      <button class="pill on" data-type="N">Novel</button>
      <button class="pill on" data-type="C">Comic</button>
      <button class="pill on" data-type="SS">Short</button>
      <button class="pill on" data-type="VG">Game</button>
      <button class="pill on" data-type="A">Audio</button>
      <button class="pill on" data-type="JR">Jr Reader</button>
    </div>

    <button class="ctrl-pill" id="toggleDone">Hide Completed</button>

    <button class="refresh-btn" id="refreshBtn" title="Re-crawl the wiki now">
      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2.5"
           stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 4 23 10 17 10"/>
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
      </svg>
      Refresh
    </button>
  </div>

  <!-- Crawl banner -->
  <div class="crawl-banner" id="crawlBanner"></div>

  <!-- Table -->
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th class="col-check">Done</th>
          <th class="col-num">#</th>
          <th class="col-univ">Universe</th>
          <th class="col-year">Era</th>
          <th class="col-type">Type</th>
          <th>Title</th>
          <th class="col-rel sortable" id="sortReleased">
            Released <i class="sort-icon"></i>
          </th>
        </tr>
      </thead>
      <tbody id="tbody">
        <tr class="state-row">
          <td colspan="7"><span class="spinner"></span> Loading archive…</td>
        </tr>
      </tbody>
    </table>
  </div>

</div>

<footer>
  <div class="footer-inner">
    <span>Star Wars Canon &amp; Legends Timeline</span>
    <span id="lastCrawlTime"></span>
  </div>
</footer>

<script>
  // ── State ──────────────────────────────────────────────────────────────────
  let allEntries   = [];
  let activeUniverse = 'canon';           // 'canon' | 'legends' | 'both'
  let activeTypes  = new Set(['TV','F','N','C','SS','VG','A','JR']);
  let searchTerm   = '';
  let hideDone     = false;
  let sortDir      = null;                // null | 'asc' | 'desc'

  const pendingToggles = new Set();
  let   crawlPollTimer = null;

  const TYPE_LABEL = {
    TV:'Series', F:'Film', N:'Novel', C:'Comic',
    SS:'Short',  VG:'Game', A:'Audio', JR:'Jr Reader', '':'—'
  };

  // ── Date parser for sorting ────────────────────────────────────────────────
  // Returns a sortable integer (ms since epoch) or 0 if unparseable.
  function parseDateMs(str) {
    if (!str) return 0;
    const d = new Date(str);
    if (!isNaN(d)) return d.getTime();
    // Try "Month YYYY" or "YYYY"
    const m = str.match(/(\w+)\s+(\d{4})/);
    if (m) { const d2 = new Date(`${m[1]} 1, ${m[2]}`); if (!isNaN(d2)) return d2.getTime(); }
    const y = str.match(/\d{4}/);
    if (y) return new Date(`${y[0]}-01-01`).getTime();
    return 0;
  }

  // ── Load ───────────────────────────────────────────────────────────────────
  async function loadEntries() {
    try {
      allEntries = await fetch('/api/entries').then(r => r.json());
      render();
    } catch {
      document.getElementById('tbody').innerHTML =
        `<tr class="state-row"><td colspan="7">⚠ Could not reach the database.</td></tr>`;
    }
  }

  // ── Stats ──────────────────────────────────────────────────────────────────
  function updateStats(visible) {
    const done  = visible.filter(e => e.progress === 'Complete').length;
    const total = visible.length;
    const allDone  = allEntries.filter(e => e.progress === 'Complete').length;
    const allTotal = allEntries.length;
    const pct   = allTotal ? Math.round((allDone / allTotal) * 100) : 0;
    document.getElementById('progressBar').style.width   = pct + '%';
    document.getElementById('progressCount').textContent = `${allDone} / ${allTotal} (${pct}%)`;
    document.getElementById('statTotal').textContent = total;
    document.getElementById('statDone').textContent  = done;
    document.getElementById('statLeft').textContent  = total - done;
  }

  // ── Toggle ─────────────────────────────────────────────────────────────────
  async function toggleEntry(id) {
    if (pendingToggles.has(id)) return;
    pendingToggles.add(id);

    const entry = allEntries.find(e => e.id === id);
    if (!entry) { pendingToggles.delete(id); return; }

    const newDone      = entry.progress !== 'Complete';
    entry.progress     = newDone ? 'Complete' : '';
    entry.completed_at = newDone ? new Date().toISOString() : null;

    const row = document.querySelector(`tr[data-id="${id}"]`);
    if (row) {
      applyRowState(row, entry);
      if (hideDone && newDone) {
        row.style.transition = 'opacity 0.3s';
        row.style.opacity    = '0';
        setTimeout(() => { row.remove(); updateStats(visibleEntries()); }, 310);
      }
    }
    updateStats(visibleEntries());

    try {
      const data = await fetch(`/api/toggle/${id}`, { method:'POST' }).then(r => r.json());
      entry.completed_at = data.completed_at;
      if (row && row.isConnected) {
        const ts = row.querySelector('.completed-on');
        if (ts) ts.textContent = fmtDone(data.completed_at);
      }
    } catch {
      entry.progress     = newDone ? '' : 'Complete';
      entry.completed_at = null;
      updateStats(visibleEntries());
      if (row && row.isConnected) applyRowState(row, entry);
    } finally {
      pendingToggles.delete(id);
    }
  }

  function applyRowState(row, entry) {
    const isDone = entry.progress === 'Complete';
    row.classList.toggle('done', isDone);
    const btn = row.querySelector('.check-btn');
    if (btn) { btn.classList.toggle('checked', isDone); btn.title = isDone ? 'Mark incomplete':'Mark complete'; }
    const ts = row.querySelector('.completed-on');
    if (ts) { ts.textContent = isDone ? fmtDone(entry.completed_at) : ''; ts.style.display = isDone ? '' : 'none'; }
  }

  // ── Filter helper ──────────────────────────────────────────────────────────
  function visibleEntries() {
    const search = searchTerm.toLowerCase();
    return allEntries.filter(e => {
      if (activeUniverse !== 'both' && e.universe !== activeUniverse) return false;
      const typeKey = (e.type || '').trim();
      if (!activeTypes.has(typeKey) && typeKey !== '') return false;
      if (hideDone && e.progress === 'Complete') return false;
      if (search && !e.title.toLowerCase().includes(search) &&
                    !(e.year||'').toLowerCase().includes(search)) return false;
      return true;
    });
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  function render() {
    let visible = visibleEntries();

    // Sort by release date if active
    if (sortDir) {
      visible = [...visible].sort((a, b) => {
        const da = parseDateMs(a.released), db2 = parseDateMs(b.released);
        return sortDir === 'asc' ? da - db2 : db2 - da;
      });
    }

    updateStats(visible);

    if (!visible.length) {
      document.getElementById('tbody').innerHTML =
        `<tr class="state-row"><td colspan="7">No entries match the current filter.</td></tr>`;
      return;
    }

    const rows = visible.map((e, i) => {
      const isDone   = e.progress === 'Complete';
      const typeKey  = (e.type || '').trim();
      const label    = TYPE_LABEL[typeKey] ?? typeKey;
      const univCls  = e.universe === 'legends' ? 'univ-legends' : 'univ-canon';
      const univLbl  = e.universe === 'legends' ? 'Legends' : 'Canon';
      const doneDate = isDone ? fmtDone(e.completed_at) : '';

      return `<tr class="${isDone?'done':''}" data-id="${e.id}" style="animation-delay:${Math.min(i*6,180)}ms">
          <td class="col-check">
            <button class="check-btn ${isDone?'checked':''}" onclick="toggleEntry(${e.id})"
                    title="${isDone?'Mark incomplete':'Mark complete'}">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </button>
          </td>
          <td class="col-num">${String(e.id).padStart(4,'0')}</td>
          <td class="col-univ"><span class="univ-badge ${univCls}">${univLbl}</span></td>
          <td class="col-year">${esc(e.year||'—')}</td>
          <td><span class="badge badge-${typeKey}">${label}</span></td>
          <td class="col-title">
            <div class="title-cell">
              <span class="title-text" title="${esc(e.title)}">${esc(e.title)}</span>
              <span class="completed-on" style="${isDone?'':'display:none'}">${doneDate}</span>
            </div>
          </td>
          <td class="col-rel">${esc(e.released||'—')}</td>
        </tr>`;
    });

    document.getElementById('tbody').innerHTML = rows.join('');
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function fmtDone(iso) {
    if (!iso) return '';
    try { return '✓ ' + new Date(iso).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}); }
    catch { return ''; }
  }

  // ── Universe tabs ──────────────────────────────────────────────────────────
  document.querySelectorAll('.utab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.utab').forEach(b => b.className = 'utab');
      activeUniverse = btn.dataset.universe;
      btn.classList.add(`active-${activeUniverse}`);
      render();
    });
  });

  // ── Type filter pills (multi-select toggle) ────────────────────────────────
  document.getElementById('typeFilters').addEventListener('click', e => {
    const pill = e.target.closest('.pill[data-type]');
    if (!pill) return;
    const t = pill.dataset.type;
    if (activeTypes.has(t)) {
      // Don't allow deselecting the last type
      if (activeTypes.size === 1) return;
      activeTypes.delete(t);
      pill.classList.remove('on');
    } else {
      activeTypes.add(t);
      pill.classList.add('on');
    }
    render();
  });

  // ── Search ─────────────────────────────────────────────────────────────────
  document.getElementById('searchInput').addEventListener('input', e => {
    searchTerm = e.target.value;
    render();
  });

  // ── Hide completed ─────────────────────────────────────────────────────────
  document.getElementById('toggleDone').addEventListener('click', function() {
    hideDone = !hideDone;
    this.textContent = hideDone ? 'Show Completed' : 'Hide Completed';
    this.classList.toggle('active', hideDone);
    render();
  });

  // ── Sort by release date ───────────────────────────────────────────────────
  document.getElementById('sortReleased').addEventListener('click', function() {
    if      (!sortDir)         sortDir = 'asc';
    else if (sortDir === 'asc') sortDir = 'desc';
    else                        sortDir = null;

    this.classList.remove('asc','desc');
    if (sortDir) this.classList.add(sortDir);
    render();
  });

  // ── Refresh / crawl polling ────────────────────────────────────────────────
  const banner     = document.getElementById('crawlBanner');
  const refreshBtn = document.getElementById('refreshBtn');

  function showBanner(type, msg) { banner.className = `crawl-banner show ${type}`; banner.textContent = msg; }
  function hideBanner()          { banner.className = 'crawl-banner'; }
  function setRefreshBusy(b)     { refreshBtn.disabled = b; refreshBtn.classList.toggle('spinning', b); }

  async function pollCrawlStatus() {
    try {
      const data = await fetch('/api/crawl-status').then(r => r.json());
      if (data.last_run)
        document.getElementById('lastCrawlTime').textContent = 'Last crawl: ' + fmtDone(data.last_run);
      if (data.running) {
        showBanner('running','⟳  Crawling wiki (Canon + Legends)…');
        setRefreshBusy(true);
        crawlPollTimer = setTimeout(pollCrawlStatus, 1500);
      } else {
        setRefreshBusy(false);
        if (data.last_result === 'ok') {
          showBanner('ok','✓  Crawl complete — reloading entries…');
          await loadEntries();
          setTimeout(hideBanner, 4000);
        } else if (data.last_result === 'error') {
          showBanner('error','✗  Crawl failed: ' + data.message);
        }
      }
    } catch { setRefreshBusy(false); showBanner('error','✗  Could not reach server.'); }
  }

  refreshBtn.addEventListener('click', async () => {
    clearTimeout(crawlPollTimer);
    setRefreshBusy(true);
    showBanner('running','⟳  Starting crawl…');
    try {
      const res = await fetch('/api/refresh', { method:'POST' });
      if (res.status === 409) showBanner('running','⟳  A crawl is already running…');
    } catch { showBanner('error','✗  Could not contact server.'); setRefreshBusy(false); return; }
    crawlPollTimer = setTimeout(pollCrawlStatus, 1000);
  });

  // Restore last-crawl time on load
  fetch('/api/crawl-status').then(r=>r.json()).then(data => {
    if (data.last_run)
      document.getElementById('lastCrawlTime').textContent = 'Last crawl: ' + fmtDone(data.last_run);
    if (data.running) { setRefreshBusy(true); showBanner('running','⟳  Background crawl in progress…'); crawlPollTimer = setTimeout(pollCrawlStatus,1500); }
  }).catch(()=>{});

  loadEntries();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"[!] Database not found at {DB_PATH}")
        print("[!] Run ./sw_crawler first to populate it.")
    app.run(host="0.0.0.0", port=5000, debug=True)