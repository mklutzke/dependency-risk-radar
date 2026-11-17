-- =====================================================================
-- DuckDB 01  One GH Archive hour, up close (runs on a laptop)
-- Run from the repo root with the DuckDB CLI:
--   duckdb < sql/duckdb/01_gha_hour_profile.sql
-- (or paste block by block into a notebook cell with duckdb.sql(...).show())
--
-- Reads the raw gzipped NDJSON straight from data.gharchive.org.
-- Hour format: YYYY-MM-DD-H (no leading zero on H), UTC.
-- Compare a healthy-coverage hour (2018) with a recent one (2026).
-- Record file size in MB from:  curl -sI <url> | grep -i content-length
-- =====================================================================
INSTALL httpfs; LOAD httpfs;

CREATE OR REPLACE TABLE hour_raw AS
SELECT '2018-06-13-15' AS hour, json
FROM read_ndjson_objects('https://data.gharchive.org/2018-06-13-15.json.gz')
UNION ALL
SELECT '2026-06-10-15' AS hour, json
FROM read_ndjson_objects('https://data.gharchive.org/2026-06-10-15.json.gz');

CREATE OR REPLACE TABLE hour_ev AS
SELECT
  hour,
  json->>'$.type'              AS type,
  json->>'$.actor.login'       AS actor,
  json->>'$.repo.name'         AS repo,
  (json->>'$.repo.id')::BIGINT AS repo_id,
  json->>'$.created_at'        AS created_at,
  length(json::VARCHAR)        AS bytes
FROM hour_raw;

-- Shape: events, distinct actors / repos, bot share, average event size
SELECT
  hour,
  COUNT(*)                                            AS events,
  COUNT(DISTINCT actor)                               AS actors,
  COUNT(DISTINCT repo_id)                             AS repos,
  ROUND(AVG(CASE WHEN actor LIKE '%[bot]' THEN 1 ELSE 0 END), 3) AS bot_share,
  ROUND(AVG(bytes))                                   AS avg_event_bytes,
  ROUND(SUM(bytes) / 1e6, 1)                          AS raw_json_mb
FROM hour_ev GROUP BY hour ORDER BY hour;

-- Event-type mix (share of the hour)
SELECT hour, type, COUNT(*) AS events,
       ROUND(COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY hour), 3) AS share
FROM hour_ev GROUP BY hour, type ORDER BY hour, events DESC;

-- Missing values in the fields we key on
SELECT hour,
  SUM(CASE WHEN actor   IS NULL THEN 1 ELSE 0 END) AS null_actor,
  SUM(CASE WHEN repo_id IS NULL THEN 1 ELSE 0 END) AS null_repo_id,
  SUM(CASE WHEN type    IS NULL THEN 1 ELSE 0 END) AS null_type
FROM hour_ev GROUP BY hour;

-- Outliers: most active actors in the hour (bots and CI dominate)
SELECT hour, actor, COUNT(*) AS events
FROM hour_ev GROUP BY hour, actor
QUALIFY ROW_NUMBER() OVER (PARTITION BY hour ORDER BY COUNT(*) DESC) <= 10
ORDER BY hour, events DESC;

-- Save for charts
COPY (SELECT hour, type, COUNT(*) AS events FROM hour_ev GROUP BY ALL)
  TO 'data/gha_hour_type_mix.csv' (HEADER);
