"""Loader: UK Companies House bulk — companies + Persons with Significant Control.

Two snapshots, both streamed from zip:
  1. BasicCompanyDataAsOneFile-*.zip  -> CSV, all UK companies       -> entity
  2. persons-with-significant-control-snapshot-*.zip -> JSONL PSC    -> entity + relationship (subject=company, object=PSC)
Phases commit separately, so a crash loses only the current phase.
"""

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import requests
from psycopg2.extras import execute_values, Json

OUTPUT_PAGE = "https://download.companieshouse.gov.uk/en_output.html"
PSC_PAGE = "https://download.companieshouse.gov.uk/en_pscdata.html"
SOURCE_ID = "uk-psc"

ENTITY_COLS = ("entity_type", "name", "name_normalized", "source_id", "source_key",
               "registration_number", "jurisdiction_code", "legal_form", "status", "city", "country")
ENTITY_INSERT = f"""
INSERT INTO entity ({", ".join(ENTITY_COLS)})
VALUES %s
ON CONFLICT (source_id, source_key) DO UPDATE SET
    name = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    registration_number = COALESCE(EXCLUDED.registration_number, entity.registration_number),
    legal_form = COALESCE(EXCLUDED.legal_form, entity.legal_form),
    status = COALESCE(EXCLUDED.status, entity.status),
    city = COALESCE(EXCLUDED.city, entity.city),
    updated_at = now()
"""

REL_COLS = ("source_id", "subject_id", "object_id", "rel_type", "details")

# PSC entities: DO NOTHING — snapshot dáta sa nemenia, prepis existujúcich
# riadkov = zbytočný index churn (veľa IO). Firma fáza (denný update) = DO UPDATE.
PSC_INSERT = """
INSERT INTO entity (entity_type, name, name_normalized, source_id, source_key,
                    registration_number, jurisdiction_code, legal_form, status, city, country)
VALUES %s
ON CONFLICT (source_id, source_key) DO NOTHING
"""
DROP_REL = "DROP TABLE IF EXISTS ukpsc_rel;"
CREATE_REL = "CREATE TEMP TABLE ukpsc_rel (comp_no text, psc_key text, details jsonb)"
REL_INSERT = """
INSERT INTO relationship (source_id, subject_id, object_id, rel_type, details)
SELECT 'uk-psc', cs.id, cp.id, 'significant_control', r.details
FROM ukpsc_rel r
JOIN entity cs ON cs.source_id = 'uk-psc' AND cs.source_key = r.comp_no
JOIN entity cp ON cp.source_id = 'uk-psc' AND cp.source_key = r.psc_key
ON CONFLICT DO NOTHING
"""

INSERT_SOURCE = """
INSERT INTO source (id, name, country, entity_count, url)
VALUES ('uk-psc', 'UK Companies House PSC + company register', 'GB', NULL, :url)
ON CONFLICT (id) DO UPDATE SET url = EXCLUDED.url
"""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _dedup_entities(rows: list[tuple]) -> list[tuple]:
    out: dict[tuple, tuple] = {}
    for r in rows:
        out.setdefault((r[3], r[4]), r)
    return list(out.values())


def _scrape_latest_url(page: str, pattern: str, name: str) -> str | None:
    for _ in range(2):
        try:
            r = requests.get(page, timeout=60)
            if r.status_code == 200:
                hits = re.findall(pattern, r.text)
                if hits:
                    return sorted(hits)[-1]
        except requests.RequestException:
            pass
    print(f"  upozornenie: URL pre {name} sa nedala ziskat, pouzijem cached zip")
    return None


def _download(zip_file: Path, url: str | None, name: str) -> None:
    if zip_file.exists():
        return
    if url is None:
        raise RuntimeError(f"{name}: zip chyba a URL nedostupna")
    zip_file.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", url)
    with requests.get(url, stream=True, timeout=3600) as r:
        r.raise_for_status()
        with open(zip_file, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)
    print("  saved", zip_file.name, zip_file.stat().st_size // (1024 * 1024), "MB")


# ---------- phase 1: companies (CSV) ----------

def load_companies(cur, conn, zip_file: Path, limit: int | None) -> int:
    import csv
    rows: list[tuple] = []
    n = 0
    with zipfile.ZipFile(zip_file) as z:
        csv_name = next(x for x in z.namelist() if x.endswith(".csv"))
        f = io.TextIOWrapper(z.open(csv_name), encoding="utf-8", errors="replace", newline="")
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        idx = {h: i for i, h in enumerate(header)}
        for rec in reader:
            if limit and n >= limit:
                break
            def col(h):
                i = idx.get(h)
                return rec[i].strip() if i is not None and i < len(rec) else ""
            num = col("CompanyNumber")
            name = col("CompanyName")
            if not (num and name):
                continue
            rows.append((
                "company", name, norm(name), "uk-psc", num, num, "GB",
                col("CompanyCategory"), col("CompanyStatus"),
                col("RegAddress.PostTown"), "GB",
            ))
            n += 1
            if len(rows) >= 20000:
                execute_values(cur, ENTITY_INSERT, _dedup_entities(rows), page_size=5000)
                rows.clear()
                if n % 100000 == 0:
                    conn.commit()
                print(f"  companies {n}")
    if rows:
        execute_values(cur, ENTITY_INSERT, _dedup_entities(rows), page_size=5000)
    return n


# ---------- phase 2: PSC (JSONL) ----------

def _person_key(d: dict) -> str:
    ne = d.get("name_elements") or {}
    dob = d.get("date_of_birth") or {}
    src = "|".join(str(x) for x in (
        ne.get("forename"), ne.get("middle_name"), ne.get("surname"),
        dob.get("year"), dob.get("month"), d.get("country_of_residence")))
    return hashlib.sha1(src.encode()).hexdigest()[:12]


def _name_of(d: dict) -> str | None:
    name = d.get("name")
    if name:
        return name.strip() or None
    ne = d.get("name_elements") or {}
    return " ".join(x for x in (ne.get("forename"), ne.get("middle_name"), ne.get("surname")) if x) or None


def load_psc(cur, conn, zip_file: Path, limit: int | None) -> int:
    cur.execute(DROP_REL)
    cur.execute(CREATE_REL)
    ent_rows: list[tuple] = []
    rel_rows: list[tuple] = []
    n = 0
    with zipfile.ZipFile(zip_file) as z:
        txt_name = next(x for x in z.namelist() if x.endswith(".txt"))
        for line in z.open(txt_name):
            line = line.strip()
            if not line or line[:1] != b"{":
                continue
            rec = json.loads(line)
            d = rec.get("data") or {}
            kind = d.get("kind") or ""
            if not kind.endswith(("person-with-significant-control", "beneficial-owner")):
                continue
            comp_no = rec.get("company_number")
            name = _name_of(d)
            if not (comp_no and name):
                continue
            if kind.startswith(("individual", "super-secure")):
                etype, key, regno = "person", _person_key(d), None
            else:
                ident = d.get("identification") or {}
                regno = (ident.get("registration_number") or "").strip() or None
                etype, key = "company", regno or "c" + hashlib.sha1(name.encode()).hexdigest()[:12]
            ent_rows.append((
                etype, name, norm(name), "uk-psc", key, regno, None, None,
                "inactive" if d.get("ceased_on") else "active", None, None,
            ))
            natures = d.get("natures_of_control") or []
            rel_rows.append((comp_no, key, Json({
                "kind": kind,
                "natures_of_control": natures,
                "notified_on": d.get("notified_on"),
                "ceased_on": d.get("ceased_on"),
            })))
            n += 1
            if len(ent_rows) >= 20000:
                execute_values(cur, PSC_INSERT, _dedup_entities(ent_rows), page_size=5000)
                ent_rows.clear()
                execute_values(cur, "INSERT INTO ukpsc_rel VALUES %s", rel_rows, page_size=5000)
                rel_rows.clear()
                if n % 100000 == 0:
                    cur.execute(REL_INSERT)
                    cur.execute("TRUNCATE ukpsc_rel")
                    conn.commit()
                print(f"  psc {n}")
    if ent_rows:
        execute_values(cur, PSC_INSERT, _dedup_entities(ent_rows), page_size=5000)
    if rel_rows:
        execute_values(cur, "INSERT INTO ukpsc_rel VALUES %s", rel_rows, page_size=5000)
    cur.execute(REL_INSERT)
    conn.commit()
    return n


def load(db, engine, download_dir: Path, limit: int | None = None) -> int:
    co_url = _scrape_latest_url(OUTPUT_PAGE, r"BasicCompanyDataAsOneFile-[0-9-]+\.zip", "companies")
    psc_url = _scrape_latest_url(PSC_PAGE, r"persons-with-significant-control-snapshot-[0-9-]+\.zip", "psc")
    co_zip = download_dir / "ch_basic.zip"
    psc_zip = download_dir / "ch_psc.zip"
    _download(co_zip, ("https://download.companieshouse.gov.uk/" + co_url) if co_url else None, "companies")
    _download(psc_zip, ("https://download.companieshouse.gov.uk/" + psc_url) if psc_url else None, "psc")

    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        url = (co_url or "") if co_url else ""
        cur.execute(INSERT_SOURCE.replace(":url", "%s"),
                    ("https://download.companieshouse.gov.uk/" + url,))
        cur.execute("SELECT count(*) FROM entity WHERE source_id='uk-psc' AND entity_type='company'")
        have_companies = cur.fetchone()[0] > 0
        if have_companies and not co_zip.exists():
            print(f"  companies uz nacitane ({have_companies}), skip")
        else:
            n = load_companies(cur, conn, co_zip, limit)
            conn.commit()
            print(f"  companies total {n} (committed)")
        m = load_psc(cur, conn, psc_zip, limit)
        print(f"  psc total {m} (committed)")
    finally:
        conn.close()
    return n