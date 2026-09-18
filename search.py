"""Query helper: prepojenie na FastAPI projekt.

Pripoj sa cez SQLAlchemy engine (z db.py) alebo cez FastAPI dependency:

    from sqlalchemy import text
    from fastapi import Depends

    engine = db.engine()

    @app.get("/kyb/search")
    def search(q: str):
        with engine.connect() as c:
            rows = c.execute(text("SELECT * FROM kyb_match(:q)"), {"q": q}).mappings().all()
        return rows
"""

import db

NAME_QUERY = """
SELECT e.id, e.name, e.entity_type, e.jurisdiction_code, e.registration_number,
       e.status, e.program, s.name AS source, similarity(e.name_normalized, norm_name(:q)) AS score
FROM entity e
JOIN source s ON s.id = e.source_id
WHERE e.name_normalized % norm_name(:q)
ORDER BY score DESC, e.name
LIMIT :limit
"""

EDGE_QUERY = """
SELECT e.name AS name, e.entity_type, e.registration_number, r.rel_type,
       o.name AS counterparty, o.entity_type, o.registration_number, TRUE AS outgoing
FROM relationship r
JOIN entity e ON e.id = r.subject_id
JOIN entity o ON o.id = r.object_id
WHERE e.id = :id
UNION ALL
SELECT o.name AS name, o.entity_type, o.registration_number, r.rel_type,
       e.name AS counterparty, e.entity_type, e.registration_number, FALSE AS outgoing
FROM relationship r
JOIN entity e ON e.id = r.subject_id
JOIN entity o ON o.id = r.object_id
WHERE o.id = :id
"""


def search(engine, q: str, limit: int = 25):
    """Fuzzy hladanie entity podla mena."""
    with engine.connect() as c:
        return c.execute(db.text(NAME_QUERY), {"q": q, "limit": limit}).mappings().all()


def relationships(engine, entity_id: int):
    """Vsetky vztahy entity (vlastnicka/riadiace struktura)."""
    with engine.connect() as c:
        return c.execute(db.text(EDGE_QUERY), {"id": entity_id}).mappings().all()