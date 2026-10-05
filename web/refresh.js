// web/refresh.js - asks the API to rebuild the dashboard numbers, then waits for it to finish.
// Classic script, loaded after index.html's main script and upload.js (uses api(), el(), $(), loadAll(), showView()).

const REFRESH = {pollMs: 6000, maxMs: 12 * 60 * 1000, running: false};
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Returns "succeeded", "failed", "timeout", "busy" or "aborted" (signed out while waiting).
async function runRefresh(onState) {
  if (REFRESH.running) return "busy";
  REFRESH.running = true;
  try {
    onState("queued", "Starting the update…");
    const req = await api("/v1/refresh", {method: "POST"});
    const since = new Date(req.requested_at).toISOString();
    const t0 = Date.now();
    while (Date.now() - t0 < REFRESH.maxMs) {
      await sleep(REFRESH.pollMs);
      if (!session) return "aborted";
      const s = await api("/v1/refresh/status?since=" + encodeURIComponent(since));
      if (s.state === "succeeded") { onState("succeeded", "Your dashboard is up to date."); return "succeeded"; }
      if (s.state === "failed") { onState("failed", "The update did not finish. Your data is safe. Please try again."); return "failed"; }
      onState(s.state, s.state === "running"
        ? "Updating your dashboard. This usually takes about 2 minutes."
        : "Waiting for the update to start…");
    }
    onState("failed", "The update is taking longer than expected. Try again in a few minutes.");
    return "timeout";
  } catch (e) {
    if (!session) return "aborted";
    onState("failed", e.message);
    return "failed";
  } finally {
    REFRESH.running = false;
  }
}

const stateClass = s => s === "failed" ? "err" : s === "succeeded" ? "ok" : "muted";

// Used after an import: shows progress under the import summary.
function watchRefresh(box) {
  const msg = el("p", "", "muted");
  box.replaceChildren(msg);
  runRefresh((state, text) => { msg.textContent = text; msg.className = stateClass(state); }).then(result => {
    if (result === "aborted") return;
    if (result === "busy") { msg.textContent = "An update is already in progress. It will include your data if it starts after the import."; return; }
    if (result === "succeeded") {
      loadAll().catch(() => {});                       // numbers are ready, load them now
      const b = el("button", "View dashboard", "btn primary");
      b.type = "button"; b.onclick = () => showView("dashboard");
      box.append(b);
    } else {
      const b = el("button", "Try again", "btn");
      b.type = "button"; b.onclick = () => watchRefresh(box);
      box.append(b);
    }
  });
}

// "Update now" button on the dashboard (admins only).
function initRefresh(me) {
  const btn = $("refresh-btn"), msg = $("refresh-msg");
  btn.hidden = me.role !== "admin";
  btn.onclick = async () => {
    btn.disabled = true;
    const result = await runRefresh((state, text) => { msg.textContent = text; msg.className = "small " + stateClass(state); });
    btn.disabled = false;
    if (result === "succeeded") {
      await loadAll().catch(e => { msg.textContent = e.message; msg.className = "small err"; });
      setTimeout(() => { msg.textContent = ""; }, 5000);
    }
  };
}