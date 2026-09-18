"""KYB DB CLI.

  python load.py schema            -> vytvori tabulky
  python load.py list              -> vsetky zdroje + stav
  python load.py run <source_id>   -> spusti loader
"""

import importlib
import sys
from pathlib import Path

import db

DOWNLOAD_DIR = Path(__file__).parent / "downloads"

_LOADERS = {p.stem: p for p in (Path(__file__).parent / "loaders").glob("*.py") if p.stem != "__init__"}


def _resolve(source_id: str):
    if source_id in _LOADERS:
        return importlib.import_module(f"loaders.{source_id}")
    for mod in _LOADERS:
        m = importlib.import_module(f"loaders.{mod}")
        if getattr(m, "SOURCE_ID", None) == source_id:
            return m
    return None


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "list"

    if cmd == "schema":
        db.run_schema()
        return 0

    if cmd == "list":
        import sources
        sources.list_sources()
        return 0

    if cmd == "run":
        if len(argv) < 2:
            print("chyba: zadaj source_id, napr. `python load.py run us-ofac`")
            return 1
        loader = _resolve(argv[1])
        if loader is None:
            print(f"chyba: ziadny loader pre '{argv[1]}'. Dostupne: {sorted(_LOADERS)}")
            return 1
        limit = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else None
        print(f"spustam loader: {argv[1]}" + (f" (limit {limit})" if limit else ""))
        n = loader.load(db, db.engine(), DOWNLOAD_DIR, limit=limit)
        print(f"hotovo: {n} zaznamov")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))