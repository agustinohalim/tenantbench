"""Inspect BIRD dev: schemas, foreign keys, row counts, and gold-query coverage per candidate DB.

Usage: python -I scripts/inspect_bird.py <path to dev_20240627>
Output feeds Hasil_ValidatorTenant_0 (database choice); no validator is run.
"""
import sqlite3, sys, pathlib, json, collections
root = pathlib.Path(sys.argv[1])
dev = json.load(open(root / "dev.json", encoding="utf-8"))
qcount = collections.Counter(d["db_id"] for d in dev)
for db in sorted(p for p in (root / "dev_databases").iterdir() if (p / f"{p.name}.sqlite").is_file()):
    f = db / f"{db.name}.sqlite"
    con = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
    tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    print(f"== {db.name}  questions={qcount[db.name]}")
    for t in tabs:
        n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        fks = [(r[3], r[2], r[4]) for r in con.execute(f'PRAGMA foreign_key_list("{t}")')]
        pk = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")') if r[5]]
        print(f"   {t:28s} rows={n:<9d} pk={pk} fk={fks}")
    con.close()


import json, sys, collections, sqlglot
from sqlglot import exp

dev = json.load(open(root / "dev.json", encoding="utf-8"))
TEN = {
 "financial": {"district","account","client","disp","card","loan","order","trans"},
 "formula_1": {"seasons","races","results","laptimes","pitstops","qualifying","driverstandings","constructorstandings","constructorresults"},
 "superhero": {"publisher","superhero","hero_power","hero_attribute"},
 "toxicology": {"molecule","atom","bond","connected"},
 "california_schools": {"schools","frpm","satscores"},
 "thrombosis_prediction": {"patient","examination","laboratory"},
 "card_games": {"sets","cards","foreign_data","legalities","rulings","set_translations"},
}
stat = collections.defaultdict(collections.Counter)
for d in dev:
    db = d["db_id"]
    if db not in TEN: continue
    s = stat[db]; s["q"] += 1
    try:
        tree = sqlglot.parse_one(d["SQL"], read="sqlite")
        tabs = {t.name.lower() for t in tree.find_all(exp.Table)}
        sqlglot.transpile(d["SQL"], read="sqlite", write="postgres")
    except Exception:
        s["parse_fail"] += 1; continue
    if tabs & TEN[db]: s["touch"] += 1
    if len(tabs & TEN[db]) >= 2: s["touch2"] += 1
    if any(isinstance(n, (exp.Subquery, exp.Union, exp.CTE)) for n in tree.walk()): s["nested"] += 1
for db, s in stat.items():
    print(f"{db:24s} q={s['q']:3d} touch={s['touch']:3d} touch>=2tab={s['touch2']:3d} nested={s['nested']:3d} parse_fail={s['parse_fail']}")
