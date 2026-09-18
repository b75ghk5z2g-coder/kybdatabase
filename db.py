import os
from pathlib import Path

# load .env if present (no dependency needed)
_env = Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text(encoding="ascii").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

DEFAULT_DB = "kyb"


def db_name() -> str:
    return os.environ.get("PGDATABASE", DEFAULT_DB)


def engine(db: str | None = None):
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=os.environ.get("PGPORT", "5432"),
        database=db or db_name(),
    )
    return create_engine(url, pool_pre_ping=True)


def run_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    with engine().begin() as conn:
        conn.execute(text(sql))
    print("schema OK")