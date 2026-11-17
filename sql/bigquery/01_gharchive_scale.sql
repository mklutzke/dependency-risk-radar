-- =====================================================================
-- 01  GH Archive scale and coverage over time
-- Source: githubarchive (BigQuery public mirror of data.gharchive.org)
--
-- Queries A-C read table METADATA only (__TABLES__): ~0 bytes billed.
-- Query D scans real columns: DRY-RUN FIRST (bytes shown top-right).
-- Save each result as CSV into data/ with the file name given below.
--
-- Note: size_bytes is BigQuery's logical (uncompressed, columnar) size,
-- not the gzipped JSON size on data.gharchive.org. Say which one you
-- quote on the slide.
--
-- Trap: the githubarchive.day dataset also contains a table named
-- `yesterday`. It sorts after '20150101' as text, so every query here
-- keeps only table names that are exactly 8 digits (YYYYMMDD), and query
-- D uses the `day.20*` wildcard so `yesterday` can't match.
-- =====================================================================

-- A) Events and size per year, 2015 onward   -> data/gha_year_tables.csv
SELECT
  table_id                              AS year,
  row_count                             AS events,
  ROUND(size_bytes / POW(1024, 3), 1)   AS gib_logical
FROM `githubarchive.year.__TABLES__`
WHERE REGEXP_CONTAINS(table_id, r'^\d{4}$')
  AND table_id >= '2015'
ORDER BY year;


-- B) Events per day, every day since 2015    -> data/gha_day_tables.csv
--    This is the coverage chart: a sudden drop = capture problem, not
--    a drop in GitHub activity.
SELECT
  PARSE_DATE('%Y%m%d', table_id)        AS day,
  row_count                             AS events,
  ROUND(size_bytes / POW(1024, 3), 2)   AS gib_logical
FROM `githubarchive.day.__TABLES__`
WHERE REGEXP_CONTAINS(table_id, r'^\d{8}$')
  AND table_id >= '20150101'
ORDER BY day;


-- B2) Which days are missing entirely?       -> note the list (missing values)
WITH t AS (
  SELECT PARSE_DATE('%Y%m%d', table_id) AS day
  FROM `githubarchive.day.__TABLES__`
  WHERE REGEXP_CONTAINS(table_id, r'^\d{8}$')
)
SELECT d AS missing_day
FROM UNNEST(GENERATE_DATE_ARRAY('2015-01-01', DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY))) AS d
LEFT JOIN t ON t.day = d
WHERE t.day IS NULL
ORDER BY d;


-- C) Totals for the "why Spark" slide         -> note the numbers
SELECT
  COUNT(*)                                       AS day_tables,
  SUM(row_count)                                 AS total_events,
  ROUND(SUM(size_bytes) / POW(1024, 4), 2)       AS tib_logical,
  ROUND(AVG(row_count) / 24)                     AS avg_events_per_hour
FROM `githubarchive.day.__TABLES__`
WHERE REGEXP_CONTAINS(table_id, r'^\d{8}$')
  AND table_id >= '20150101';


-- D) Event-type mix and bot share, one mid-June Wednesday per year
--    -> data/gha_type_mix_sample_days.csv
--    Same weekday each year so weekends don't distort the trend.
--    Scans only `type` + `actor.login` for 12 days: expect a few GB.
--    With the `day.20*` wildcard, _TABLE_SUFFIX is the date without "20".
SELECT
  CONCAT('20', _TABLE_SUFFIX)                           AS day,
  type,
  COUNT(*)                                              AS events,
  COUNTIF(ENDS_WITH(actor.login, '[bot]'))              AS bot_events
FROM `githubarchive.day.20*`
WHERE _TABLE_SUFFIX IN ('150610','160608','170614','180613',
                        '190612','200610','210609','220608',
                        '230614','240612','250611','260610')
GROUP BY day, type
ORDER BY day, events DESC;


-- E) Renames and transfers: of repos active in both June 2018 and
--    June 2024, how many show up under a different name?
--    Keyed on repo.id (stable); names lower-cased so case-only changes
--    don't count. Uses each repo's last name seen in the month.
--    A lower bound: repos renamed and renamed back are missed.
--    Scans repo.id + repo.name + created_at for 2 months: DRY-RUN first
--    (expect well under 10 GB).
WITH y2018 AS (
  SELECT repo.id AS repo_id,
         ARRAY_AGG(LOWER(repo.name) ORDER BY created_at DESC LIMIT 1)[OFFSET(0)] AS name_2018
  FROM `githubarchive.month.201806`
  GROUP BY repo_id
),
y2024 AS (
  SELECT repo.id AS repo_id,
         ARRAY_AGG(LOWER(repo.name) ORDER BY created_at DESC LIMIT 1)[OFFSET(0)] AS name_2024
  FROM `githubarchive.month.202406`
  GROUP BY repo_id
)
SELECT
  COUNT(*)                                                       AS repos_in_both,
  COUNTIF(name_2018 != name_2024)                                AS renamed_or_moved,
  ROUND(COUNTIF(name_2018 != name_2024) / COUNT(*), 4)           AS share_renamed_or_moved,
  COUNTIF(SPLIT(name_2018, '/')[OFFSET(0)]
          != SPLIT(name_2024, '/')[OFFSET(0)])                   AS owner_changed
FROM y2018 JOIN y2024 USING (repo_id);
