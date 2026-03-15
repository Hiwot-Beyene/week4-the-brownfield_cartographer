-- BigQuery vendor syntax: backtick project.dataset.table, QUALIFY (window filter).
SELECT
  user_id,
  event_date,
  ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY event_date) AS rn
FROM `my_project.my_dataset.raw_events`
QUALIFY rn = 1;
