# Tableau calculated fields: Retail Sales Analysis

Create each one with **Analysis → Create Calculated Field**, name it exactly as shown, and paste the formula.
Tableau shows CSV columns in title case (`new_cases` becomes *New Cases*). If yours show the raw names, use those in the formulas.

## Connect the data

Connect to the fact table, then drag each dimension table onto the canvas and relate it:

- `fact_sales.customer_id` = `dim_customer.customer_id`
- `fact_sales.sale_date` = `dim_date.date`

## Fields

### Avg Transaction Value

```
SUM([Total Sale]) / COUNT([Transaction Id])
```

### Sales per Customer

```
SUM([Total Sale]) / COUNTD([Customer Id])
```

### Sales YoY %

```
(SUM([Total Sale]) - LOOKUP(SUM([Total Sale]), -1)) / ABS(LOOKUP(SUM([Total Sale]), -1))
```

Table calculation: compute using Year with Month on the view.

### Shift Order

```
CASE [Shift] WHEN "Morning" THEN 1 WHEN "Afternoon" THEN 2 ELSE 3 END
```

Sort the Shift field by this.
