"""Load the retail sales CSV into DuckDB and answer the project's SQL questions."""

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "SQL - Retail Sales Analysis_utf .csv"


def connect(path: Path = RAW) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB with the raw table and the cleaned `retail_sales` table.

    The CSV's header has `transactions_id` and a typo, `quantiy`; the SQL file uses
    `transaction_id` and `quantity`, so the columns are renamed to match it.
    """
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE raw_sales AS
        SELECT
            transactions_id AS transaction_id,
            CAST(sale_date AS DATE) AS sale_date,
            CAST(sale_time AS TIME) AS sale_time,
            customer_id, gender, CAST(age AS INTEGER) AS age, category,
            CAST(quantiy AS INTEGER) AS quantity, price_per_unit, cogs, total_sale
        FROM read_csv_auto(?, header = true)
        """,
        [str(path)],
    )
    # The cleaning step from retail_sales_query_p1.sql (rows missing key fields are removed).
    con.execute(
        """
        CREATE TABLE retail_sales AS
        SELECT * FROM raw_sales
        WHERE NOT (
            transaction_id IS NULL OR sale_date IS NULL OR sale_time IS NULL OR gender IS NULL
            OR category IS NULL OR quantity IS NULL OR cogs IS NULL OR total_sale IS NULL
        )
        """
    )
    return con


def quality(con) -> pd.DataFrame:
    return con.sql(
        """
        SELECT
            (SELECT COUNT(*) FROM raw_sales)                         AS raw_rows,
            (SELECT COUNT(*) FROM raw_sales) - (SELECT COUNT(*) FROM retail_sales) AS rows_removed,
            (SELECT COUNT(*) FROM retail_sales WHERE age IS NULL)    AS rows_missing_age,
            (SELECT COUNT(*) FROM retail_sales WHERE ABS(total_sale - quantity * price_per_unit) > 0.01) AS totals_that_dont_add_up,
            (SELECT COUNT(*) FROM retail_sales WHERE cogs > price_per_unit) AS cogs_above_price
        """
    ).df()


# The ten business questions from retail_sales_query_p1.sql, in DuckDB SQL.
# Only dialect differences were changed (e.g. TO_CHAR -> strftime); the logic is the original's.
QUESTIONS = [
    ("Q1", "All sales made on 5 November 2022",
     "SELECT *\nFROM retail_sales\nWHERE sale_date = '2022-11-05';"),
    ("Q2", "Clothing transactions with 4 or more items in November 2022",
     "SELECT *\nFROM retail_sales\nWHERE category = 'Clothing'\n  AND strftime(sale_date, '%Y-%m') = '2022-11'\n  AND quantity >= 4;"),
    ("Q3", "Total sales and orders for each category",
     "SELECT category,\n       SUM(total_sale) AS net_sale,\n       COUNT(*) AS total_orders\nFROM retail_sales\nGROUP BY 1\nORDER BY net_sale DESC;"),
    ("Q4", "Average age of Beauty customers",
     "SELECT ROUND(AVG(age), 2) AS avg_age\nFROM retail_sales\nWHERE category = 'Beauty';"),
    ("Q5", "Transactions over 1,000",
     "SELECT *\nFROM retail_sales\nWHERE total_sale > 1000;"),
    ("Q6", "Transactions by gender in each category",
     "SELECT category, gender, COUNT(*) AS total_trans\nFROM retail_sales\nGROUP BY category, gender\nORDER BY 1;"),
    ("Q7", "Best month for average sale in each year",
     "SELECT year, month, avg_sale\nFROM (\n    SELECT EXTRACT(YEAR FROM sale_date) AS year,\n           EXTRACT(MONTH FROM sale_date) AS month,\n           AVG(total_sale) AS avg_sale,\n           RANK() OVER (PARTITION BY EXTRACT(YEAR FROM sale_date)\n                        ORDER BY AVG(total_sale) DESC) AS rank\n    FROM retail_sales\n    GROUP BY 1, 2\n) AS t1\nWHERE rank = 1;"),
    ("Q8", "Top 5 customers by total sales",
     "SELECT customer_id, SUM(total_sale) AS total_sales\nFROM retail_sales\nGROUP BY 1\nORDER BY 2 DESC\nLIMIT 5;"),
    ("Q9", "Unique customers in each category",
     "SELECT category, COUNT(DISTINCT customer_id) AS cnt_unique_cs\nFROM retail_sales\nGROUP BY category\nORDER BY 2 DESC;"),
    ("Q10", "Orders by shift (morning before 12, afternoon 12–17, evening after)",
     "WITH hourly_sale AS (\n    SELECT *,\n        CASE\n            WHEN EXTRACT(HOUR FROM sale_time) < 12 THEN 'Morning'\n            WHEN EXTRACT(HOUR FROM sale_time) BETWEEN 12 AND 17 THEN 'Afternoon'\n            ELSE 'Evening'\n        END AS shift\n    FROM retail_sales\n)\nSELECT shift, COUNT(*) AS total_orders\nFROM hourly_sale\nGROUP BY shift\nORDER BY total_orders DESC;"),
]


def answers(con) -> list[tuple[str, str, str, pd.DataFrame]]:
    return [(qid, title, sql, con.sql(sql).df()) for qid, title, sql in QUESTIONS]


# ------------------------------------------------------------ extra analysis --
def monthly(con) -> pd.DataFrame:
    return con.sql(
        """
        SELECT date_trunc('month', sale_date) AS month,
               SUM(total_sale) AS revenue, COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS customers
        FROM retail_sales GROUP BY 1 ORDER BY 1
        """
    ).df()


def category_by_age(con) -> pd.DataFrame:
    """Share of each age group's spending that goes to each category."""
    return con.sql(
        """
        WITH banded AS (
            SELECT CASE WHEN age < 30 THEN '18–29' WHEN age < 40 THEN '30–39' WHEN age < 50 THEN '40–49'
                        WHEN age < 60 THEN '50–59' ELSE '60+' END AS age_band, category, total_sale
            FROM retail_sales WHERE age IS NOT NULL
        )
        SELECT age_band, category, SUM(total_sale) / SUM(SUM(total_sale)) OVER (PARTITION BY age_band) AS share
        FROM banded GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()


def hourly(con) -> pd.DataFrame:
    return con.sql(
        """
        SELECT EXTRACT(HOUR FROM sale_time) AS hour, COUNT(*) AS orders, SUM(total_sale) AS revenue
        FROM retail_sales GROUP BY 1 ORDER BY 1
        """
    ).df()


def rfm(con) -> pd.DataFrame:
    """Recency, frequency and monetary value per customer, scored 1-4 (quartiles) with SQL window functions."""
    return con.sql(
        """
        WITH base AS (
            SELECT customer_id,
                   DATE_DIFF('day', MAX(sale_date), (SELECT MAX(sale_date) FROM retail_sales)) AS recency_days,
                   COUNT(*) AS frequency,
                   SUM(total_sale) AS monetary
            FROM retail_sales GROUP BY customer_id
        ), scored AS (
            SELECT *,
                   5 - NTILE(4) OVER (ORDER BY recency_days) AS r,
                   NTILE(4) OVER (ORDER BY frequency) AS f,
                   NTILE(4) OVER (ORDER BY monetary) AS m
            FROM base
        )
        SELECT *,
               CASE
                   WHEN r >= 3 AND f + m >= 7 THEN 'Champions'
                   WHEN r >= 3 THEN 'Active'
                   WHEN f + m >= 6 THEN 'Valuable but slipping'
                   ELSE 'Lapsed'
               END AS segment
        FROM scored ORDER BY monetary DESC
        """
    ).df()


def cohorts(con) -> pd.DataFrame:
    """Share of each quarterly cohort (by first purchase) that buys again in later quarters."""
    return con.sql(
        """
        WITH q AS (
            SELECT customer_id, date_trunc('quarter', sale_date) AS quarter FROM retail_sales GROUP BY 1, 2
        ), first AS (
            SELECT customer_id, MIN(quarter) AS cohort FROM q GROUP BY 1
        ), joined AS (
            SELECT f.cohort, DATE_DIFF('quarter', f.cohort, q.quarter) AS quarters_later, q.customer_id
            FROM q JOIN first f USING (customer_id)
        )
        SELECT cohort, quarters_later,
               COUNT(DISTINCT customer_id) AS customers,
               COUNT(DISTINCT customer_id) / FIRST(COUNT(DISTINCT customer_id)) OVER (PARTITION BY cohort ORDER BY quarters_later) AS retention
        FROM joined GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()


def clean_csv(con, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con.sql("SELECT * FROM retail_sales ORDER BY transaction_id").write_csv(str(path))
