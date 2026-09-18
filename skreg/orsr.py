"""Obchodný register SR (ORSK) OpenAPI — sluzby.orsr.sk/openapi/Orsr.json.

Prináša presne to, čo RPO/ORSF mirror nevracajú: spoločníkov aj s podielom
(vklad / základné imanie), dátumy narodenia štatutárov, spôsob konania,
vklady, históriu názvov a informácie o súde/vložke.
"""

import requests

ORSK_SEARCH = "https://sluzby.orsr.sk/api/legal-person"
ORSK_EXTRACT = "https://sluzby.orsr.sk/api/legal-person/extract"
HEADERS = {"User-Agent": "Mozilla/5.0 (AML-Audit subject verification)"}
TIMEOUT = 20


def _get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _dat(v):
    return (v or "")[:10]


def _person_name(pd):
    pp = (pd or {}).get("physicalPerson") or {}
    return (pp.get("personName") or {}).get("formattedName", "") or ""


def lookup_orsr(ico: str) -> dict:
    """ORSK profil podľa IČO. Vracia {} (ok=False) ak subjekt nie je v OR SK."""
    ico = (ico or "").strip()
    if not ico:
        return {"ok": False}
    j = _get(f"{ORSK_SEARCH}?Filter.CorporateBodyFullNameOrRegistrationNumber="
             f"{ico}&Filter.IncludeTerminated=true")
    hits = (j or {}).get("data") or []
    if not hits:
        return {"ok": False}
    hit = hits[0]
    fr = hit.get("fileReference") or {}

    section, vlozka, sud = fr.get("section"), hit.get("insertNumber"), fr.get("court")
    ex = _get(f"{ORSK_EXTRACT}?oddiel={section}&vlozka={vlozka}&sud={sud}") or {}
    cb = ((ex.get("legalPerson") or {}).get("corporateBody")) or {}

    # štatutári (mená + dátumy narodenia + funkcia)
    sb_type = (cb.get("statutoryBodyType") or [{}])[0].get("value", "štatutárny orgán")
    statutari = []
    for s in cb.get("statutoryBody") or []:
        pd = s.get("personData") or {}
        pp = pd.get("physicalPerson") or {}
        statutari.append({
            "name": (pp.get("personName") or {}).get("formattedName", ""),
            "role": sb_type,
            "birth": _dat((pp.get("birth") or {}).get("dateOfBirth")),
            "validFrom": _dat(s.get("functionCreationDate") or s.get("effectiveFrom")),
        })

    # základné imanie + vklady
    equity = (cb.get("equity") or [{}])[0].get("equityValue", 0) or 0
    deposits = []
    for d in cb.get("deposits") or []:
        for st in d.get("stakeholder") or []:
            deposits.append({
                "meno": st.get("value", ""),
                "vklad": d.get("depositValue"),
                "splatene": d.get("depositPayedValue"),
                "mena": (d.get("currency") or {}).get("item", "EUR"),
            })

    podiel_map = {}
    for d in deposits:
        v = d.get("vklad") or 0
        if equity:
            podiel_map[d["meno"]] = round(v / equity * 100, 2)

    # spoločníci
    shareholders = []
    for sh in cb.get("stakeholder") or []:
        pd = sh.get("personData") or {}
        name = (pd.get("corporateBody") or {}).get("corporateBodyFullName") or _person_name(pd)
        addr = (pd.get("physicalAddress") or [None])[0] or {}
        obec = addr.get("municipality") or {}
        pobocka = " ".join(x for x in [addr.get("streetName"), addr.get("buildingNumber")] if x)
        ids = [(i.get("identifierValue") or "").replace(" ", "") for i in pd.get("id") or []]
        shareholders.append({
            "meno": name,
            "role": (sh.get("stakeholderType") or {}).get("item", {}).get("codelistItem", {}).get("itemName", "spoločník"),
            "adresa": f"{pobocka}, {obec.get('item', '')}".strip(", "),
            "krajina": (addr.get("country") or {}).get("item", ""),
            "ico": next((i for i in ids if i.isdigit()), ""),
            "birth": _dat((pd.get("physicalPerson") or {}).get("birth", {}).get("dateOfBirth")),
            "podiel_pct": podiel_map.get(name, ""),
            "vyklad": next((d["vklad"] for d in deposits if d["meno"] == name), ""),
            "splatene": next((d["splatene"] for d in deposits if d["meno"] == name), ""),
            "valid_from": _dat(sh.get("functionCreationDate") or sh.get("effectiveFrom")),
        })

    return {
        "ok": True,
        "vlozka": fr.get("formattedValueSpaced", ""),
        "sud": ex.get("courtName", ""),
        "historia_nazvov": hit.get("corporateBodyFullNames") or [],
        "statutari": statutari,
        "shareholders": shareholders,
        "sposob_konania": (cb.get("authorizationToExecute") or [{}])[0].get("value", ""),
        "equity": equity if equity else None,
        "zakladny_kapital_zaplatene": (cb.get("equity") or [{}])[0].get("equityValuePaid",
                                                                       None) if equity else None,
        "documents_count": hit.get("documentsCount") or 0,
        "register": "OR SR",
    }