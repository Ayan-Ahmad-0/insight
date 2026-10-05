// web/upload.js - CSV upload for organisation admins.
// Classic script, loaded after the main script in index.html. It uses the page's
// api(), el() and $() helpers. The organisation never comes from the file: the API
// takes it from the signed login token, and the database policy enforces it.

const UPLOAD_LIMITS = {bytes: 5 * 1024 * 1024, rows: 20000, batch: 500};
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ALIASES = {
  user: ["user_id", "userid", "user", "user id", "customer_id", "account_id", "member_id", "uid"],
  feature: ["feature", "event", "event_name", "action", "name", "page", "type"],
  time: ["occurred_at", "timestamp", "time", "date", "datetime", "created_at", "event_time"],
  id: ["event_id", "eventid", "id", "event_key"],
};

// ---------- pure helpers (unit-tested in node) ----------
function detectDelimiter(text) {
  const first = text.split(/\r?\n/, 1)[0] || "";
  const counts = [",", ";", "\t"].map(d => [d, first.split(d).length - 1]);
  counts.sort((a, b) => b[1] - a[1]);
  return counts[0][1] > 0 ? counts[0][0] : ",";
}

function parseCsv(text) {
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);       // Excel's byte-order mark
  const delim = detectDelimiter(text);
  const rows = []; let row = [], field = "", inQ = false;
  const endRow = () => { row.push(field); field = ""; if (row.some(v => v.trim() !== "")) rows.push(row); row = []; };
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false; }
      else field += c;
    } else if (c === '"' && field === "") inQ = true;
    else if (c === delim) { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; endRow(); }
    else field += c;
  }
  if (field !== "" || row.length) endRow();
  return rows;
}

function guessColumn(header, kind) {
  const names = header.map(h => String(h).trim().toLowerCase());
  for (const a of ALIASES[kind]) { const i = names.indexOf(a); if (i >= 0) return i; }
  return -1;
}

function normFeature(s) {
  const f = String(s).trim().toLowerCase().replace(/[\s/]+/g, "_").replace(/[^a-z0-9_.-]/g, "");
  if (!f) return {error: "feature name is empty"};
  if (f.length > 64) return {error: "feature name is longer than 64 characters"};
  return {value: f};
}

// Accepts 2026-09-30, 2026-09-30 14:03[:05], 2026-09-30T14:03:05Z, ...+05:00. Never guesses dd/mm vs mm/dd.
function parseTime(s, assumeUtc, now = Date.now()) {
  const m = String(s).trim().match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$/i);
  if (!m) return {error: "time must look like 2026-09-30 or 2026-09-30T14:03:00Z"};
  const Y = +m[1], Mo = +m[2], D = +m[3];
  const dateOnly = m[4] === undefined;
  const h = dateOnly ? 12 : +m[4], mi = dateOnly ? 0 : +m[5], sec = dateOnly ? 0 : +(m[6] || 0);
  const probe = new Date(Date.UTC(Y, Mo - 1, D));
  if (probe.getUTCFullYear() !== Y || probe.getUTCMonth() !== Mo - 1 || probe.getUTCDate() !== D)
    return {error: "not a real calendar date"};
  if (h > 23 || mi > 59 || sec > 59) return {error: "not a real time of day"};
  let offsetMin = 0;
  const tz = m[7];
  if (tz && tz.toUpperCase() !== "Z") {
    const t = tz.replace(":", "");
    offsetMin = (t[0] === "-" ? -1 : 1) * (+t.slice(1, 3) * 60 + +t.slice(3, 5));
  } else if (!tz && !dateOnly && !assumeUtc) {
    return {error: "time has no timezone (tick the UTC box if your times are in UTC)"};
  }
  const ms = Date.UTC(Y, Mo - 1, D, h, mi, sec) - offsetMin * 60000;
  if (Y < 2000) return {error: "year is before 2000"};
  if (ms > now + 60000) return {error: "time is in the future"};
  return {date: new Date(ms)};
}

const toHex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
const sha256hex = async str => toHex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str)));

// RFC 4122 version-5 UUID, identical to Python's uuid.uuid5(namespace, name).
async function uuid5(namespace, name) {
  const ns = namespace.replace(/-/g, "").match(/../g).map(h => parseInt(h, 16));
  const digest = new Uint8Array(await crypto.subtle.digest(
    "SHA-1", new Uint8Array([...ns, ...new TextEncoder().encode(name)])));
  digest[6] = (digest[6] & 0x0f) | 0x50;
  digest[8] = (digest[8] & 0x3f) | 0x80;
  const h = toHex(digest.slice(0, 16));
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
}

// rows: data rows (no header). map: column indexes. Returns only fields the API accepts.
async function buildEvents(rows, map, opts, orgId) {
  const events = [], errors = [], preview = [], seen = new Set(), users = new Map();
  let fileDupes = 0, first = null, last = null;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i], n = i + 1;
    const userRaw = String(r[map.user] ?? "").trim();
    if (!userRaw) { errors.push({row: n, msg: "user is empty"}); continue; }
    const f = normFeature(r[map.feature] ?? "");
    if (f.error) { errors.push({row: n, msg: f.error}); continue; }
    const t = parseTime(r[map.time] ?? "", opts.assumeUtc);
    if (t.error) { errors.push({row: n, msg: t.error}); continue; }
    if (!users.has(userRaw))
      users.set(userRaw, UUID_RE.test(userRaw) ? userRaw.toLowerCase() : await uuid5(orgId, userRaw));
    const iso = t.date.toISOString();
    const idRaw = map.id >= 0 ? String(r[map.id] ?? "").trim() : "";
    const key = "csv-" + (await sha256hex(idRaw ? `id|${idRaw}` : `${userRaw}|${f.value}|${iso}`)).slice(0, 32);
    if (seen.has(key)) { fileDupes++; continue; }
    seen.add(key);
    const ev = {user_id: users.get(userRaw), feature: f.value, occurred_at: iso, event_key: key};
    events.push(ev);
    if (preview.length < 5) preview.push({userRaw, ...ev});
    if (first === null || iso < first) first = iso;
    if (last === null || iso > last) last = iso;
  }
  return {events, errors, preview, fileDupes, first, last};
}

async function sendBatches(events, onProgress) {
  const totals = {received: 0, inserted: 0, duplicates: 0};
  for (let i = 0; i < events.length; i += UPLOAD_LIMITS.batch) {
    const chunk = events.slice(i, i + UPLOAD_LIMITS.batch);
    try {
      const res = await api("/v1/events", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({events: chunk})});
      totals.received += res.received; totals.inserted += res.inserted; totals.duplicates += res.duplicates;
    } catch (e) { e.partial = totals; throw e; }
    onProgress(Math.min(i + chunk.length, events.length), events.length);
  }
  return totals;
}

// ---------- UI (only runs in the browser) ----------
const up = {orgId: null, data: [], wired: false, run: 0, built: null, busy: false};

function showView(name) {
  $("view-dashboard").hidden = name !== "dashboard";
  $("view-upload").hidden = name !== "upload";
  $("nav-dash").setAttribute("aria-pressed", String(name === "dashboard"));
  $("nav-upload").setAttribute("aria-pressed", String(name === "upload"));
}

function fillSelect(sel, header, guess, placeholder) {
  sel.replaceChildren(new Option(placeholder, "-1"));
  header.forEach((h, i) => sel.append(new Option(String(h).trim() || `Column ${i + 1}`, String(i))));
  sel.value = String(guess);
}

function downloadTemplate() {
  const csv = "user_id,feature,occurred_at,event_id\r\n" +
    "u_1042,export_report,2026-09-30T14:03:00Z,evt-0001\r\n" +
    "u_1043,dashboard_view,2026-09-30T14:05:12Z,evt-0002\r\n";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type: "text/csv"}));
  a.download = "insight-upload-template.csv";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function renderPreview(items) {
  const box = $("up-preview"); box.replaceChildren();
  if (!items.length) return;
  const t = el("table", undefined, "tbl");
  const head = el("tr");
  ["User in your file", "Becomes", "Feature", "Time (UTC)"].forEach(h => head.append(el("th", h)));
  t.append(head);
  items.forEach(p => {
    const tr = el("tr");
    [p.userRaw, p.user_id.slice(0, 8) + "…", p.feature, p.occurred_at.replace("T", " ").replace(/\.000Z$/, "Z")]
      .forEach(v => tr.append(el("td", v)));
    t.append(tr);
  });
  box.append(el("p", "Preview of the first rows", "muted small"), t);
}

async function revalidate() {
  const run = ++up.run;
  const map = {user: +$("map-user").value, feature: +$("map-feature").value,
               time: +$("map-time").value, id: +$("map-id").value};
  const rep = $("up-report"); rep.replaceChildren();
  $("up-import").disabled = true; $("up-result").replaceChildren(); up.built = null;
  if (map.user < 0 || map.feature < 0 || map.time < 0) {
    rep.append(el("p", "Choose the columns that hold the user, the feature and the time.", "muted"));
    renderPreview([]); return;
  }
  if (!(globalThis.crypto && crypto.subtle)) {
    rep.append(el("p", "This browser can't run the checks here. Open the page over https and try again.", "err"));
    return;
  }
  const built = await buildEvents(up.data, map, {assumeUtc: $("up-utc").checked}, up.orgId);
  if (run !== up.run) return;                      // a newer choice replaced this one
  up.built = built;
  const lines = [
    `${up.data.length.toLocaleString()} rows read`,
    `${built.events.length.toLocaleString()} ready to import` +
      (built.first ? ` (${built.first.slice(0, 10)} to ${built.last.slice(0, 10)})` : ""),
    `${built.errors.length.toLocaleString()} rows will be skipped`];
  if (built.fileDupes) lines.push(`${built.fileDupes.toLocaleString()} repeated rows in the file count once`);
  lines.forEach(t => rep.append(el("div", t)));
  if (built.errors.length) {
    const ul = el("ul", undefined, "errs");
    built.errors.slice(0, 15).forEach(e => ul.append(el("li", `Row ${e.row}: ${e.msg}`)));
    if (built.errors.length > 15) ul.append(el("li", `…and ${built.errors.length - 15} more`));
    rep.append(ul);
  }
  renderPreview(built.preview);
  $("up-import").disabled = built.events.length === 0;
}

async function onFile(file) {
  $("up-result").replaceChildren(); $("up-refresh").replaceChildren(); $("up-report").replaceChildren(); renderPreview([]);
  $("up-import").disabled = true; $("up-map").hidden = true;
  if (!file) return;
  if (file.size > UPLOAD_LIMITS.bytes) {
    $("up-report").append(el("p", `That file is larger than ${UPLOAD_LIMITS.bytes / 1048576} MB. Split it and upload it in parts.`, "err")); return;
  }
  const rows = parseCsv(await file.text());
  if (rows.length < 2) { $("up-report").append(el("p", "The file needs a header row and at least one data row.", "err")); return; }
  if (rows.length - 1 > UPLOAD_LIMITS.rows) {
    $("up-report").append(el("p", `That file has ${(rows.length - 1).toLocaleString()} rows. The limit is ${UPLOAD_LIMITS.rows.toLocaleString()} per upload.`, "err")); return;
  }
  const header = rows[0]; up.data = rows.slice(1);
  fillSelect($("map-user"), header, guessColumn(header, "user"), "Choose a column…");
  fillSelect($("map-feature"), header, guessColumn(header, "feature"), "Choose a column…");
  fillSelect($("map-time"), header, guessColumn(header, "time"), "Choose a column…");
  fillSelect($("map-id"), header, guessColumn(header, "id"), "(none)");
  $("up-map").hidden = false;
  await revalidate();
}

async function runImport() {
  if (!up.built || !up.built.events.length || up.busy) return;
  up.busy = true; $("up-import").disabled = true;
  const out = $("up-result"); out.replaceChildren();
  const bar = $("up-progress"); bar.hidden = false; bar.max = up.built.events.length; bar.value = 0;
  try {
    const t = await sendBatches(up.built.events, (done) => { bar.value = done; });
    out.append(el("h3", "Import finished"),
      el("div", `${t.inserted.toLocaleString()} new events added`),
      el("div", `${t.duplicates.toLocaleString()} were already there`),
      el("div", `${up.built.errors.length.toLocaleString()} rows in your file were skipped`),
      el("p", "Uploading the same file again is safe.", "muted small"));
    if (t.inserted > 0) watchRefresh($("up-refresh"));
  } catch (e) {
    const sent = e.partial ? e.partial.received : 0;
    out.append(el("p", `Stopped: ${e.message}. ${sent.toLocaleString()} rows were sent before the problem. ` +
      "You can upload the same file again: events that were already added are not counted twice.", "err"));
  } finally {
    bar.hidden = true; up.busy = false; $("up-import").disabled = false;
  }
}

function initUpload(me) {
  up.orgId = me.org_id;
  $("nav-upload").hidden = me.role !== "admin";
  $("empty-upload").hidden = me.role !== "admin";
  if (up.wired) return;
  up.wired = true;
  $("nav-dash").onclick = () => showView("dashboard");
  $("nav-upload").onclick = () => showView("upload");
  $("empty-upload").onclick = () => showView("upload");
  $("up-template").onclick = downloadTemplate;
  $("up-file").onchange = e => onFile(e.target.files[0]);
  ["map-user", "map-feature", "map-time", "map-id", "up-utc"].forEach(id => { $(id).onchange = revalidate; });
  $("up-import").onclick = runImport;
}

function resetUpload() {
  up.data = []; up.built = null; up.run++;
  $("up-file").value = ""; $("up-map").hidden = true;
  ["up-report", "up-preview", "up-result", "up-refresh"].forEach(id => $(id).replaceChildren());
  $("up-import").disabled = true; showView("dashboard");
}

if (typeof module !== "undefined") {
  module.exports = {parseCsv, parseTime, normFeature, uuid5, buildEvents, guessColumn, detectDelimiter, sha256hex};
}