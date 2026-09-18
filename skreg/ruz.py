"""RÚZ Open API (Register účtovných závierok, CC0) — doplnkové dáta k IČO.

Prináša to, čo RPO/ORSF nevedia: DIČ, kategória počtu zamestnancov
(velkostOrganizacie) a obrat z poslednej dostupnej čitateľnej účtovnej závierky.
Pre firmy podávajúce IFRS závierky ako PDF nemusia byť tabuľky dostupné.
"""

import requests

RUZ_BASE = "https://www.registeruz.sk/cruz-public/api/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = 20
MAX_ZAVIERKY = 40

_velkosti = None
_sablony = {}
_kapital_cache = {}


def _get(path):
    try:
        r = requests.get(RUZ_BASE + path, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _velkost_name(kod):
    global _velkosti
    if _velkosti is None:
        data = _get("velkosti-organizacie") or {}
        _velkosti = {k["kod"]: (k.get("nazov") or {}).get("sk", "") for k in data.get("klasifikacie", [])}
    return _velkosti.get(str(kod), "") or (f"kód {kod}" if kod else "")


def _sablona_rows(sid):
    """Vráti {cisloRiadku: text} pre šablónu Súvahy, inak {}."""
    if sid is None:
        return {}
    if sid not in _sablony:
        data = _get(f"sablona?id={sid}") or {}
        tables = data.get("tabulky") or []
        _sablony[sid] = tables
    rows = {}
    for tab in _sablony[sid]:
        nazov = tab.get("nazov", {})
        text = " ".join(str(nazov.get(k, "")) for k in ("sk", "en")).lower()
        if "pas" not in text and "passive" not in text:
            continue
        for rw in tab.get("riadky") or []:
            label = (rw.get("text", {}) or {}).get("sk", "")
            rows[int(rw.get("cisloRiadku") or 0)] = label
    return rows


def _parse_kapital(vykaz):
    """Základné imanie z Súvahy (Strana pasív) štruktúrovaného výkazu.

    Data array: po riadkoch zľava doprava, každý riadok dve čísla
    (bežné a bezprostredne predchádzajúce účtovné obdobie) — zodpovedá stĺpcom
    4 a 5 v hlavičke šablóny. Index = (cisloRiadku - prvyRiadok) * 2.

    IFRS závierky nemajú 'obsah.tabulky' (len skenované PDF) — fallback cez
    Windows OCR (_parse_kapital_pdf). Vracia {'bezne','predosle','od','do'}."""
    k = _parse_kapital_structured(vykaz)
    if k:
        return k
    return _parse_kapital_pdf(vykaz)


def _parse_kapital_structured(vykaz):
    if not vykaz or vykaz.get("pristupnostDat") != "Verejné":
        return {}
    obsah = vykaz.get("obsah") or {}
    tabulky = obsah.get("tabulky") or []
    if not tabulky:
        return {}  # IFRS/PDF-only: strukturovane data nie su dostupne
    rows = _sablona_rows(vykaz.get("idSablony"))
    if not rows:
        return {}
    first = min(rows)
    for tab in tabulky:
        nazov = tab.get("nazov", {})
        text = " ".join(str(nazov.get(k, "")) for k in ("sk", "en")).lower()
        if "pas" not in text and "passive" not in text:
            continue
        d = tab.get("data") or []
        if not d:
            continue
        # nájdi riadok 82 / 69: "Základné imanie (411 alebo +/- 491)"
        hit = None
        for cislo, label in rows.items():
            if "základné imanie" not in label.lower():
                continue
            if "súčet" in label.lower() or "zmena" in label.lower() or "pohľadávky" in label.lower():
                continue
            hit = (cislo, label)
            break
        if hit is None:
            return {}
        cislo, label = hit
        # stĺpce: bežné (4) a predchádzajúce (5) — 2 čísla na riadok
        cols = 2
        if len(d) != len(rows) * cols:
            continue  # rozloženie dát nesedí so šablónou — neindexuj naslepo
        idx = (cislo - first) * cols
        ts = obsah.get("titulnaStrana", {})
        bezne = d[idx] if idx < len(d) else ""
        predosle = d[idx + 1] if idx + 1 < len(d) else ""
        if bezne not in ("", None):
            return {"bezne": bezne, "predosle": predosle,
                    "od": ts.get("obdobieOd", ""), "do": ts.get("obdobieDo", "")}
    return {}


def _parse_kapital_pdf(vykaz):
    """IFRS závierka: Súvaha len ako skenované PDF príloha — Windows OCR."""
    vid = vykaz.get("id")
    if vid in _kapital_cache:
        return _kapital_cache[vid]
    if not vykaz or vykaz.get("pristupnostDat") != "Verejné":
        return {}
    prilohy = vykaz.get("prilohy") or []
    pdf_att = next((p for p in prilohy
                    if (p.get("mimeType") or "").lower() == "application/pdf"), None)
    if not pdf_att:
        return {}
    try:
        url = "https://www.registeruz.sk/cruz-public/domain/" \
              f"financialreport/attachment/{pdf_att['id']}"
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
    except Exception:
        return {}
    res = _ocr_kapital(r.content)
    _kapital_cache[vid] = res
    return res


def _ocr_kapital(pdf_bytes):
    """Základné imanie z OCR skenovanej Súvahy. {} ak OCR nedostupný (Linux)."""
    try:
        from engine.ocr import find_kapital
        import asyncio
        return asyncio.run(find_kapital(pdf_bytes))
    except Exception:
        return {}


def _parse_obrat(vykaz):
    """Vráti {'bezne','predosle','od','do'} z výkazu ziskov a strát, inak {}.
    Riadok 1 = "Čistý obrat", data je [bežné, predchádzajúce] per riadok."""
    if not vykaz or vykaz.get("pristupnostDat") != "Verejné":
        return {}
    for tab in (vykaz.get("obsah", {}).get("tabulky") or []):
        nazov = tab.get("nazov", {})
        if not isinstance(nazov, dict):
            continue
        text = " ".join(str(tab.get("nazov", {}).get(k, "")) for k in ("sk", "en"))
        if "zisk" not in text.lower() and "income" not in text.lower():
            continue
        d = tab.get("data") or []
        if len(d) >= 2 and d[0] not in ("", None):
            ts = vykaz.get("obsah", {}).get("titulnaStrana", {})
            return {"bezne": d[0], "predosle": d[1],
                    "od": ts.get("obdobieOd", ""), "do": ts.get("obdobieDo", "")}
    return {}


def lookup_ruz(ico: str) -> dict:
    """RÚZ profil podľa IČO: DIČ, kategória zamestnancov, obrat."""
    ico = (ico or "").strip()
    if not ico:
        return {"ok": False}
    ids = _get(f"uctovne-jednotky?zmenene-od=2000-01-01&ico={ico}")
    uj_ids = (ids or {}).get("id") or []
    if not uj_ids:
        return {"ok": False}

    uj = _get(f"uctovna-jednotka?id={uj_ids[0]}")
    if not uj:
        return {"ok": False}

    out = {
        "ok": True,
        "dic": uj.get("dic", ""),
        "nazov": uj.get("nazovUJ", ""),
        "velkost_kod": uj.get("velkostOrganizacie", ""),
        "velkost": _velkost_name(uj.get("velkostOrganizacie", "")),
        "nace_kod": uj.get("skNace", ""),
        "adresa": f"{uj.get('ulica', '')}, {uj.get('mesto', '')}".strip(", "),
        "obrat": {},
        "zakladne_imanie": {},
    }

    # API vracia idUctovnychZavierok v NEZORADENOM poradí (VERSOR: 2017,2023,2024,
    # 2019,...2022,2016,2013) — preto vezmi hlavičky a zoraď najnovšou prvou.
    # Niektoré najnovšie roky sú IFRS PDF (žiadne data) — skenuj ďalej, kým
    # nenájdeš najnovšie čitateľné (obrat aj základné imanie).
    zavierky = []
    for zid in (uj.get("idUctovnychZavierok") or [])[:MAX_ZAVIERKY]:
        z = _get(f"uctovna-zavierka?id={zid}")
        if not z:
            continue
        zavierky.append(z)
    zavierky.sort(key=lambda x: x.get("obdobieDo", ""), reverse=True)

    for z in zavierky:
        for vid in (z or {}).get("idUctovnychVykazov") or []:
            v = _get(f"uctovny-vykaz?id={vid}")
            if not out["obrat"]:
                out["obrat"] = _parse_obrat(v)
            if not out["zakladne_imanie"]:
                out["zakladne_imanie"] = _parse_kapital(v)
            if out["obrat"] and out["zakladne_imanie"]:
                break
        if out["obrat"] and out["zakladne_imanie"]:
            break
    return out