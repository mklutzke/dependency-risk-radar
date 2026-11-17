-- =====================================================================
-- DuckDB 02  Profile the npm package universe (data/npm_packages.csv)
-- Recomputes the headline numbers from eda/01_npm_package_universe.py
-- in SQL, so each one is computed two ways (Python vs SQL) and must agree.
-- Run from the repo root:  duckdb < sql/duckdb/02_npm_packages_profile.sql
-- =====================================================================
CREATE OR REPLACE TABLE pkg AS
SELECT * FROM read_csv_auto('data/npm_packages.csv', all_varchar = true);

CREATE OR REPLACE VIEW ok AS
SELECT *,
       TRY_CAST(n_maintainers AS INT) AS maint,
       TRY_CAST(download_rank AS INT) AS dl_rank
FROM pkg WHERE status = '200';

-- Headline numbers
SELECT
  (SELECT COUNT(*) FROM pkg)                                    AS requested,
  COUNT(*)                                                      AS fetched,
  ROUND(AVG(CASE WHEN repo_host = 'github' THEN 1 ELSE 0 END), 4) AS github_match_rate,
  COUNT(DISTINCT github_repo)                                   AS distinct_github_repos,
  ROUND(AVG(CASE WHEN maint = 1 THEN 1 ELSE 0 END), 4)          AS single_maintainer_share,
  ROUND(AVG(CASE WHEN deprecated = 'True' THEN 1 ELSE 0 END), 4) AS deprecated_share
FROM ok;

-- Repository host breakdown (missing values = no repository field)
SELECT repo_host, COUNT(*) AS packages,
       ROUND(COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS share
FROM ok GROUP BY repo_host ORDER BY packages DESC;

-- Monorepos: repos that publish more than one high-impact package
WITH r AS (
  SELECT github_repo, COUNT(*) AS n FROM ok
  WHERE github_repo IS NOT NULL GROUP BY github_repo
)
SELECT
  COUNT(*) FILTER (WHERE n > 1)            AS monorepos,
  SUM(n)   FILTER (WHERE n > 1)            AS packages_in_monorepos,
  MAX(n)                                   AS max_packages_one_repo
FROM r;

-- Maintainer distribution, overall and by download-rank band
SELECT
  CASE WHEN dl_rank IS NULL THEN 'dependents-only'
       WHEN dl_rank <= 1000  THEN 'top 1k'
       WHEN dl_rank <= 5000  THEN '1k-5k'
       ELSE '5k+' END                                     AS band,
  COUNT(*)                                                AS packages,
  ROUND(AVG(CASE WHEN maint = 1 THEN 1 ELSE 0 END), 3)    AS single_maint_share,
  ROUND(AVG(CASE WHEN maint >= 5 THEN 1 ELSE 0 END), 3)   AS five_plus_share
FROM ok GROUP BY band ORDER BY MIN(COALESCE(dl_rank, 1e9));

-- Save the band table for charts
COPY (
  SELECT LEAST(maint, 5) AS maintainers, COUNT(*) AS packages
  FROM ok GROUP BY ALL ORDER BY maintainers
) TO 'data/npm_maintainer_hist.csv' (HEADER);
