-- Snowflake vendor syntax: SAMPLE, double-quoted identifiers.
SELECT * FROM analytics."fact_orders"
SAMPLE (10) ROWS
WHERE created_at > '2020-01-01';
