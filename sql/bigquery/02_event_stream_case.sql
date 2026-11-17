-- =====================================================================
-- 02  Case study: was the event-stream takeover visible in GH Archive?
--
-- Known story (2018): maintainer hands the repo to a new account,
-- new account adds flatmap-stream, malicious code ships, and it is
-- discovered ~Nov 20, 2018 (issue #116).
--
-- Cost control: query A touches 4 small columns over 12 month tables.
-- `payload` is the big column - only query it for single DAYS (query C).
-- DRY-RUN each query first.
-- =====================================================================

-- A) Who did what, per month, 2018            -> data/es_monthly_actor_type.csv
SELECT
  FORMAT_TIMESTAMP('%Y-%m', created_at)  AS month,
  actor.login                            AS actor,
  type,
  COUNT(*)                               AS events,
  MIN(created_at)                        AS first_seen,
  MAX(created_at)                        AS last_seen
FROM `githubarchive.month.*`
WHERE _TABLE_SUFFIX BETWEEN '201801' AND '201812'
  AND repo.name = 'dominictarr/event-stream'
GROUP BY month, actor, type
ORDER BY month, events DESC;


-- B) Monthly "control" metrics with window functions
--    -> data/es_control_metrics.csv
--    control events = pushes, PR merges/closes, releases, member changes.
--    For each month: who held the most control, their share, and whether
--    that account was new to the repo within the window.
WITH ev AS (
  SELECT
    DATE_TRUNC(DATE(created_at), MONTH) AS month,
    actor.login                         AS actor,
    type
  FROM `githubarchive.month.*`
  WHERE _TABLE_SUFFIX BETWEEN '201801' AND '201812'
    AND repo.name = 'dominictarr/event-stream'
),
control AS (
  SELECT month, actor, COUNT(*) AS n
  FROM ev
  WHERE type IN ('PushEvent', 'ReleaseEvent', 'MemberEvent', 'CreateEvent', 'DeleteEvent')
  GROUP BY month, actor
),
ranked AS (
  SELECT
    month, actor, n,
    SUM(n)       OVER (PARTITION BY month)                    AS month_total,
    ROW_NUMBER() OVER (PARTITION BY month ORDER BY n DESC)    AS rnk,
    MIN(month)   OVER (PARTITION BY actor)                    AS actor_first_month
  FROM control
)
SELECT
  month,
  actor                                   AS top_actor,
  n                                       AS top_actor_events,
  month_total                             AS control_events,
  ROUND(n / month_total, 2)               AS top_actor_share,
  actor_first_month = month               AS top_actor_is_new
FROM ranked
WHERE rnk = 1
ORDER BY month;


-- C) Membership changes, with payload, for the days found in A
--    A showed one MemberEvent: dominictarr, 2018-09-04 05:07 UTC.
--    This confirms who was added. One day table with payload is a few GB.
SELECT
  created_at,
  actor.login                                        AS actor,
  type,
  JSON_VALUE(payload, '$.action')                    AS action,
  JSON_VALUE(payload, '$.member.login')              AS member
FROM `githubarchive.day.20180904`          -- day of the MemberEvent found in A
WHERE repo.name = 'dominictarr/event-stream'
  AND type = 'MemberEvent';


-- D) Same idea for xz (optional, 2021-2024): when did a new account
--    become the top source of control events?
--    Repo name in GH Archive may be 'tukaani-project/xz' or older names;
--    check with a LIKE '%/xz' filter on a single month first.
-- SELECT FORMAT_TIMESTAMP('%Y-%m', created_at) AS month, actor.login, type, COUNT(*) AS events
-- FROM `githubarchive.month.*`
-- WHERE _TABLE_SUFFIX BETWEEN '202101' AND '202404'
--   AND repo.name = 'tukaani-project/xz'
-- GROUP BY 1, 2, 3 ORDER BY 1, 4 DESC;
