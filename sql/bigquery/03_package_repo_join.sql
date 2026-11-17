-- =====================================================================
-- 03  Joining the sources: npm package -> GitHub repo -> GH Archive
--
-- Setup (once): upload data/npm_packages.csv (from eda/01_...py) to
-- BigQuery as table  <your_project>.drr.npm_packages  (auto-detect schema).
-- Replace `YOUR_PROJECT` below.
--
-- deps.dev tables are partitioned by SnapshotAt: ALWAYS filter on one
-- snapshot or you scan every snapshot ever taken.
-- If a column name errors, list the real ones with:
--   SELECT table_name, column_name, data_type
--   FROM `bigquery-public-data.deps_dev_v1.INFORMATION_SCHEMA.COLUMNS`
--   WHERE table_name IN ('PackageVersionToProject', 'Advisories');
--
-- HOW TO RUN: BigQuery only allows DECLARE at the top of a script.
-- Either run the whole file, or highlight the DECLARE line PLUS one
-- block and use "Run selection".
-- =====================================================================

DECLARE snap TIMESTAMP DEFAULT (
  SELECT MAX(Time) FROM `bigquery-public-data.deps_dev_v1.Snapshots`
);

-- A) Do npm's repository field and deps.dev agree on the repo?
--    ("ask it twice" for the mapping)       -> data/map_npm_vs_depsdev.csv

WITH dd AS (
  -- most common GitHub project per npm package across its versions
  SELECT Name AS package, LOWER(ProjectName) AS dd_repo
  FROM `bigquery-public-data.deps_dev_v1.PackageVersionToProject`
  WHERE SnapshotAt = snap
    AND System = 'NPM'
    AND ProjectType = 'GITHUB'
  GROUP BY package, dd_repo
  QUALIFY ROW_NUMBER() OVER (PARTITION BY package ORDER BY COUNT(*) DESC) = 1
),
np AS (
  SELECT package, github_repo AS npm_repo
  FROM `YOUR_PROJECT.drr.npm_packages`
  WHERE CAST(status AS STRING) = '200'
)
SELECT
  COUNT(*)                                                  AS packages,
  COUNTIF(npm_repo IS NOT NULL)                             AS npm_has_github,
  COUNTIF(dd_repo  IS NOT NULL)                             AS depsdev_has_github,
  COUNTIF(npm_repo = dd_repo)                               AS agree,
  COUNTIF(npm_repo IS NOT NULL AND dd_repo IS NOT NULL
          AND npm_repo != dd_repo)                          AS disagree,
  COUNTIF(npm_repo IS NULL AND dd_repo IS NULL)             AS neither
FROM np
LEFT JOIN dd USING (package);


-- B) Which mapped repos are actually alive in GH Archive?
--    2024-Q2 used as a "healthy coverage" window.  -> data/map_repo_activity.csv
--    Scans repo.name + actor.login + type for 3 months: dry-run first.
--    A repo with 0 events = silent OR renamed (GH Archive logs the name
--    at event time). Spot-check 20 zero-event repos by hand.
WITH repos AS (
  SELECT github_repo AS repo,
         COUNT(*)              AS n_packages,
         MIN(download_rank)    AS best_download_rank
  FROM `YOUR_PROJECT.drr.npm_packages`
  WHERE github_repo IS NOT NULL
  GROUP BY repo
),
ev AS (
  SELECT LOWER(repo.name)                                AS repo,
         COUNT(*)                                        AS events,
         COUNTIF(type = 'PushEvent')                     AS pushes,
         COUNT(DISTINCT IF(type = 'PushEvent', actor.login, NULL)) AS pushers
  FROM `githubarchive.month.*`
  WHERE _TABLE_SUFFIX BETWEEN '202404' AND '202406'
  GROUP BY repo
)
SELECT r.*, IFNULL(e.events, 0) AS events_2024q2,
       IFNULL(e.pushes, 0) AS pushes_2024q2,
       IFNULL(e.pushers, 0) AS pushers_2024q2
FROM repos r LEFT JOIN ev e USING (repo)
ORDER BY best_download_rank;

-- B2) Summary of B (run on the saved table or wrap B as a CTE)
-- SELECT COUNT(*) repos, COUNTIF(events_2024q2 = 0) silent_or_renamed,
--        COUNTIF(pushers_2024q2 = 1) one_pusher, COUNTIF(pushers_2024q2 = 0) no_pushes
-- FROM ...


-- C) Advisories for the high-impact set, by year disclosed (backtest labels)
--    -> data/advisories_by_year.csv

WITH adv AS (
  SELECT a.SourceID, a.Disclosed, p.Name AS package
  FROM `bigquery-public-data.deps_dev_v1.Advisories` AS a,
       UNNEST(a.Packages) AS p
  WHERE a.SnapshotAt = snap
    AND p.System = 'NPM'
)
SELECT
  EXTRACT(YEAR FROM Disclosed)            AS year,
  COUNT(DISTINCT SourceID)                AS advisories,
  COUNT(DISTINCT adv.package)             AS packages_hit
FROM adv
JOIN `YOUR_PROJECT.drr.npm_packages` np USING (package)
GROUP BY year
ORDER BY year;
