"""KYB lokálny prehliadač. Spustenie: python app.py (ide na http://localhost:8090)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

import db
import search
from skreg import network, screening

app = FastAPI(title="KYB Databáza")
_engine = db.engine()

BASE_HTML = """
<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<title>KYB Databáza</title>
<script src="https://unpkg.com/vis-network@9.1.7/standalone/umd/vis-network.min.js"></script>
<script>
const API = "";
async function j(u){const r=await fetch(u);if(!r.ok)throw new Error((await r.text()).slice(0,300));return r.json();}
let results = [];
let hist = [];
async function doSearch(){
  const q = document.getElementById("q").value.trim();
  if(!q) return;
  try {
    results = await j(`/api/search?q=${encodeURIComponent(q)}`);
    const list = document.getElementById("results");
    list.innerHTML = "";
    results.forEach((e,i)=>{
      const d = document.createElement("div");
      d.className = "hit";
      d.innerHTML = `<b>${escapeHtml(e.name)}</b> <span class=muted>${escapeHtml(e.source||"")} · ${escapeHtml(e.status||"")}</span>`;
      d.onclick = ()=>showEntity(i);
      list.appendChild(d);
    });
    document.getElementById("status").textContent = `${results.length} výsledkov`;
  } catch(err){ document.getElementById("status").textContent = "chyba: "+err.message; }
}
async function showEntity(i){
  const e = results[i];
  const ed = await j(`/api/entity/${e.id}`);
  document.getElementById("detail").innerHTML =
    `<h3>${escapeHtml(ed.name)}</h3>
     <p class=muted>${escapeHtml(ed.entity_type)} · ${escapeHtml(ed.jurisdiction_code||"-")} ·
       ${escapeHtml(ed.registration_number||"-")} · ${escapeHtml(ed.status||"-")} · zdroj ${escapeHtml(ed.source||"-")}</p>
     <div id="graph"></div>`;
  drawGraph(e.id, ed.name, [e]);
}
async function drawGraph(id, label, path){
  const rels = await j(`/api/rels/${id}`);
  const el = document.getElementById("graph");
  if(!rels.length){ el.innerHTML = `<p class=muted>bez vzťahov — entita nie je ako vlastník a ani ako ovládaná v žiadnom zázname</p>`; return; }
  const CAP = 30, extra = rels.length - CAP;
  const shown = extra>0 ? rels.slice(0,CAP) : rels;
  const nodes = [{id:0, label:truncate(label,25), color:{background:"#522E91",border:"#3A2066"}, font:{color:"#fff"}}];
  const edges = [];
  const nid = {}; let next = 1;
  shown.forEach(r=>{
    const cid = nid[r.counterparty] || (nid[r.counterparty] = next++);
    if(!nodes.find(n=>n.id===cid))
      nodes.push({id:cid, label:truncate(r.counterparty,25),
        color: r.outgoing ? {background:"#EDE9F5",border:"#B9A7DB"} : {background:"#FDF3E3",border:"#E0B97A"}});
    if(r.outgoing) edges.push({from:0, to:cid, label:short(r.rel_type), arrows:"to"});
    else edges.push({from:cid, to:0, label:short(r.rel_type), arrows:"to", color:{color:"#C0392B"}});
  });
  el.innerHTML = extra>0
    ? `<p class=muted>zobrazujem ${CAP} z ${rels.length} vzťahov · klik na uzol = zanorenie doň</p>`
    : `<p class=muted>klik na uzol = zanorenie doň · ← späť na predošlý</p>`;
  const net = new vis.Network(el, {nodes, edges},
    {physics:{solver:"barnesHut", stabilization:{iterations:150}},
     edges:{font:{size:9}}, nodes:{font:{size:12}}});
  net.on("click", p=>{
    if(p.nodes && p.nodes[0]!==0){
      const nm = nodes.find(n=>n.id===p.nodes[0]).label.replace(/…$/,"");
      hist.push({id, label});
      document.getElementById("back").style.display = "inline";
      doDrill(nm);
    }
  });
  path = path || [];
}
function goBack(){
  const h = hist.pop();
  if(h){ document.getElementById("back").style.display = hist.length ? "inline" : "none"; drawGraph(h.id, h.label); }
}
async function doDrill(name){
  try {
    const hits = await j(`/api/search?q=${encodeURIComponent(name)}&limit=3`);
    if(hits[0]) showEntity(0, hits[0].name);
    else document.getElementById("graph").innerHTML = `<p class=muted>subjekt nenájdený</p>`;
  } catch(err){ document.getElementById("graph").innerHTML = `<p class=muted>chyba: ${escapeHtml(err.message)}</p>`; }
}
function truncate(s,n){return (s||"").length>n ? s.slice(0,n)+"…" : s;}
function short(s){return (s||"").replace(/_/g," ").slice(0,26);}
function escapeHtml(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
async function doScreen(){
  const ico = document.getElementById("ico").value.trim();
  if(!ico) return;
  const st = document.getElementById("sverdict");
  st.textContent = "="; st.style.color = "#777";
  try {
    const r = await j(`/api/screening?ico=${encodeURIComponent(ico)}`);
    const col = r.verdict==="NEGATIVE" ? "#1E7B34" : (r.verdict.startsWith("CRITICAL") ? "#B71C1C" : "#E65100");
    st.style.color = col;
    st.textContent = `${r.verdict} (${r.risk_pct}%) · ${r.nazov||"neznámy"} · DIČ ${r.dic||"-"} · ${r.velkost||"-"}`;
    let h = "";
    if(r.person_hits && r.person_hits.length){
      h = "<div class=hit>";
      r.person_hits.forEach(p=>{ h += `<b>${escapeHtml(p.meno)}</b><br>`;
        p.matches.forEach(m=>{ h += `&nbsp;→ ${escapeHtml(m.name)} (${m.score.toFixed(0)}%) ${escapeHtml(m.status||"")}<br>`; }); });
      h += "</div>";
    }
    document.getElementById("sdetail").innerHTML = h;
  } catch(err){ st.textContent = "chyba: "+err.message; }
}
async function doNet(){
  const ico = document.getElementById("net_ico").value.trim();
  const st = document.getElementById("netstatus");
  if(!ico) return;
  st.style.color = "#777"; st.textContent = "… ťahám ORSR (môže trvať 30-60s)";
  try {
    const r = await j(`/api/sk-network?ico=${encodeURIComponent(ico)}&depth=2`);
    if(!r.ok){ st.style.color = "#B71C1C"; st.textContent = r.error || "chyba"; return; }
    st.style.color = "#1E7B34";
    st.textContent = `${r.name} · ${r.nodes.length} subjektov · ${r.edges.length} vzťahov (${r.profiles_fetched} ORSR profilov)`;
    drawNetwork(r);
  } catch(err){ st.style.color="#B71C1C"; st.textContent = "chyba: "+err.message; }
}
function drawNetwork(data){
  document.getElementById("detail").innerHTML = `<h3>${escapeHtml(data.name)}</h3>
    <p class=muted>SK vlastnícka sieť (ORSR, hĺbka ${data.depth})</p><div id="graph"></div>`;
  const byId = {}; data.nodes.forEach(n=>byId[n.id]=n);
  const nodes = data.nodes.map(n=>({
    id:n.id, label:truncate(n.name,25),
    shape: n.type==="person" ? "ellipse" : "box",
    color: n.id===data.root_id
      ? {background:"#522E91",border:"#3A2066"}
      : (n.type==="person" ? {background:"#FDF3E3",border:"#E0B97A"} : {background:"#EDE9F5",border:"#B9A7DB"}),
    font: n.id===data.root_id ? {color:"#fff"} : undefined
  }));
  const edges = data.edges.map(e=>({from:e.from, to:e.to, label:short(e.label||e.rel_type), arrows:"to",
    color:{color:"#C0392B"}}));
  new vis.Network(document.getElementById("graph"), {nodes, edges},
    {physics:{solver:"barnesHut", stabilization:{iterations:200}}, edges:{font:{size:9}}, nodes:{font:{size:12}}});
}
document.addEventListener("DOMContentLoaded",()=>{
  document.getElementById("q").addEventListener("keydown",e=>{if(e.key==="Enter")doSearch();});
  document.getElementById("btn").addEventListener("click",doSearch);
  document.getElementById("ico").addEventListener("keydown",e=>{if(e.key==="Enter")doScreen();});
  document.getElementById("sbtn").addEventListener("click",doScreen);
  document.getElementById("net_ico").addEventListener("keydown",e=>{if(e.key==="Enter")doNet();});
  document.getElementById("netbtn").addEventListener("click",doNet);
});
</script>
<style>
 body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f5f5f7;color:#222}
 .muted{color:#777;font-size:12px} .hit{padding:8px;border-bottom:1px solid #ddd;cursor:pointer;background:#fff}
 .hit:hover{background:#efe9f5} h3{margin:6px 0} #graph{width:100%;height:420px;border:1px solid #ddd;background:#fff}
 input{padding:8px;width:340px} button{padding:8px 16px;background:#522E91;color:#fff;border:none;cursor:pointer}
 #results{max-height:50vh;overflow:auto;border:1px solid #ddd;background:#fff;margin:12px 0}
</style>
</head>
<body>
<h1>KYB Databáza</h1>
<p><b>SK vlastnícka sieť (IČO):</b> <input id="net_ico" placeholder="31322832"><button id="netbtn">Sieť</button>
<span id="netstatus" class="muted"></span></p>
<p><b>SK screening podľa IČO:</b> <input id="ico" placeholder="00151653"><button id="sbtn">Screenovať</button>
<span id="sverdict" class="muted"></span></p>
<div id="sdetail"></div>
<input id="q" placeholder="hľadať firmu / osobu…"><button id="btn">Hľadať</button>
<span id="status" class="muted"></span>
<div id="results"></div>
<div id="detail"></div>
     <a id="back" style="display:none;cursor:pointer;color:#522E91" onclick="goBack()">← späť</a>
</body></html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(BASE_HTML)


@app.get("/api/search")
def api_search(q: str, limit: int = 25):
    rows = search.search(_engine, q, limit=limit)
    return [dict(r) for r in rows]


@app.get("/api/entity/{entity_id}")
def api_entity(entity_id: int):
    with _engine.connect() as c:
        row = c.execute(db.text("""
            SELECT id, name, entity_type, jurisdiction_code, registration_number,
                   status, legal_form, city, country, source_id
            FROM entity WHERE id = :id"""), {"id": entity_id}).mappings().first()
        if row is None:
            return {"error": "nenájdené"}
        d = dict(row)
        s = c.execute(db.text("SELECT name FROM source WHERE id = :sid"),
                      {"sid": d.pop("source_id")}).scalar()
        if d["legal_form"]:
            d["type"] = d["legal_form"]
        d["source"] = s
        return d


@app.get("/api/rels/{entity_id}")
def api_rels(entity_id: int):
    rows = search.relationships(_engine, entity_id)
    return [dict(r) for r in rows]


@app.get("/api/screening")
def api_screening(ico: str):
    r = screening.screen(_engine, ico)
    status = r["verdict"]["status"]
    return {
        "ico": r["ico"], "nazov": r["nazov"], "verdict": status,
        "risk_pct": r["verdict"]["risk_pct"],
        "match_name": r["verdict"]["match_name"],
        "dic": r["dic"], "velkost": r["velkost"],
        "obrat": r["obrat"], "zakladne_imanie": r["zakladne_imanie"],
        "register": r["register"], "vlozka": r["vlozka"],
        "kuv": r["kuv"], "statutari": r["statutari"],
        "shareholders": r["shareholders"],
        "partner": r["partner_veren._sektora"],
        "vymaz": r["vymaz"], "pokuta": r["pokuta"],
        "person_hits": r["person_hits"],
    }


@app.get("/api/sk-network")
def api_sk_network(ico: str, depth: int = 2):
    return network.build(_engine, ico, depth=max(1, min(depth, 3)))


if __name__ == "__main__":
    import uvicorn
    print("KYB prehliadač: http://localhost:8090")
    uvicorn.run(app, host="127.0.0.1", port=8090)