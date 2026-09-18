"""Screening SK subjektu podľa IČO: ORSR+RPVS+RÚZ + OFAC match v KYB DB.

Vracia profil odvetu (tiers z skreg/aml.py, prevzaté z AML-GT):
- CRITICAL_RISK: mená osôb subjektu sa zhodujú s OFAC sankciou (score >= 85)
- HIGH/MEDIUM/LOW: slabší match
- NEGATIVE: bez záznamu
"""

import db
import normalize
from skreg import aml, orsr, rpvs, ruz

OFAC_MATCH = """
SELECT e.name, e.entity_type, e.registration_number, e.jurisdiction_code,
       e.status, similarity(e.name_normalized, :n) AS score
FROM entity e
WHERE e.source_id = 'ofac'
  AND e.name_normalized % :n
ORDER BY score DESC
LIMIT 3
"""


def _scan(engine, name):
    n = normalize.norm(name)
    if not n:
        return []
    with engine.connect() as c:
        matches = c.execute(db.text(OFAC_MATCH), {"n": n}).mappings().all()
        return [dict(m) for m in matches]


def _person_names(o, r):
    """Mena osôb: statutari + spolocnici + KUV + verejni funkcionari (bez duplicit)."""
    names = [s["name"] for s in (o.get("statutari") or [])]
    names += [s["meno"] for s in (o.get("shareholders") or [])]
    names += [k["meno"] for k in (r.get("kuv") or [])]
    names += [f["meno"] for f in (r.get("verejni_funkcionari") or [])]
    seen, out = set(), []
    for n in names:
        n = (n or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def screen(engine, ico: str) -> dict:
    o = orsr.lookup_orsr(ico)
    r = rpvs.lookup_rpvs(ico)
    u = ruz.lookup_ruz(ico)

    person_hits = []
    for name in _person_names(o, r):
        m = _scan(engine, name)
        if m:
            person_hits.append({"meno": name, "matches": m})

    match_list = [
        {"name": m["name"], "score": float(m["score"]), "source": "OFAC",
         "is_sanction": True, "is_pep": False, "is_debtor": False}
        for p in person_hits for m in p["matches"]
    ]
    verdict = aml.evaluate_screening(match_list)

    return {
        "ico": ico,
        "orsr_ok": bool(o.get("ok")),
        "nazov": (u.get("nazov") or (o.get("historia_nazvov") or [None])[0] or ""),
        "verdict": verdict,
        "person_hits": person_hits,
        "register": o.get("register") if o.get("ok") else None,
        "vlozka": o.get("vlozka") if o.get("ok") else None,
        "dic": u.get("dic"),
        "velkost": u.get("velkost"),
        "obrat": (u.get("obrat") or {}).get("bezne"),
        "zakladne_imanie": (u.get("zakladne_imanie") or {}).get("bezne"),
        "kuv": r.get("kuv") or [],
        "statutari": o.get("statutari") or [],
        "shareholders": o.get("shareholders") or [],
        "partner_veren._sektora": bool(r.get("partner")),
        "vymaz": r.get("vymaz"),
        "pokuta": r.get("pokuta"),
    }