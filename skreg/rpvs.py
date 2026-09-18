"""RPVS Open Data API v2 (register partnerov verejneho sektora).

Free official OData feed; fills the otherwise-empty "Konečný užívateľ výhod"
table with actually verified ultimate beneficial owners (KÚV per zákon
č. 315/2016). Lookup: PartneriVerejnehoSektora by ICO -> Partner.Id ->
KonecniUzivateliaVyhod by Partner/Id.

NOTE: this OData server requires '%20' for spaces in query strings; '+' is
rejected, so URLs are built manually, not via requests params.
"""

import requests

RPVS_BASE = "https://rpvs.gov.sk/opendatav2/"
HEADERS = {"User-Agent": "AML-Audit/1.0 (subject verification)"}
TIMEOUT = 20


def _get(path: str):
    try:
        r = requests.get(RPVS_BASE + path, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _dat(v) -> str:
    return (v or "")[:10]


def lookup_rpvs(ico: str) -> dict:
    """Public-sector-partner profile + current ultimate beneficial owners (KÚV).

    Returns {"partner": bool, "kuv": [{"meno","datum_narodenia","statna_prislusnost",
    "adresa","verejny_cinitel","od","do"}],
    "verejni_funkcionari":[{"meno","od","do"}],
    "pokuta":{"poznamka","datum"}|None, "vymaz":{"dovod","poznamka","datum"}|None,
    "kvalifikovane_podnety":[{"spisova_znacka","sposob","od","pravoplatne"}]}
    or a minimal dict on failure."""
    ico = (ico or "").strip()
    if not ico:
        return {"partner": False, "kuv": []}

    ps = _get(f"PartneriVerejnehoSektora?$filter=Ico%20eq%20%27{ico}%27&$expand=Partner&$count=true")
    if not ps or not ps.get("value"):
        return {"partner": False, "kuv": []}

    partner_ids = []
    for v in ps["value"]:
        pid = (v.get("Partner") or {}).get("Id")
        if pid and pid not in partner_ids:
            partner_ids.append(pid)
    if not partner_ids:
        return {"partner": True, "kuv": []}

    pid = partner_ids[0]
    extra = _get(f"Partneri?$filter=Id%20eq%20{pid}"
                 f"&$expand=Pokuta,Vymaz,KvalifikovanePodnety,VerejniFunkcionari&$count=true")
    p = (extra.get("value") or [])[0] if extra and extra.get("value") else {}
    vymaz = p.get("Vymaz") or {}
    pokuta = p.get("Pokuta") or {}
    kvalif = []
    for k in (p.get("KvalifikovanePodnety") or []):
        kvalif.append({
            "spisova_znacka": k.get("SpisovaZnackaKonania", ""),
            "sposob": k.get("SposobRozhodnutiaKP"),
            "od": _dat(k.get("DatumZacatiaKonania")),
            "pravoplatne": _dat(k.get("DatumPravoplatnostiRozhodnutia")),
        })
    vf = []
    for f in (p.get("VerejniFunkcionari") or []):
        vf.append({
            "meno": f"{f.get('Meno') or ''} {f.get('Priezvisko') or ''}".strip(),
            "od": _dat(f.get("PlatnostOd")),
            "do": _dat(f.get("PlatnostDo")),
        })

    kuv = []
    data = _get(f"KonecniUzivateliaVyhod?"
                f"$filter=Partner/Id%20eq%20{pid}%20and%20PlatnostDo%20eq%20null"
                f"&$expand=StatnaPrislusnost,Adresa&$count=true")
    for item in (data.get("value") or []) if data else []:
        adr = (item.get("Adresa") or {}).get
        kuv.append({
            "meno": f"{item.get('Meno') or ''} {item.get('Priezvisko') or ''}".strip(),
            "datum_narodenia": _dat(item.get("DatumNarodenia")),
            "statna_prislusnost": (item.get("StatnaPrislusnost") or {}).get("Meno", ""),
            "adresa": ", ".join(x for x in [
                adr("Mesto", ""), adr("MenoUlice", ""), adr("OrientacneCislo", "")] if x),
            "verejny_cinitel": bool(item.get("JeVerejnyCinitel")),
            "od": _dat(item.get("PlatnostOd")),
            "do": _dat(item.get("PlatnostDo")),
        })
    seen = set()
    uniq = []
    for k in kuv:
        key = (k["meno"], k["datum_narodenia"])
        if key not in seen:
            seen.add(key)
            uniq.append(k)
    return {
        "partner": True,
        "kuv": uniq,
        "verejni_funkcionari": vf,
        "pokuta": ({"poznamka": pokuta.get("Poznamka", ""),
                    "datum": _dat(pokuta.get("DatumVytvorenia"))} if pokuta else None),
        "vymaz": ({"dovod": (vymaz.get("Dovod") or "").lower(),
                    "poznamka": vymaz.get("Poznamka", ""),
                    "datum": _dat(vymaz.get("Datum"))} if vymaz else None),
        "kvalifikovane_podnety": kvalif,
    }