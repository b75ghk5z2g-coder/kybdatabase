"""Loader: ROR (Research Organization Registry) — 137K organizations.

Download: newest 'ROR Data' release from Zenodo (json inside zip), upsert entities,
aliases and org relationships (parent/child) resolved within the dump.
"""

import json
import zipfile
from pathlib import Path

import requests
from psycopg2.extras import execute_values

ZENODO_QUERY = "https://zenodo.org/api/records?q=title:%22ROR%20Data%22&sort=newest&size=1"
SOURCE_ID = "ror"

INSERT_SOURCE = """
INSERT INTO source (id, name, country, entity_count, url)
VALUES ('ror', 'Research Organizations Registry', 'Global', 137398, NULL)
ON CONFLICT (id) DO NOTHING
"""

ENTITY_INSERT = """
INSERT INTO entity (entity_type, name, name_normalized, source_id, source_key, registration_number,
                    jurisdiction_code, status, city, country)
VALUES %s
ON CONFLICT (source_id, source_key) DO UPDATE SET
    name = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    registration_number = EXCLUDED.registration_number,
    jurisdiction_code = EXCLUDED.jurisdiction_code,
    status = EXCLUDED.status,
    city = EXCLUDED.city,
    country = EXCLUDED.country,
    updated_at = now()
"""


def norm(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _latest_zip_url() -> str:
    r = requests.get(ZENODO_QUERY, timeout=120)
    r.raise_for_status()
    rec = r.json()["hits"]["hits"][0]
    return rec["files"][0]["links"]["self"]


def _download(dl: Path) -> Path:
    if dl.exists():
        return dl
    url = _latest_zip_url()
    dl.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", url)
    r = requests.get(url, timeout=1200)
    r.raise_for_status()
    dl.write_bytes(r.content)
    return dl


def _rows(cur, sql, rows, page_size=5000):
    if rows:
        execute_values(cur, sql, rows, page_size=page_size)


def load(db, engine, download_dir: Path, limit: int | None = None) -> int:
    zip_path = _download(download_dir / "ror-data.zip")
    with zipfile.ZipFile(zip_path) as z:
        jname = next(n for n in z.namelist() if n.endswith(".json"))
        orgs = json.load(z.open(jname))

    conn = engine.raw_connection()
    n = 0
    try:
        cur = conn.cursor()
        cur.execute(INSERT_SOURCE)
        ents, rels, aliases = [], [], []
        for org in orgs[:limit] if limit else orgs:
            rid = org["id"]  # https://ror.org/xxxx
            names = org.get("names") or []
            name = next((nm["value"] for nm in names if "ror_display" in nm.get("types", [])), None) or (names[0]["value"] if names else rid)
            loc = (org.get("locations") or [{}])[0].get("geonames_details") or {}
            ent_type = "company" if "company" in org.get("types", []) else "other"
            ents.append((
                ent_type, name, norm(name), "ror", rid, rid,
                loc.get("country_code"), org.get("status"),
                loc.get("name"), loc.get("country_code"),
            ))
            for nm in org.get("names", []):
                if "ror_display" in nm.get("types", []):
                    continue
                v = nm.get("value")
                if v and v != name:
                    aliases.append((rid, v, norm(v)))
            for rel in org.get("relationships") or []:
                target = rel["id"]
                rtype = {"child": "parent_of", "parent": "subsidiary_of",
                         "successor": "successor_of"}.get(rel["type"], "related_to")
                rels.append((rid, target, rtype))
            n += 1
            if n % 20000 == 0:
                print(f"  orgs {n}")

        print(f"  parsing done: {n} orgs")
        _rows(cur, ENTITY_INSERT, ents)
        print("  entities inserted")

        if rels:
            cur.execute("DROP TABLE IF EXISTS ror_rel; CREATE TEMP TABLE ror_rel (sub text, obj text, rtype text)")
            _rows(cur, "INSERT INTO ror_rel VALUES %s", rels)
            cur.execute("""
                INSERT INTO relationship (source_id, subject_id, object_id, rel_type, details)
                SELECT 'ror', cs.id, co.id, r.rtype, NULL
                FROM ror_rel r
                JOIN entity cs ON cs.source_id='ror' AND cs.source_key = r.sub
                JOIN entity co ON co.source_id='ror' AND co.source_key = r.obj
                ON CONFLICT DO NOTHING
            """)
            print(f"  relationships inserted {len(rels)}")

        if aliases:
            cur.execute("DROP TABLE IF EXISTS ror_alias; CREATE TEMP TABLE ror_alias (rid text, name text, norm text)")
            _rows(cur, "INSERT INTO ror_alias VALUES %s", aliases)
            cur.execute("""
                INSERT INTO alias (entity_id, name, name_normalized)
                SELECT e.id, a.name, a.norm
                FROM ror_alias a JOIN entity e ON e.source_id='ror' AND e.source_key = a.rid
                ON CONFLICT DO NOTHING
            """)
            print(f"  aliases inserted {len(aliases)}")

        conn.commit()
    finally:
        conn.close()
    return n