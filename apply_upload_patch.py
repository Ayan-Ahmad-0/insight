p = "web/index.html"
s = open(p, encoding="utf-8").read()

css = """
  /* upload view */
  .nav{display:inline-flex}
  select{font:inherit;width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
  .maps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:8px}
  .maps label{margin:0 0 4px}
  .step{margin-top:16px}
  .tbl{width:100%;border-collapse:collapse;font-size:14px;margin-top:6px}
  .tbl th,.tbl td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
  .errs{margin:8px 0 0;padding-left:18px;color:var(--red);font-size:14px}
  progress{width:100%;height:10px;accent-color:var(--green);margin-top:12px}
  #up-result{margin-top:12px}
"""
assert "</style>" in s
s = s.replace("</style>", css + "</style>", 1)

old_header = """<header class="topbar" id="topbar" hidden>
  <div class="brand">Insight</div>
  <button id="signout" class="btn">Sign out</button>
</header>"""
new_header = """<header class="topbar" id="topbar" hidden>
  <div class="brand">Insight</div>
  <div class="seg nav" role="group" aria-label="Pages">
    <button id="nav-dash" aria-pressed="true">Dashboard</button>
    <button id="nav-upload" aria-pressed="false" hidden>Upload data</button>
  </div>
  <button id="signout" class="btn">Sign out</button>
</header>"""
assert old_header in s; s = s.replace(old_header, new_header, 1)

assert '<div id="app" hidden>' in s
s = s.replace('<div id="app" hidden>', '<div id="app" hidden>\n    <div id="view-dashboard">', 1)

banner = '<div id="banner" class="banner" role="alert" hidden></div>'
empty = banner + """
    <div id="empty" class="panel" style="margin-top:16px" hidden>
      <h3>No usage data yet</h3>
      <p class="sub">Once events arrive, your numbers and charts appear here.</p>
      <button id="empty-upload" class="btn primary" type="button" hidden>Upload your data</button>
    </div>"""
assert banner in s; s = s.replace(banner, empty, 1)

old_tail = """    <p class="foot muted small">Numbers update once a day after the morning data run.</p>
  </div>
</main>"""
upload_view = """    <p class="foot muted small">Numbers update once a day after the morning data run.</p>
    </div>

    <div id="view-upload" hidden>
      <div class="page-head">
        <div>
          <h1>Upload your data</h1>
          <p class="muted">Add past usage from a CSV file. Uploading the same file twice never counts anything twice.</p>
        </div>
      </div>

      <div class="panel step">
        <h3>1. Get the template</h3>
        <p class="sub">One row per event: who used which feature, and when. Use anonymous user ids, not email addresses.</p>
        <button id="up-template" class="btn" type="button">Download template</button>
      </div>

      <div class="panel step">
        <h3>2. Choose your file</h3>
        <p class="sub">CSV, up to 5 MB and 20,000 rows per upload. Times like 2026-09-30T14:03:00Z or 2026-09-30 14:03.</p>
        <input id="up-file" type="file" accept=".csv,text/csv" aria-label="CSV file">
      </div>

      <div id="up-map" class="panel step" hidden>
        <h3>3. Match your columns</h3>
        <div class="maps">
          <div><label for="map-user">User</label><select id="map-user"></select></div>
          <div><label for="map-feature">Feature or action</label><select id="map-feature"></select></div>
          <div><label for="map-time">Time</label><select id="map-time"></select></div>
          <div><label for="map-id">Event id (optional)</label><select id="map-id"></select></div>
        </div>
        <label style="margin-top:14px;font-weight:400"><input id="up-utc" type="checkbox" checked> Times without a timezone are in UTC</label>
      </div>

      <div class="panel step">
        <h3>4. Check and import</h3>
        <div id="up-report" class="muted">Choose a file to see a check of its rows.</div>
        <div id="up-preview"></div>
        <div style="margin-top:14px"><button id="up-import" class="btn primary" type="button" disabled>Import</button></div>
        <progress id="up-progress" value="0" max="1" hidden></progress>
        <div id="up-result" aria-live="polite"></div>
      </div>
    </div>
  </div>
</main>"""
assert old_tail in s; s = s.replace(old_tail, upload_view, 1)

old = """  $("plan-line").textContent = `Product usage dashboard · ${pretty(me.plan)} plan`;
}"""
new = """  $("plan-line").textContent = `Product usage dashboard · ${pretty(me.plan)} plan`;
  initUpload(me);
}"""
assert old in s; s = s.replace(old, new, 1)

old = '    $("events-btn").hidden = !hasEvents();'
new = old + '\n    $("empty").hidden = state.daily.length > 0 || state.feats.length > 0;'
assert old in s; s = s.replace(old, new, 1)

old = '  session = null; $("ask-log").replaceChildren(); $("ask-clear").hidden = true;'
new = '  session = null; $("ask-log").replaceChildren(); $("ask-clear").hidden = true; resetUpload();'
assert old in s; s = s.replace(old, new, 1)

assert "</script>\n</body>" in s
s = s.replace("</script>\n</body>", '</script>\n<script src="upload.js"></script>\n</body>', 1)
open(p, "w", encoding="utf-8").write(s)
print("index.html patched")