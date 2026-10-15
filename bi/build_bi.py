"""Export model-ready tables for Tableau and Power BI.

    python -m bi.build_bi

Writes bi/data/*.csv (a small star schema) and bi/kpis.json (the headline numbers your
dashboard should show, so you can check a Tableau or Power BI build against this repo).
Uses the cleaned `retail_sales` table from the SQL project, so every figure matches it.
"""

import json
from pathlib import Path

from analysis import data as d

OUT = Path(__file__).resolve().parent


def tables(con) -> dict:
    fact_sales = con.sql(
        """
        SELECT transaction_id, sale_date, CAST(sale_time AS VARCHAR) AS sale_time,
               EXTRACT(HOUR FROM sale_time) AS sale_hour,
               CASE WHEN EXTRACT(HOUR FROM sale_time) < 12 THEN 'Morning'
                    WHEN EXTRACT(HOUR FROM sale_time) <= 17 THEN 'Afternoon'
                    ELSE 'Evening' END AS shift,
               customer_id, gender, age,
               CASE WHEN age IS NULL THEN 'Unknown'
                    WHEN age < 25 THEN '18-24' WHEN age < 35 THEN '25-34'
                    WHEN age < 45 THEN '35-44' WHEN age < 55 THEN '45-54'
                    ELSE '55+' END AS age_band,
               category, quantity, price_per_unit, cogs, total_sale
        FROM retail_sales ORDER BY transaction_id
        """
    ).df()
    # RFM segment per customer, from the same SQL window-function logic as the live report.
    dim_customer = d.rfm(con)[["customer_id", "recency_days", "frequency", "monetary", "r", "f", "m", "segment"]]
    dim_customer = dim_customer.sort_values("customer_id").reset_index(drop=True)
    dim_date = con.sql(
        """
        SELECT CAST(d AS DATE) AS date, year(d) AS year, quarter(d) AS quarter,
               month(d) AS month_no, monthname(d) AS month, dayname(d) AS weekday, isodow(d) AS weekday_no
        FROM range((SELECT MIN(sale_date) FROM retail_sales), (SELECT MAX(sale_date) FROM retail_sales) + INTERVAL 1 DAY, INTERVAL 1 DAY) t(d)
        """
    ).df()
    return {"dim_customer": dim_customer, "dim_date": dim_date, "fact_sales": fact_sales}


def kpis(con, t: dict) -> dict:
    f = t["fact_sales"]
    q = d.quality(con).iloc[0]
    by_cat = f.groupby("category")["total_sale"].sum().sort_values(ascending=False)
    seg = t["dim_customer"]["segment"].value_counts()
    return {
        "Total sales": int(f["total_sale"].sum()),
        "Transactions": int(len(f)),
        "Customers": int(f["customer_id"].nunique()),
        "Average transaction value": round(float(f["total_sale"].mean()), 2),
        "Units sold": int(f["quantity"].sum()),
        "Top category by sales": f"{by_cat.index[0]} ({int(by_cat.iloc[0]):,})",
        "Rows removed in cleaning": int(q["rows_removed"]),
        "Champions (RFM segment)": int(seg.get("Champions", 0)),
        "Date range": f"{f['sale_date'].min():%Y-%m-%d} to {f['sale_date'].max():%Y-%m-%d}",
    }


def build(out: Path = OUT) -> dict:
    con = d.connect()
    t = tables(con)
    (out / "data").mkdir(parents=True, exist_ok=True)
    for name, df in t.items():
        df.to_csv(out / "data" / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    k = kpis(con, t)
    (out / "kpis.json").write_text(json.dumps(k, indent=2) + "\n")
    return {"tables": t, "kpis": k}


if __name__ == "__main__":
    res = build()
    for name, df in res["tables"].items():
        print(f"{name}: {len(df):,} rows")
    print(json.dumps(res["kpis"], indent=2))
