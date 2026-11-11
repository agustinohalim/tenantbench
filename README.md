# tenantbench

A test harness for checking whether SQL validators that enforce a tenant predicate on
LLM-generated queries can be bypassed.

Status: version 1.0.0. The evaluation was pre-registered on 2026-11-10; `results/PREREG_LOCK` names
the locked code commit, and the test split was run once after it.
`registration/Prareg_ValidatorTenant_disunting.md` is the pre-registration (Indonesian), a public
copy with five marked redactions and the SHA-256 of the original file at locking and with its five
logged deviations.

## What it does

1. Adds a `tenant_id` column to public text-to-SQL databases (BIRD dev, CC BY-SA 4.0).
2. Loads them into PostgreSQL with row-level security (RLS). RLS is used only as an oracle, to decide
   what counts as a leak.
3. Builds a bypass corpus. Mutation templates are grouped into structural classes and applied to
   gold queries.
4. Runs several validator designs over the corpus. A query **leaks** when the validator accepts it
   and its result without RLS differs from its result under RLS for the requesting tenant.

## Data

BIRD is © its authors and licensed under CC BY-SA 4.0 (https://bird-bench.github.io). The original
databases are downloaded by `scripts/fetch_bird.sh` and are not stored here. Everything under
`data/release/` and `results/` is derived from BIRD and carries CC BY-SA 4.0; the code is MIT.

| File | Content |
|---|---|
| `data/release/corpus.jsonl` | 2,391 leaking statements (12 classes, dev and test splits), as built by `build_corpus.py` |
| `data/release/valid.jsonl` | 593 valid queries with a tenant predicate in every scope |
| `data/release/load_report.json` | tenancy assignment and row counts per database |
| `results/dev/`, `results/test/` | per-statement verdicts of V1–V7 (`*_runs.jsonl`), summaries, release sweep (`*_versions.csv`), latency |
| `results/rq2/` | 1,200 local-model generations under six injection instructions and their evaluation |
| `results/rq4/` | Cube 1.8.21 run test (two runs) and documentation notes for six semantic-layer specifications |
| `results/logs/` | run logs; local paths replaced by `<repo>` and `<home>` |

`results/test/test_inputs.sha256` holds the hashes of the corpus and valid queries used for the test
run; the files in `data/release/` match them.

The tenancy is synthetic. No database in BIRD is multi-tenant in its original form, and no data from
any production system are used.

## Layout

```
tenantbench/        library code (oracle, mutators, validators)
scripts/            data download and preparation
tests/              unit tests
results/            committed result summaries
```

## Running

```
pip install -r requirements.txt              # Python 3.12
(cd v7_askdb && npm ci --ignore-scripts)     # AskDB guard used as V7
bash scripts/fetch_bird.sh                   # BIRD dev, checked by size
bash scripts/start_pg.sh                     # PostgreSQL 17 oracle on 127.0.0.1:55432
python -I scripts/load_pg.py data/raw/bird_dev/dev_20240627
python -I scripts/build_valid.py data/raw/bird_dev/dev_20240627
python -I scripts/build_corpus.py
python -I scripts/run_validators.py --split dev
python -I scripts/summarise.py --split dev
python -I scripts/version_sweep.py --split dev   # needs releases under versions/ and v7_askdb/versions/
```

## Validators

| | Design |
|---|---|
| V1 | keyword: `tenant_id =` somewhere in the text |
| V2 | sqlglot, outermost SELECT only |
| V3 | sqlglot, every SELECT scope, aliases compared case-insensitively |
| V4 | rewriter: every tenant table replaced by a filtered derived table |
| V5 | reference: per scope, PostgreSQL identifier rules, construct and function allowlist, outer-join aware |
| V6 | sql-guardrail 0.5.2 (MIT), `require_predicate`, non-tenant rules off |
| V7 | AskDB `@askdb/core` 1.0.0-beta.55 (Apache-2.0), `validateTenantGuardrails` |

Third-party validators are called as published; their licences apply to them.

## Citation

See `CITATION.cff`. Version 1.0.0 is archived on Zenodo: https://doi.org/10.5281/zenodo.24126240
(all versions: https://doi.org/10.5281/zenodo.24126239).

## Licence

Code: MIT (`LICENSE`). Derived data and results: CC BY-SA 4.0, following BIRD.
