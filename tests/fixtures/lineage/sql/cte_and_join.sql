WITH cte AS (SELECT id, name FROM t1)
SELECT cte.id, t2.val FROM cte JOIN t2 ON cte.id = t2.id;
