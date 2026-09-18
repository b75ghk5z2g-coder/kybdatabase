"""SK vlastnícka sieť na požiadanie: ORSR extract → DB → graf.

Slovensko nemá hromadný export vlastníctva, takže sieť sa buduje rekurzívne:
IČO → spoločníci (ORSK extract) → ich IČO → ich spoločníci … do hĺbky `depth`.
Uloží entity + vzťahy do DB (source 'sk-orsr') a vráti uzly/hrany pre graf.
"""

import hashlib
import json

import db
import normalize
from skreg import orsr

SOURCE_ID = "sk-orsr"
SOURCE_NAME = "ORSR (Obchodný register SR)"
SOURCE_URL = "https://sluzby.orsr.sk/"

ENTITY_UPSERT = """
INSERT INTO entity (entity_type, name, name_normalized, jurisdiction_code,
                    registration_number, source_id, source_key, status,
                    legal_form, country, city, address, raw)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
ON CONFLICT (source_id, source_key) DO UPDATE SET
    name = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    status = EXCLUDED.status,
    country = EXCLUDED.country,
    city = EXCLUDED.city,
    address = EXCLUDED.address,
    raw = EXCLUDED.raw,
    updated_at = now()
RETURNING id
"""

REL_UPSERT = """
INSERT INTO relationship (source_id, subject_id, object_id, rel_type, details)
VALUES (%s, %s, %s, 'shareholder_of', %s::jsonb)
ON CONFLICT (source_id, subject_id, object_id, rel_type) DO UPDATE SET details = EXCLUDED.details
"""

MAX_SHAREHOLDERS = 50
MAX_PROFILES = 40


def _ensure_source(cur):
    cur.execute("""INSERT INTO source (id, name, country, url) VALUES (%s,%s,'SK',%s)
                   ON CONFLICT (id) DO NOTHING""", (SOURCE_ID, SOURCE_NAME, SOURCE_URL))


def _person_key(name, birth):
    h = hashlib.sha1(f"{name}|{birth}".encode()).hexdigest()[:16]
    return "p:" + h


def _company_key(ico, name):
    if ico and str(ico).isdigit():
        return str(ico)
    return "n:" + hashlib.sha1((name or "").encode()).hexdigest()[:16]


def _upsert(cur, sh, kind, company_ico=None):
    """Vráti entity id pre spoločníka (osoba/firma)."""
    name = (sh.get("meno") or "").strip()
    ico = (sh.get("ico") or "").strip()
    birth = sh.get("birth") or ""
    if kind == "company":
        skey = ico or _company_key(None, name)
        etype, reg = "company", (ico or None)
    else:
        skey = _person_key(name, birth)
        etype, reg = "person", None
    nname = normalize.norm(name)
    jcode = "SK" if (ico and ico.isdigit()) else None
    legal = sh.get("role")
    country = sh.get("krajina") or None
    address = sh.get("adresa") or None
    import json
    cur.execute(ENTITY_UPSERT, (etype, name, nname, jcode, reg, SOURCE_ID, skey,
                                "active", legal, country, None, address,
                                json.dumps(sh, ensure_ascii=False)))
    return cur.fetchone()[0]


def _company_entity(cur, ico, name, profile=None):
    import json
    nname = normalize.norm(name)
    cur.execute(ENTITY_UPSERT, ("company", name, nname, "SK", ico, SOURCE_ID, ico,
                                "active", None, "SK", None, None,
                                json.dumps(profile or {}, ensure_ascii=False)))
    return cur.fetchone()[0]


def build(engine, ico: str, depth: int = 2) -> dict:
    ico = (ico or "").strip()
    if not (ico.isdigit() and len(ico) in (7, 8)):
        return {"ok": False, "error": "zadaj 7-8 miestne IČO"}

    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        _ensure_source(cur)

        nodes = {}   # source_key -> {id,name,type,country,jurisdiction}
        edges = []
        seen = {}
        root_prof = orsr.lookup_orsr(ico)
        if not root_prof.get("ok"):
            return {"ok": False, "error": f"IČO {ico} nie je v ORSR"}
        root_name = (root_prof.get("historia_nazvov") or [ico])[0]
        root_id = _company_entity(cur, ico, root_name, {"vlozka": root_prof.get("vlozka")})
        nodes[ico] = {"id": root_id, "name": root_name, "type": "company",
                      "country": "SK", "jurisdiction": "SK"}

        queue = [(ico, root_id, root_name, 0)]
        fetched = 0
        while queue:
            c_ico, c_id, c_name, d = queue.pop(0)
            if d >= depth or fetched >= MAX_PROFILES:
                continue
            prof = root_prof if c_ico == ico else orsr.lookup_orsr(c_ico)
            fetched += 1
            if not prof.get("ok"):
                continue
            for sh in (prof.get("shareholders") or [])[:MAX_SHAREHOLDERS]:
                sh_ico = (sh.get("ico") or "").strip()
                kind = "company" if sh_ico else "person"
                skey = sh_ico or _person_key(sh.get("meno") or "", sh.get("birth") or "")
                sid = _upsert(cur, sh, kind)
                cur.execute(REL_UPSERT, (SOURCE_ID, sid, c_id, json.dumps({
                    "role": sh.get("role"),
                    "podiel_pct": sh.get("podiel_pct"),
                    "vklad": sh.get("vyklad"),
                    "valid_from": sh.get("valid_from"),
                }, ensure_ascii=False)))
                nodes.setdefault(skey, {"id": sid, "name": sh.get("meno") or "",
                                        "type": kind,
                                        "country": sh.get("krajina") or None,
                                        "jurisdiction": "SK" if sh_ico else None})
                edges.append({"from": sid, "to": c_id, "rel_type": "shareholder_of",
                              "label": sh.get("role") or "spoločník",
                              "share_pct": sh.get("podiel_pct")})
                if sh_ico and sh_ico not in seen and d + 1 < depth:
                    seen[sh_ico] = True
                    queue.append((sh_ico, sid, sh.get("meno") or sh_ico, d + 1))
                if len(nodes) > 400:
                    break
        conn.commit()
        return {"ok": True, "ico": ico, "name": root_name, "root_id": root_id,
                "nodes": list(nodes.values()), "edges": edges,
                "depth": depth, "profiles_fetched": fetched}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()