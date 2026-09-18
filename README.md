# KYB Databáza

Lokálna databáza pre Know-Your-Business screening. Sťahuje registrované subjekty a vlastnícke vzťahy z verejných zdrojov (OpenCorporates rodina) do lokálneho PostgreSQL a poskytuje fuzzy vyhľadávanie s grafom vlastníkov cez webové rozhranie.

## Zdroje

| Source | Obsah | Status |
|---|---|---|
| GLEIF (LEI + RR) | ~3.4M právnických osôb + konsolidované vlastníctvo (direct/ultimate) | načítané |
| UK Companies House (PSC) | ~6M firiem + osoby s podstatným vplyvom | načítané |
| ROR | 137K výskumných organizácií + vzťahy | načítané |
| OFAC SDN | ~19K sankcionovaných subjektov | načítané |
| ua-edr, ru-egrul, sk-rpvs, … | čakajúce | — |

## Spustenie

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # alebo: sqlalchemy psycopg2-binary requests fastapi uvicorn[standard]
```

PostgreSQL (portable, port 5432, db `kyb`) + `db.py` s prihlasovacími údajmi v `.env`.

```bash
python load.py list                # zdroje + status
python load.py run gleif           # načíta zdroj
python app.py                      # web prehliadač → http://localhost:8090
```

## Web

- `GET /` — prehliadač (vyhľadávanie + graf vzťahov)
- `GET /api/search?q=...` — fuzzy search (pg_trgm)
- `GET /api/entity/{id}` — detail
- `GET /api/rels/{id}` — vzťahy (vlastníctvo obojsmerne)

## Štruktúra

```
load.py          CLI: zoznam zdrojov, beh loaderov, čistenie
db.py            pripojenie na PostgreSQL
schema.sql       schéma (entity, relationship, source)
search.py        fuzzy search + vzťahy
app.py           FastAPI web
loaders/         jeden loader na zdroj
normalize.py     translit cyriliky (pre ua-edr, ru-egrul)
```

## Poznámky

- Windows: dlhé behy spúšťať detached (WMI), inak shell-kill zabije aj PostgreSQL.
- Počas záťaže vypnúť autovacuum na tabuľkách entity/relationship (inak IO thrash).
- PSC entity sa vkladajú `ON CONFLICT DO NOTHING` (snapshot dáta), firmy `DO UPDATE` (denný update).