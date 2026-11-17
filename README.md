# Dependency Risk Radar

*Detecting risks in open-source packages, before they become incidents.*

**Problem.** Platform, security and OSPO teams depend on thousands of npm packages but only learn about risk when an advisory is published. Takeovers like event-stream (2018) and xz Utils (2024) started with a change in who controls a project, and that change was visible in public GitHub activity first. This project builds a monthly health timeline for every repo behind npm's high-impact packages and ranks the ones whose control or activity just shifted, with the evidence.

## Architecture (target)

```
GH Archive (hourly JSON) ─┐
OpenDigger mirror (live) ─┤                 ┌─ Spark on GKE (batch backfill) ─┐
deps.dev (BigQuery) ──────┼─► Cloud Storage ┤                                  ├─► Parquet lake ─┬─► DuckDB (EDA, backtest)
npm registry API ─────────┘   (raw, as-is)  └─ Spark Structured Streaming ────┘  Bronze→Platinum  └─► MongoDB Atlas + Atlas Search ─► Claude via MongoDB MCP
                                                         Claude labels issue/PR text (Silver → Gold), checked against hand labels
```

See `docs/Week8_Checkin_Dependency_Risk_Radar.pptx` for the diagram, layers and data model.

## Repo layout

| Path | What it is |
|---|---|
| `eda/01_npm_package_universe.py` | npm high-impact package list → latest manifests → GitHub repo mapping, maintainer counts. Resumable (`--budget`) |
| `eda/02_charts.py` | Turns CSVs in `data/` into PNGs in `docs/img/` (skips any CSV not there yet) |
| `sql/bigquery/01_gharchive_scale.sql` | GH Archive size and coverage per year/day (metadata, ~free) + event-type mix |
| `sql/bigquery/02_event_stream_case.sql` | event-stream 2018 case study, incl. window-function control metrics |
| `sql/bigquery/03_package_repo_join.sql` | npm vs deps.dev repo agreement, repo activity in GH Archive, advisories |
| `sql/duckdb/01_gha_hour_profile.sql` | Profile raw GH Archive hours straight from data.gharchive.org |
| `sql/duckdb/02_npm_packages_profile.sql` | Recomputes the npm numbers in SQL (must match the Python output) |
| `docs/` | Slides and chart images |
| `data/` | Local outputs, **git-ignored** (see Data sources) |

## How to run the EDA

```bash
pip install -r requirements.txt
python eda/01_npm_package_universe.py --workers 32 --budget 600   # rerun until it prints the summary
duckdb < sql/duckdb/02_npm_packages_profile.sql
duckdb < sql/duckdb/01_gha_hour_profile.sql
# BigQuery: run sql/bigquery/*.sql in the console (DRY-RUN first), save results as CSV into data/
python eda/02_charts.py
```

BigQuery runs in the free **sandbox** (no billing account). Always check the bytes estimate before running; select only needed columns, and query `payload` only on single-day tables.

## Data sources

| Source | What | How obtained | Size / rate |
|---|---|---|---|
| GH Archive | every public GitHub event, hourly gzipped JSON | data.gharchive.org (HTTP) and `githubarchive` BigQuery public dataset | multiple TB compressed; 87,672 hourly files for 2015–2024 |
| OpenDigger mirror | same format, independent capture | gharchive.open-digger.cn, polled hourly | 1 file/hour |
| deps.dev | npm package→repo links, OSV advisories | `bigquery-public-data.deps_dev_v1` | snapshot tables |
| npm registry | package manifests: repository, maintainers, publisher | registry.npmjs.org public API | 17,338 high-impact packages (npm-high-impact 1.13.0) |

All public. deps.dev data is CC-BY 4.0. No data is committed to this repo.

## Secrets

No keys, tokens or connection strings in the repo. Put them in `.env` (git-ignored) and read them from the environment.
