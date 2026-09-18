"""Loader: US OFAC SDN list (Specially Designated Nationals).

Source: legacy csv download, https://www.treasury.gov/ofac/downloads/sdn.csv
Column layout (fixed, no header): 0 ent_num, 1 name, 2 type, 3 program,
4 title, 5 call_sign, 6 vess_type, 7 grt, 8 vess_flag, 9 vess_owner, 10 pob, 11 remarks.
"""

from pathlib import Path

import requests
from psycopg2.extras import Json

URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
SOURCE_ID = "us-ofac"
FIELDS = ["ent_num", "name", "type", "program", "title", "call_sign",
          "vess_type", "grt", "vess_flag", "vess_owner", "pob", "remarks"]

INSERT_SOURCE = """
INSERT INTO source (id, name, country, entity_count, url)
VALUES (:id, :name, :country, :entities, :url)
ON CONFLICT (id) DO UPDATE SET url = EXCLUDED.url, entity_count = EXCLUDED.entity_count
"""

UPSERT = """
INSERT INTO entity (entity_type, name, name_normalized, source_id, source_key, type, program, country, status, raw, updated_at)
VALUES ('other', :name, norm_name(:name), :source_id, :source_key, :type, :program, :country, :status, :raw, now())
ON CONFLICT (source_id, source_key) DO UPDATE SET
    name = EXCLUDED.name,
    name_normalized = EXCLUDED.name_normalized,
    type = EXCLUDED.type,
    program = EXCLUDED.program,
    country = EXCLUDED.country,
    status = EXCLUDED.status,
    raw = EXCLUDED.raw,
    updated_at = now()
"""


def load(db, engine, download_dir: Path, limit: int | None = None) -> int:
    dl = download_dir / "ofac_sdn.csv"
    if not dl.exists():
        dl.parent.mkdir(parents=True, exist_ok=True)
        print("downloading", URL)
        r = requests.get(URL, timeout=300)
        r.raise_for_status()
        dl.write_bytes(r.content)

    n = 0
    with engine.begin() as conn:
        conn.execute(db.text(INSERT_SOURCE), {
            "id": SOURCE_ID, "name": "US OFAC SDN List", "country": "US",
            "entities": None, "url": URL,
        })
        stmt = db.text(UPSERT)
        with open(dl, newline="", encoding="utf-8-sig") as f:
            import csv
            for fields in csv.reader(f):
                if len(fields) < 2:
                    continue
                if limit and n >= limit:
                    break
                row = dict(zip(FIELDS, fields))
                row = {k: v.strip() for k, v in row.items()}
                raw = {k: v for k, v in row.items() if v and v.strip("-0 ")}
                conn.execute(stmt, {
                    "name": row["name"],
                    "source_id": SOURCE_ID,
                    "source_key": "sdn-" + row["ent_num"],
                    "type": row.get("type") or None,
                    "program": row.get("program") or None,
                    "country": None,
                    "status": "listed",
                    "raw": Json(raw),
                })
                n += 1
                if n % 5000 == 0:
                    print(f"  {n}")
    return n