"""Loader: GLEIF LEI-CDF v3.1 (global legal entity identifiers) + RR-CDF v2.1 (ownership).

Download: scrape latest daily file links from the GLEIF page, parse LEI records
into entity and RR relationship records into relationship, bulk upsert.
"""

import re
import zipfile
from pathlib import Path

import requests
from psycopg2.extras import execute_values

DOWNLOAD_PAGE = "https://www.gleif.org/en/lei-data/gleif-concatenated-file/download-the-concatenated-file"
SOURCE_ID = "gleif"
NS = "{http://www.gleif.org/data/schema/leidata/2016}"
NS_RR = "{http://www.gleif.org/data/schema/rr/2016}"

INSERT_SOURCE = """
INSERT INTO source (id, name, country, entity_count, url)
VALUES ('gleif', 'GLEIF Concatenated File', 'Global', NULL, :url)
ON CONFLICT (id) DO UPDATE SET url = EXCLUDED.url
"""

ENTITY_INSERT = """
INSERT INTO entity (entity_type, name, name_normalized, source_id, source_key, registration_number,
                    jurisdiction_code, legal_form, status, city, country)
VALUES %s
ON CONFLICT (source_id, source_key) DO UPDATE SET
    name = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    registration_number = EXCLUDED.registration_number,
    jurisdiction_code = EXCLUDED.jurisdiction_code,
    legal_form = EXCLUDED.legal_form,
    status = EXCLUDED.status,
    city = EXCLUDED.city,
    country = EXCLUDED.country,
    updated_at = now()
"""

DROP_REL = "DROP TABLE IF EXISTS gleif_rel;"
CREATE_REL = "CREATE TEMP TABLE gleif_rel (lei text, parent text, rtype text, status text, amount text, method text)"
REL_INSERT = """
INSERT INTO relationship (source_id, subject_id, object_id, rel_type, details)
SELECT 'gleif', cs.id, cp.id, r.rtype,
       jsonb_strip_nulls(jsonb_build_object(
           'status', NULLIF(r.status, ''),
           'amount', NULLIF(r.amount, ''),
           'method', NULLIF(r.method, '')
       ))
FROM gleif_rel r
JOIN entity cs ON cs.source_id = 'gleif' AND cs.source_key = r.lei
JOIN entity cp ON cp.source_id = 'gleif' AND cp.source_key = r.parent
ON CONFLICT DO NOTHING
"""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _latest_file_url(kind: str) -> str | None:
    for _ in range(2):
        try:
            r = requests.get(DOWNLOAD_PAGE, timeout=60)
            if r.status_code == 200:
                nums = [int(x) for x in re.findall(rf"concatenated-files/{kind}/get/(\d+)/zip", r.text)]
                if nums:
                    return f"https://leidata.gleif.org/api/v1/concatenated-files/{kind}/get/{max(nums)}/zip"
        except requests.RequestException:
            pass
    return None


def _download(zip_file: Path, url: str | None) -> None:
    if zip_file.exists():
        return
    if url is None:
        raise RuntimeError(f"{zip_file.name} chýba a URL sa nedá získať")
    zip_file.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", url)
    with requests.get(url, stream=True, timeout=1800) as r:
        r.raise_for_status()
        with open(zip_file, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)
    print("  saved", zip_file.name, zip_file.stat().st_size // (1024 * 1024), "MB")


def _iter_records(zip_file: Path, prefix: str, record: str):
    """Stream name-matching records from a huge pretty-printed XML inside a zip."""
    import xml.etree.ElementTree as ET
    open_tag, close_tag = f"<{prefix}:{record}".encode(), f"</{prefix}:{record}>".encode()
    with zipfile.ZipFile(zip_file) as z:
        xml_name = next(n for n in z.namelist() if n.endswith(".xml"))
        buf: list[bytes] = []
        capturing = False
        for raw_line in z.open(xml_name):
            if open_tag in raw_line:
                capturing = True
                buf = [raw_line]
            elif capturing:
                buf.append(raw_line)
                if close_tag in raw_line:
                    capturing = False
                    yield ET.fromstring(b"".join(buf))
                    buf.clear()


def _text(elem, path, ns=NS) -> str | None:
    full = "/".join(ns + p for p in path.split("/"))
    el = elem.find(full)
    if el is not None and el.text and el.text.strip():
        return el.text.strip()
    return None


def _load_entities(cur, zip_file: Path, limit: int | None) -> int:
    rows: list[tuple] = []
    n = 0
    for rec in _iter_records(zip_file, "lei", "LEIRecord"):
        if limit and n >= limit:
            break
        lei = _text(rec, "LEI")
        name = _text(rec, "Entity/LegalName")
        if not (lei and name):
            continue
        juris = _text(rec, "Entity/LegalJurisdiction")
        country = juris[:2] if juris else None
        rows.append((
            "company", name, norm(name), "gleif", lei, lei, country,
            _text(rec, "Entity/LegalForm/EntityLegalFormCode"),
            _text(rec, "Entity/EntityStatus"),
            _text(rec, "Entity/HeadquartersAddress/City") or _text(rec, "Entity/LegalAddress/City"),
            country,
        ))
        n += 1
        if len(rows) >= 20000:
            execute_values(cur, ENTITY_INSERT, rows, page_size=5000)
            rows.clear()
            print(f"  entities {n}")
    if rows:
        execute_values(cur, ENTITY_INSERT, rows, page_size=5000)
    return n


def _load_relationships(cur, conn, zip_file: Path, limit: int | None) -> int:
    rows: list[tuple] = []
    n = 0
    for rec in _iter_records(zip_file, "rr", "RelationshipRecord"):
        if limit and n >= limit:
            break
        child = _text(rec, "Relationship/StartNode/NodeID", NS_RR)
        parent = _text(rec, "Relationship/EndNode/NodeID", NS_RR)
        rtype = (_text(rec, "Relationship/RelationshipType", NS_RR) or "").lower()
        if not (child and parent and rtype):
            continue
        rows.append((
            child, parent, rtype,
            _text(rec, "Relationship/RelationshipStatus", NS_RR),
            _text(rec, "Relationship/RelationshipQuantifiers/RelationshipQuantifier/QuantifierAmount", NS_RR),
            _text(rec, "Relationship/RelationshipQuantifiers/RelationshipQuantifier/MeasurementMethod", NS_RR),
        ))
        n += 1
        if len(rows) >= 20000:
            execute_values(cur, "INSERT INTO gleif_rel VALUES %s", rows, page_size=5000)
            rows.clear()
            if n % 100000 == 0:
                cur.execute(REL_INSERT)
                cur.execute("TRUNCATE gleif_rel")
                conn.commit()
            print(f"  rels {n}")
    if rows:
        execute_values(cur, "INSERT INTO gleif_rel VALUES %s", rows, page_size=5000)
    cur.execute(REL_INSERT)
    conn.commit()
    return n


def load(db, engine, download_dir: Path, limit: int | None = None) -> int:
    lei_zip = download_dir / "gleif_leif.zip"
    rr_zip = download_dir / "gleif_rr.zip"
    lei_url = _latest_file_url("lei2")
    rr_url = _latest_file_url("rr")
    print(f"  urls: lei={lei_url or 'n/a'} rr={rr_url or 'n/a'}")
    _download(lei_zip, lei_url)
    _download(rr_zip, rr_url)

    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        if lei_url:
            cur.execute(INSERT_SOURCE.replace(":url", "%s"), (lei_url,))
        n = _load_entities(cur, lei_zip, limit)
        conn.commit()
        print(f"  entities total {n} (committed)")
        cur.execute(DROP_REL)
        cur.execute(CREATE_REL)
        m = _load_relationships(cur, conn, rr_zip, limit)
        print(f"  written relationships total {m} (committed)")
    finally:
        conn.close()
    return n