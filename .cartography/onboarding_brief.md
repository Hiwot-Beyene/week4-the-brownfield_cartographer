# Day-One Onboarding Brief

**Repository:** dbt-labs_jaffle-shop

## The Five FDE Day-One Questions

### What is the primary data ingestion path?
Data ingestion starts from these lineage sources: cast_to_date, compute_booleans, customer_order_count, customer_orders_summary, days, dbt_model:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/marts/customers.yml:customers, dbt_model:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/marts/order_items.yml:order_items, dbt_model:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/marts/orders.yml:orders. The first transformations that consume them are in the staging SQL and dbt model files (see Evidence for exact file:line).

Evidence (provenance):
- `dbt-labs_jaffle-shop/models/marts/metricflow_time_spine.sql:1` — _source: lineage (CONSUMES edge)_
- `dbt-labs_jaffle-shop/models/marts/orders.sql:1` — _source: lineage (CONSUMES edge)_
- `dbt-labs_jaffle-shop/models/marts/customers.sql:1` — _source: lineage (CONSUMES edge)_
- `dbt-labs_jaffle-shop/models/staging/stg_customers.sql:1` — _source: lineage (CONSUMES edge)_
- `dbt-labs_jaffle-shop/models/staging/stg_order_items.sql:1` — _source: lineage (CONSUMES edge)_

### What are the 3-5 most critical output datasets/endpoints?
The critical output datasets are: dbt_source:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_customers, dbt_source:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_items, dbt_source:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_orders, dbt_source:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_products, dbt_source:/home/hiwot/Desktop/tenacious-academy-project/week4-the-brownfield_cartographer/.cartography/cloned/dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_stores. Each is produced by a dbt model or SQL file; Evidence lists the defining file for each.

Evidence (provenance):
- `ecom.raw_customers:1` — _source: lineage (PRODUCES edge)_
- `ecom.raw_items:1` — _source: lineage (PRODUCES edge)_
- `ecom.raw_orders:1` — _source: lineage (PRODUCES edge)_
- `ecom.raw_products:1` — _source: lineage (PRODUCES edge)_
- `ecom.raw_stores:1` — _source: lineage (PRODUCES edge)_

### What is the blast radius if the most critical module fails?
The most critical modules by PageRank (highest blast radius if they fail) are: dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml, dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml, dbt-labs_jaffle-shop/.github/workflows/ci.yml. Use Navigator blast_radius on a module path for the full downstream dependency list.

Evidence (provenance):
- `dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml:1` — _source: survey (PageRank / most_connected)_
- `dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml:1` — _source: survey (PageRank / most_connected)_
- `dbt-labs_jaffle-shop/.github/workflows/ci.yml:1` — _source: survey (PageRank / most_connected)_
- `dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py:1` — _source: survey (PageRank / most_connected)_
- `dbt-labs_jaffle-shop/.pre-commit-config.yaml:1` — _source: survey (PageRank / most_connected)_

### Where is the business logic concentrated vs. distributed?
Business logic is concentrated in: dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml, dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml, dbt-labs_jaffle-shop/.github/workflows/ci.yml. Risky/dead-code candidates (review first): dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py.

Evidence (provenance):
- `dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py:1` — _source: survey (risky/dead-code)_

### What has changed most frequently in the last 90 days (git velocity map)?
High-velocity files (most changed, from structural analysis) are: dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml, dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml, dbt-labs_jaffle-shop/.github/workflows/ci.yml, dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py, dbt-labs_jaffle-shop/.pre-commit-config.yaml. Evidence lists each file; re-run with full clone for commit counts.

Evidence (provenance):
- `dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml:1` — _source: survey (high_velocity)_
- `dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml:1` — _source: survey (high_velocity)_
- `dbt-labs_jaffle-shop/.github/workflows/ci.yml:1` — _source: survey (high_velocity)_
- `dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py:1` — _source: survey (high_velocity)_
- `dbt-labs_jaffle-shop/.pre-commit-config.yaml:1` — _source: survey (high_velocity)_
