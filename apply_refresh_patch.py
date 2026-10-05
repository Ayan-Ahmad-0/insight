"""Run from the repo root: python apply_refresh_patch.py
Adds (1) session restore after a page refresh and (2) the 'update dashboard' flow to web/index.html and web/upload.js."""

def patch(path, edits):
    s = open(path, encoding="utf-8").read()
    for old, new in edits:
        assert s.count(old) == 1, f"{path}: anchor not found exactly once:\n{old[:80]}"
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)
    print("patched", path)

SESSION_JS = """
// ----- keep the session across page refreshes (this tab only) -----
function forgetSession() {
  const s = session; session = null;
  try { sessionStorage.removeItem(RT_KEY); } catch (e) {}
  if (s) fetch(`${CONFIG.SUPABASE_URL}/auth/v1/logout?scope=local`, {
    method: "POST", headers: {apikey: CONFIG.ANON_KEY, Authorization: `Bearer ${s.access_token}`}}).catch(() => {});
}

function showLogin(msg) {
  $("login").hidden = false; $("app").hidden = true; $("topbar").hidden = true;
  $("login-err").textContent = msg || "";
}

async function resume() {
  let rt = null;
  try { rt = sessionStorage.getItem(RT_KEY); } catch (e) {}
  if (!rt || session) return;                       // nothing saved, or the user already signed in
  $("login").hidden = true; $("app").hidden = false; $("topbar").hidden = false;
  $("status").textContent = "Restoring your session… the server may be waking up, this can take up to a minute.";
  try {
    await authCall("refresh_token", {refresh_token: rt});
  } catch (e) {
    if (e instanceof TypeError) { showLogin("Couldn't reach the server. Refresh the page to try again."); return; }
    try { sessionStorage.removeItem(RT_KEY); } catch (_) {}
    showLogin(""); return;
  }
  try { await loadAll(); }
  catch (e) { showLogin(e.message); }              // keeps the saved session, so refreshing again retries
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", resume);
else resume();
"""

patch("web/index.html", [
    ("let session = null;\n", 'let session = null;\nconst RT_KEY = "insight_rt";\n'),
    ("  session = await r.json();\n}",
     "  session = await r.json();\n  try { sessionStorage.setItem(RT_KEY, session.refresh_token); } catch (e) {}\n}"),
    ('  session = null; $("ask-log").replaceChildren(); $("ask-clear").hidden = true; resetUpload();',
     '  forgetSession(); $("ask-log").replaceChildren(); $("ask-clear").hidden = true; resetUpload();'),
    ("</script>\n<script src=\"upload.js\"></script>",
     SESSION_JS + "</script>\n<script src=\"upload.js\"></script>\n<script src=\"refresh.js\"></script>"),
    ('<button id="csv" class="btn">Download CSV</button>',
     '<button id="csv" class="btn">Download CSV</button>\n'
     '        <button id="refresh-btn" class="btn" type="button" hidden>Update now</button>\n'
     '        <span id="refresh-msg" class="muted small" aria-live="polite"></span>'),
    ("  initUpload(me);\n", "  initUpload(me);\n  initRefresh(me);\n"),
    ('<div id="up-result" aria-live="polite"></div>',
     '<div id="up-result" aria-live="polite"></div>\n        <div id="up-refresh" aria-live="polite"></div>'),
    ("  #up-result{margin-top:12px}\n", "  #up-result{margin-top:12px}\n  #up-refresh{margin-top:8px}\n  .ok{color:var(--green)}\n"),
])

patch("web/upload.js", [
    ('      el("p", "Your dashboard updates after the next daily refresh (03:00 UTC). Uploading the same file again is safe.", "muted small"));',
     '      el("p", "Uploading the same file again is safe.", "muted small"));\n'
     '    if (t.inserted > 0) watchRefresh($("up-refresh"));'),
    ('  $("up-result").replaceChildren(); $("up-report").replaceChildren(); renderPreview([]);',
     '  $("up-result").replaceChildren(); $("up-refresh").replaceChildren(); $("up-report").replaceChildren(); renderPreview([]);'),
    ('["up-report", "up-preview", "up-result"].forEach',
     '["up-report", "up-preview", "up-result", "up-refresh"].forEach'),
])