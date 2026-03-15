-- Deeply nested CTEs: level1 -> level2 -> level3; base tables a, b, c.
WITH level1 AS (
  WITH level2 AS (
    WITH level3 AS (SELECT * FROM base_a)
    SELECT * FROM level3
  )
  SELECT * FROM level2
),
level0 AS (SELECT 1 AS id FROM base_b)
SELECT l1.*, l0.id
FROM level1 l1
JOIN level0 l0 ON 1=1
JOIN base_c c ON c.id = l0.id;
