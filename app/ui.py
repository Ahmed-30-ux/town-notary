UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Town Notary</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#0a0a0f; color:#e0e0e0; }
  .container { max-width:960px; margin:0 auto; padding:2rem; }
  h1 { font-size:2rem; background:linear-gradient(135deg,#a78bfa,#60a5fa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:.5rem; }
  .subtitle { color:#888; margin-bottom:2rem; }
  .card { background:#14141f; border:1px solid #2a2a3a; border-radius:12px; padding:1.5rem; margin-bottom:1.5rem; }
  .card h2 { font-size:1.2rem; margin-bottom:1rem; color:#a78bfa; }
  label { display:block; font-size:.85rem; color:#888; margin-bottom:.3rem; }
  input,textarea,select { width:100%; padding:.6rem; background:#1a1a28; border:1px solid #333; border-radius:8px; color:#e0e0e0; font-size:.9rem; margin-bottom:1rem; }
  textarea { font-family:monospace; resize:vertical; min-height:60px; }
  button { background:#a78bfa; color:#000; border:none; padding:.6rem 1.5rem; border-radius:8px; font-size:.9rem; font-weight:600; cursor:pointer; }
  button:hover { background:#b99dfb; }
  pre { background:#1a1a28; padding:1rem; border-radius:8px; overflow-x:auto; font-size:.8rem; margin-top:.5rem; }
  .nav { display:flex; gap:1rem; margin-bottom:2rem; flex-wrap:wrap; }
  .nav a { color:#60a5fa; text-decoration:none; font-size:.85rem; }
</style>
</head>
<body>
<div class="container">
  <h1>Town Notary</h1>
  <p class="subtitle">Timestamp, verify, and build reputation for AI agent interactions on NANDA Town.</p>
  <div class="nav">
    <a href="#" onclick="showTab('notarize');return false">Notarize</a>
    <a href="#" onclick="showTab('verify');return false">Verify</a>
    <a href="#" onclick="showTab('search');return false">Search</a>
    <a href="#" onclick="showTab('reputation');return false">Reputation</a>
    <a href="#" onclick="showTab('recent');return false">Recent</a>
    <a href="/docs" target="_blank">API Docs</a>
  </div>

  <div id="notarize" class="card">
    <h2>Notarize Data</h2>
    <label>Agent ID</label>
    <input id="n-agent" value="agent-1">
    <label>Data</label>
    <textarea id="n-data">I agree to deliver 100 units at price 50</textarea>
    <label>Data Type</label>
    <input id="n-type" value="agreement">
    <button onclick="notarize()">Notarize</button>
    <pre id="n-result"></pre>
  </div>

  <div id="verify" class="card" style="display:none">
    <h2>Verify Record</h2>
    <label>Record ID</label>
    <input id="v-id">
    <button onclick="verify()">Verify</button>
    <pre id="v-result"></pre>
  </div>

  <div id="search" class="card" style="display:none">
    <h2>Search Records</h2>
    <label>Agent ID</label>
    <input id="s-agent">
    <label>Data Hash</label>
    <input id="s-hash">
    <button onclick="search()">Search</button>
    <pre id="s-result"></pre>
  </div>

  <div id="reputation" class="card" style="display:none">
    <h2>Agent Reputation</h2>
    <label>Agent ID</label>
    <input id="r-agent" value="agent-1">
    <button onclick="reputation()">Get Score</button>
    <pre id="r-result"></pre>
  </div>

  <div id="recent" class="card" style="display:none">
    <h2>Recent Records</h2>
    <button onclick="recent()">Refresh</button>
    <pre id="recent-result"></pre>
  </div>
</div>
<script>
const BASE = window.location.origin;
async function api(method, path, body) {
  const opts = { method, headers:{"Content-Type":"application/json"} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  return r.ok ? r.json() : { error: r.status + " " + r.statusText, body: await r.text() };
}
function showTab(name) {
  document.querySelectorAll(".card").forEach(t => t.style.display = "none");
  const el = document.getElementById(name);
  if (el) el.style.display = "block";
}
async function notarize() {
  const r = await api("POST", "/notarize", { agent_id: document.getElementById("n-agent").value, data: document.getElementById("n-data").value, data_type: document.getElementById("n-type").value });
  document.getElementById("n-result").textContent = JSON.stringify(r, null, 2);
}
async function verify() {
  const r = await api("GET", "/verify/" + document.getElementById("v-id").value);
  document.getElementById("v-result").textContent = JSON.stringify(r, null, 2);
}
async function search() {
  const p = new URLSearchParams();
  const a = document.getElementById("s-agent").value;
  const h = document.getElementById("s-hash").value;
  if (a) p.set("agent_id", a);
  if (h) p.set("hash", h);
  const r = await api("GET", "/search?" + p.toString());
  document.getElementById("s-result").textContent = JSON.stringify(r, null, 2);
}
async function reputation() {
  const r = await api("GET", "/reputation/" + encodeURIComponent(document.getElementById("r-agent").value));
  document.getElementById("r-result").textContent = JSON.stringify(r, null, 2);
}
async function recent() {
  const r = await api("GET", "/search?limit=10");
  document.getElementById("recent-result").textContent = JSON.stringify(r, null, 2);
}
showTab("notarize");
</script>
</body>
</html>"""
