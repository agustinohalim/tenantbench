# tenantbench

A test harness for checking whether SQL validators that enforce a tenant predicate on
LLM-generated queries can be bypassed.

Status: pre-registered on 2026-11-10. `results/PREREG_LOCK` names the locked commits; test-split
results are produced only after it exists.

## What it does

1. Adds a `tenant_id` column to public text-to-SQL databases (BIRD dev, CC BY-SA 4.0).
2. Loads them into PostgreSQL with row-level security (RLS). RLS is used only as an oracle, to decide
   what counts as a leak.
3. Builds a bypass corpus. Mutation templates are grouped into structural classes and applied to
   gold queries.
4. Runs several validator designs over the corpus. A query **leaks** when the validator accepts it
   and its result without RLS differs from its result under RLS for the requesting tenant.

## Data

BIRD is © its authors and licensed under CC BY-SA 4.0 (https://bird-bench.github.io). It is
downloaded by `scripts/fetch_bird.sh` and is not stored in this repository. Any derived data
released from this project carries the same license.

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
