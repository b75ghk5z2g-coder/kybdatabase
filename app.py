"""KYB lokálny prehliadač. Spustenie: python app.py (ide na http://localhost:8090)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

import db
import search

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
  const rels = await j(`/api/rels/${e.id}`);
  document.getElementById("graph").innerHTML = "";
  if(!rels.length){ document.getElementById("graph").innerHTML = `<p class=muted>bez vzťahov — entita nie je ako vlastník a ani ako ovládaná v žiadnom zázname</p>`; return; }
  const nodes = [{id:0, label: truncate(ed.name,22), color:{background:"#522E91",border:"#3A2066"}, font:{color:"#fff"}}];
  const edges = []; let nid = 1;
  const cmap = {};
  rels.forEach(r=>{
    const cid = cmap[r.counterparty] || (cmap[r.counterparty] = nid++);
    if(!nodes.find(n=>n.id===cid))
      nodes.push({id:cid, label:truncate(r.counterparty,22),
        color: r.outgoing ? {background:"#EDE9F5",border:"#B9A7DB"} : {background:"#FDF3E3",border:"#E0B97A"}});
    if(r.outgoing) edges.push({from:0, to:cid, label:short(r.rel_type), arrows:"to"});
    else edges.push({from:cid, to:0, label:short(r.rel_type), arrows:"to", color:{color:"#C0392B"}});
  });
  new vis.Network(document.getElementById("graph"),
    {nodes, edges}, {physics:{enabled:false}, edges:{font:{size:10}}});
}
function truncate(s,n){return (s||"").length>n ? s.slice(0,n)+"…" : s;}
function short(s){return (s||"").replace(/_/g," ").slice(0,26);}
function escapeHtml(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
document.addEventListener("DOMContentLoaded",()=>{
  document.getElementById("q").addEventListener("keydown",e=>{if(e.key==="Enter")doSearch();});
  document.getElementById("btn").addEventListener("click",doSearch);
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
<input id="q" placeholder="hľadať firmu / osobu…"><button id="btn">Hľadať</button>
<span id="status" class="muted"></span>
<div id="results"></div>
<div id="detail"></div>
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


if __name__ == "__main__":
    import uvicorn
    print("KYB prehliadač: http://localhost:8090")
    uvicorn.run(app, host="127.0.0.1", port=8090)