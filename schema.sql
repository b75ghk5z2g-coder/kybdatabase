CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS source (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    country       TEXT,
    entity_count  BIGINT,
    url           TEXT,
    last_loaded   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS entity (
    id                   BIGSERIAL PRIMARY KEY,
    entity_type          TEXT NOT NULL CHECK (entity_type IN ('company','person','other')),
    name                 TEXT NOT NULL,
    name_normalized      TEXT NOT NULL,
    jurisdiction_code    TEXT,
    registration_number  TEXT,
    source_id            TEXT NOT NULL REFERENCES source(id),
    source_key           TEXT NOT NULL,
    status               TEXT,
    legal_form           TEXT,
    type                 TEXT,
    country              TEXT,
    city                 TEXT,
    address              TEXT,
    program              TEXT,
    entered_date         DATE,
    raw                  JSONB,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_source   ON entity(source_id, source_key);
CREATE INDEX IF NOT EXISTS ix_entity_name           ON entity(name);
CREATE INDEX IF NOT EXISTS ix_entity_name_norm      ON entity(name_normalized);
CREATE INDEX IF NOT EXISTS ix_entity_name_trgm      ON entity USING gin (name_normalized gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_entity_regno          ON entity(registration_number) WHERE registration_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_entity_juris          ON entity(jurisdiction_code) WHERE jurisdiction_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS alias (
    entity_id       BIGINT NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    PRIMARY KEY (entity_id, name)
);
CREATE INDEX IF NOT EXISTS ix_alias_norm ON alias(name_normalized);

CREATE TABLE IF NOT EXISTS relationship (
    id          BIGSERIAL PRIMARY KEY,
    source_id   TEXT REFERENCES source(id),
    subject_id  BIGINT NOT NULL REFERENCES entity(id),
    object_id   BIGINT NOT NULL REFERENCES entity(id),
    rel_type    TEXT NOT NULL,
    details     JSONB,
    UNIQUE (source_id, subject_id, object_id, rel_type)
);
CREATE INDEX IF NOT EXISTS ix_rel_subject ON relationship(subject_id);
CREATE INDEX IF NOT EXISTS ix_rel_object  ON relationship(object_id);

-- soundex-ish fuzzy helper for name matching in SQL
CREATE OR REPLACE FUNCTION norm_name(s TEXT) RETURNS TEXT AS $$
    SELECT lower(btrim(regexp_replace(s, '[^a-z0-9]+', ' ', 'gi')))
$$ LANGUAGE sql IMMUTABLE STRICT;