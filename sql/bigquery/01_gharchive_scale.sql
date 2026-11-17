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
-- =====================================================================

-- A) Events and size per year, 2015 onward   -> data/gha_year_tables.csv
SELECT
  table_id                              AS year,
  row_count                             AS events,
  ROUND(size_bytes / POW(1024, 3), 1)   AS gib_logical
FROM `githubarchive.year.__TABLES__`
WHERE table_id >= '2015'
ORDER BY year;


-- B) Events per day, every day since 2015    -> data/gha_day_tables.csv
--    This is the coverage chart: a sudden drop = capture problem, not
--    a drop in GitHub activity.
SELECT
  PARSE_DATE('%Y%m%d', table_id)        AS day,
  row_count                             AS events,
  ROUND(size_bytes / POW(1024, 3), 2)   AS gib_logical
FROM `githubarchive.day.__TABLES__`
WHERE table_id >= '20150101'
ORDER BY day;


-- C) Totals for the "why Spark" slide         -> note the numbers
SELECT
  COUNT(*)                                       AS day_tables,
  SUM(row_count)                                 AS total_events,
  ROUND(SUM(size_bytes) / POW(1024, 4), 2)       AS tib_logical,
  ROUND(AVG(row_count) / 24)                     AS avg_events_per_hour
FROM `githubarchive.day.__TABLES__`
WHERE table_id >= '20150101';


-- D) Event-type mix and bot share, one mid-June Wednesday per year
--    -> data/gha_type_mix_sample_days.csv
--    Same weekday each year so weekends don't distort the trend.
--    Scans only `type` + `actor.login` for 12 days: expect a few GB.
SELECT
  _TABLE_SUFFIX                                         AS day,
  type,
  COUNT(*)                                              AS events,
  COUNTIF(ENDS_WITH(actor.login, '[bot]'))              AS bot_events
FROM `githubarchive.day.*`
WHERE _TABLE_SUFFIX IN ('20150610','20160608','20170614','20180613',
                        '20190612','20200610','20210609','20220608',
                        '20230614','20240612','20250611','20260610')
GROUP BY day, type
ORDER BY day, events DESC;
