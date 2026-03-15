# CODEBASE

**Repository:** dbt-labs_jaffle-shop

## Architecture Overview
This repository (dbt-labs_jaffle-shop) contains 37 analyzed modules. Structurally central or high-impact modules include: cd_prod.yml, cd_staging.yml, ci.yml, dbt_cloud_run_job.py, .pre-commit-config.yaml. Data sources include 3 entry points. Outputs or sinks include 3 endpoints or datasets. High-impact and velocity signals point to key workflow and transformation paths..

## Critical Path
- 1. `dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml` (pagerank=0.024480)
- 2. `dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml` (pagerank=0.024480)
- 3. `dbt-labs_jaffle-shop/.github/workflows/ci.yml` (pagerank=0.024480)
- 4. `dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py` (pagerank=0.024480)
- 5. `dbt-labs_jaffle-shop/.pre-commit-config.yaml` (pagerank=0.024480)

## Data Sources & Sinks
- **Sources**
  - `cast_to_date`
  - `compute_booleans`
  - `customer_order_count`
  - `customer_orders_summary`
  - `days`
  - `dbt_model:dbt-labs_jaffle-shop/models/marts/customers.yml:customers`
  - `dbt_model:dbt-labs_jaffle-shop/models/marts/order_items.yml:order_items`
  - `dbt_model:dbt-labs_jaffle-shop/models/marts/orders.yml:orders`
  - `dbt_model:dbt-labs_jaffle-shop/models/staging/stg_customers.yml:stg_customers`
  - `dbt_model:dbt-labs_jaffle-shop/models/staging/stg_locations.yml:stg_locations`
  - `dbt_model:dbt-labs_jaffle-shop/models/staging/stg_order_items.yml:stg_order_items`
  - `dbt_model:dbt-labs_jaffle-shop/models/staging/stg_orders.yml:stg_orders`
  - `dbt_model:dbt-labs_jaffle-shop/models/staging/stg_products.yml:stg_products`
  - `dbt_model:dbt-labs_jaffle-shop/models/staging/stg_supplies.yml:stg_supplies`
  - `ecom.raw_customers`
- **Sinks**
  - `dbt_source:dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_customers`
  - `dbt_source:dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_items`
  - `dbt_source:dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_orders`
  - `dbt_source:dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_products`
  - `dbt_source:dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_stores`
  - `dbt_source:dbt-labs_jaffle-shop/models/staging/__sources.yml:ecom.raw_supplies`
  - `sql:dbt-labs_jaffle-shop/models/marts/customers.sql`
  - `sql:dbt-labs_jaffle-shop/models/marts/locations.sql`
  - `sql:dbt-labs_jaffle-shop/models/marts/metricflow_time_spine.sql`
  - `sql:dbt-labs_jaffle-shop/models/marts/order_items.sql`
  - `sql:dbt-labs_jaffle-shop/models/marts/orders.sql`
  - `sql:dbt-labs_jaffle-shop/models/marts/products.sql`
  - `sql:dbt-labs_jaffle-shop/models/marts/supplies.sql`
  - `sql:dbt-labs_jaffle-shop/models/staging/stg_customers.sql`
  - `sql:dbt-labs_jaffle-shop/models/staging/stg_locations.sql`

## Known Debt
- **Circular Dependencies**
  - None detected in this repository.
- **Doc Drift Flags**
  - None flagged in this repository.

## High-Velocity Files
- `dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/.github/workflows/ci.yml` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/.pre-commit-config.yaml` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/Taskfile.yml` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/dbt_project.yml` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/macros/cents_to_dollars.sql` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/macros/generate_schema_name.sql` (high-velocity from survey; no git history for counts)
- `dbt-labs_jaffle-shop/models/marts/customers.sql` (high-velocity from survey; no git history for counts)

_(Git commit counts unavailable — shallow clone or no history; list from structural/survey data.)_

## Recent Change Velocity
- Window: last 30 days; 10 high-velocity files from structural analysis of this repository (git history unavailable for commit counts).

## Module Purpose Index
- `dbt-labs_jaffle-shop/.github/workflows/cd_prod.yml`: This module is designed to automate the deployment of database models using dbt Cloud, a cloud-based data modeling platform. It includes steps to check out code from GitHub, set up Python environment, install necessary dependencies, and execute dbt Cloud jobs for different databases (Snowflake, BigQuery, Postgres) based on the branch being pushed.
- `dbt-labs_jaffle-shop/.github/workflows/cd_staging.yml`: This module is designed to automate the deployment of staging environments for dbt projects using GitHub Actions. It includes three steps for each database type (Snowflake, BigQuery, and Postgres) that set up the necessary environment variables, install dependencies, and execute the dbt Cloud job with specified parameters such as account ID, project ID, PR job ID, API key, cause, and branch.
- `dbt-labs_jaffle-shop/.github/workflows/ci.yml`: This module is designed to automate the continuous integration (CI) process for a database project using GitHub Actions. It checks for pull requests in the `main` and `staging` branches, installs necessary dependencies, and runs dbt Cloud jobs to ensure that the changes meet the specified criteria. The purpose of this module is to maintain high-quality code and ensure that all changes are thoroughly tested before being merged into the main branch.
- `dbt-labs_jaffle-shop/.github/workflows/scripts/dbt_cloud_run_job.py`: This module is designed to automate the process of triggering and monitoring a dbt job. It reads environment variables for configuration, constructs a request payload with optional parameters like branch and schema override, triggers the job using the provided API key, and continuously checks the status of the job until it completes successfully or fails. The module provides clear outputs on the job's progress and failure reasons.
- `dbt-labs_jaffle-shop/.pre-commit-config.yaml`: This module is designed to integrate pre-commit hooks for code quality checks and formatting across multiple repositories using the `pre-commit` tool. It includes several hooks such as checking YAML files, fixing end-of-file issues, removing trailing whitespace, and ensuring that requirements.txt files are formatted correctly according to Ruff standards.
- `dbt-labs_jaffle-shop/Taskfile.yml`: This module is responsible for setting up a development environment, installing necessary packages, generating data, seeding the database with sample data, cleaning up the generated data, and finally loading the data into the database.
- `dbt-labs_jaffle-shop/dbt_project.yml`: This module configures a DBT project for the Jaffle Shop data warehouse, including setting up paths for different types of models and analyses, specifying variables, and configuring clean targets.
- `dbt-labs_jaffle-shop/macros/cents_to_dollars.sql`: This module provides a reusable function `cents_to_dollars` that converts a specified column from cents to dollars in a project-wide manner. It supports various database backends by dispatching the conversion logic to different functions based on the target database type.
- `dbt-labs_jaffle-shop/macros/generate_schema_name.sql`: This module generates a database schema name based on the provided `custom_schema_name` and the target environment. It prepends the `default_schema` with the `custom_schema_name` in production to clearly label the schemas, ensuring they are easily identifiable for different environments.
- `dbt-labs_jaffle-shop/models/marts/customers.sql`: This module calculates a summary of customer orders, including the number of lifetime orders, whether they are repeat buyers, and their spending history. It joins customer data with order data to provide detailed insights into customer behavior over time.
- `dbt-labs_jaffle-shop/models/marts/customers.yml`: This module provides a comprehensive overview of customer data, including key details such as customer ID, full name, order count, first and last order dates, total spend before tax, and total spend inclusive of taxes. It also includes metrics to calculate the lifetime spend pre-tax, the number of lifetime orders, and the average order value.
- `dbt-labs_jaffle-shop/models/marts/locations.sql`: This SQL query retrieves all records from the `stg_locations` staging table and presents them in a result set.
- `dbt-labs_jaffle-shop/models/marts/locations.yml`: This module defines a location dimension table in the semantic model, including primary key `location_id`, categorical dimensions `location_name` and `opened_date`, and an aggregate measure `average_tax_rate`.
- `dbt-labs_jaffle-shop/models/marts/metricflow_time_spine.sql`: This module generates a table containing dates for the past 10 years.
- `dbt-labs_jaffle-shop/models/marts/order_items.sql`: This module is designed to generate a summary of supply costs for each product in an e-commerce order, including the total cost of supplies used in each order. It joins multiple staging tables (stg_order_items, stg_orders, stg_products, and stg_supplies) to provide comprehensive data on products ordered by customers, their prices, and the cost of any supplies they may have purchased along with them.
- `dbt-labs_jaffle-shop/models/marts/order_items.yml`: This module defines a data model for order items, including columns for order item ID, order ID, product ID, and other relevant information. It also includes unit tests to verify the correctness of the counts of drinks and food orders. The semantic models define the structure and relationships between different entities in the data model, including dimensions such as ordered_at and is_food_item/is_drink_item. Metrics are defined to calculate various financial metrics for each order item, such as revenue, order cost, median revenue, and derived metrics like revenue growth and order gross profit. Finally, saved queries are defined to generate reports on revenue metrics over time.
- `dbt-labs_jaffle-shop/models/marts/orders.sql`: This module calculates the total cost, subtotal, and item counts for each order, categorizes them into food and drink items, and determines if an order is primarily a food or drink order based on these criteria. It also provides a row number for each customer's order to facilitate tracking in the final output.
- `dbt-labs_jaffle-shop/models/marts/orders.yml`: This module provides a comprehensive data mart for managing and analyzing orders, including key details such as customer information, order total, and item breakdown. It includes unit tests to ensure the accuracy of the data processing logic and semantic models to define the structure and relationships between different data entities. The metrics provide insights into various aspects of the order data, such as new customers, large orders, and specific types of orders (food vs. drink).
- `dbt-labs_jaffle-shop/models/marts/products.sql`: This module retrieves and presents all product data from the staging table `stg_products`.
- `dbt-labs_jaffle-shop/models/marts/products.yml`: This module defines a semantic model named "products" that represents the product dimension table in a database. It includes entities and dimensions to provide context for metrics, such as product name, type, description, price, and whether it is a food item or drink item. The model is referenced by the dbt model 'ref('products')'.
- `dbt-labs_jaffle-shop/models/marts/supplies.sql`: This module retrieves and selects all data from the `stg_supplies` table, which is assumed to be a staging area for supply-related information.
- `dbt-labs_jaffle-shop/models/marts/supplies.yml`: This module defines a semantic model named "supplies" that represents a dimension table in the database, containing one row per supply and product combination. The grain of the table is based on the primary key `supply_uuid`, which uniquely identifies each supply and product combination. The module includes entities for the primary key `supply` and dimensions such as `supply_id`, `product_id`, `supply_name`, `supply_cost`, and `is_perishable_supply`.
- `dbt-labs_jaffle-shop/models/staging/__sources.yml`: This module is designed to manage and analyze e-commerce data for the Jaffle Shop, including customer information, order details, item listings, store operations, product descriptions, and supply management. It provides a structured way to access and process this data for business intelligence, reporting, and decision-making purposes.
- `dbt-labs_jaffle-shop/models/staging/stg_customers.sql`: This module is designed to extract and transform raw customer data from a specified S3 bucket, converting it into a structured format suitable for further analysis or processing in a data warehouse.
- `dbt-labs_jaffle-shop/models/staging/stg_customers.yml`: This module is designed to clean and transform customer data, ensuring that it meets the necessary standards for analysis and storage. It includes basic cleaning steps such as removing null values and ensuring uniqueness of customer identifiers.
- `dbt-labs_jaffle-shop/models/staging/stg_locations.sql`: This module is designed to extract and transform data from the `raw_stores` table in the `ecom` database, specifically focusing on extracting location IDs, names, tax rates, and opening dates. The transformed data is then stored in a new table named `renamed`.
- `dbt-labs_jaffle-shop/models/staging/stg_locations.yml`: This module defines a data model for storing open locations with basic cleaning and transformation applied, one row per location. It includes a test function to ensure that the `opened_at` timestamp is properly truncated to a date.
- `dbt-labs_jaffle-shop/models/staging/stg_order_items.sql`: This module extracts raw item data from the E-commerce database, renames it to standardize column names, and then selects all columns from the renamed table.
- `dbt-labs_jaffle-shop/models/staging/stg_order_items.yml`: This module defines a table named `stg_order_items` that stores individual food and drink items in our orders, with columns for the unique key of each item (`order_item_id`) and the corresponding order it belongs to (`order_id`). The data tests ensure that these fields are not null and have unique values.
- `dbt-labs_jaffle-shop/models/staging/stg_orders.sql`: This module is designed to transform raw orders data from the 'ecom' database into a more structured format, including converting numeric values to dollars and truncating timestamps. It then selects all columns from the transformed data for further analysis or reporting purposes.
- `dbt-labs_jaffle-shop/models/staging/stg_orders.yml`: This module processes and cleans the `stg_orders` table, ensuring that each row represents a complete order with accurate financial calculations. It performs basic cleaning such as removing any missing values or duplicates before applying transformations to calculate the subtotal based on the total order amount minus tax paid. The data tests ensure that the cleaned data meets specific business requirements, such as checking for null values and ensuring uniqueness in the `order_id`.
- `dbt-labs_jaffle-shop/models/staging/stg_products.sql`: This module takes raw product data from an external database, renames it to more meaningful names, and converts prices from cents to dollars. It then categorizes products based on their type (food or drink).
- `dbt-labs_jaffle-shop/models/staging/stg_products.yml`: This module is designed to store and manage product data related to food and drink items that can be ordered. It includes basic cleaning and transformation steps such as removing null values and ensuring uniqueness of the product ID column, which are crucial for maintaining data integrity and facilitating efficient querying and analysis.
- `dbt-labs_jaffle-shop/models/staging/stg_supplies.sql`: This module extracts raw supply data from the 'ecom' database's 'raw_supplies' table, renames columns for clarity, converts cost to dollars, and generates a surrogate key for each supply record. It then selects all columns from the renamed dataset.
- `dbt-labs_jaffle-shop/models/staging/stg_supplies.yml`: This module is designed to manage and store supply expenses data, ensuring that each expense is uniquely identified by a UUID. It performs basic cleaning and transformation on the data, including handling fluctuations in supply costs by creating new rows for each cost.
- `dbt-labs_jaffle-shop/package-lock.yml`: This module provides utilities for database audits, including date manipulation and data validation.
- `dbt-labs_jaffle-shop/packages.yml`: This module provides a collection of utilities and functions for data analysis, including date manipulation, data validation, and more. It is designed to help users efficiently manage their data projects by providing a set of pre-built functions that can be easily integrated into their existing DBT pipelines.
