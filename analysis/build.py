"""Run the retail SQL analysis and write the website to site/index.html.

    python -m analysis.build
"""

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import data
from .report import AXIS, BLUE, GRID, INK_2, MUTED, ORANGE, SEQUENTIAL, SERIES, Report, money, style, table_html, to_json

REPO = "Scarface96/sql_retail_sales_p1"
DUCKDB_WASM = "1.32.0"


def monthly_figure(m: pd.DataFrame) -> go.Figure:
    m = m.copy()
    m["year"] = m["month"].dt.year
    m["mon"] = m["month"].dt.strftime("%b")
    fig = go.Figure()
    for i, (year, g) in enumerate(m.groupby("year")):
        fig.add_scatter(x=g["mon"], y=g["revenue"], name=str(year), mode="lines+markers", line=dict(color=SERIES[i], width=2),
                        marker=dict(size=8, line=dict(color="#fcfcfb", width=2)),
                        customdata=np.stack([g["orders"], g["customers"]], axis=1),
                        hovertemplate=f"%{{x}} {year}<br>Revenue %{{y:,.0f}}<br>%{{customdata[0]}} orders from %{{customdata[1]}} customers<extra></extra>")
    style(fig, height=380)
    fig.update_yaxes(title="Revenue", rangemode="tozero")
    return fig


def hourly_figure(h: pd.DataFrame) -> go.Figure:
    shift = np.where(h["hour"] < 12, "Morning", np.where(h["hour"] <= 17, "Afternoon", "Evening"))
    colors = {"Morning": SERIES[0], "Afternoon": SERIES[1], "Evening": SERIES[2]}
    fig = go.Figure()
    for name in ["Morning", "Afternoon", "Evening"]:
        g = h[shift == name]
        fig.add_bar(x=g["hour"], y=g["orders"], name=name, marker_color=colors[name],
                    hovertemplate="%{x}:00–%{x}:59<br>%{y} orders<extra>" + name + "</extra>")
    style(fig, height=340)
    fig.update_xaxes(title="Hour of day", dtick=2)
    fig.update_yaxes(title="Orders")
    return fig


def age_mix_figure(t: pd.DataFrame) -> go.Figure:
    p = t.pivot(index="age_band", columns="category", values="share")
    fig = go.Figure(go.Heatmap(
        z=p.values, x=p.columns, y=p.index, colorscale=[[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)],
        zmin=0, zmax=0.6, xgap=3, ygap=3, text=[[f"{v:.0%}" for v in row] for row in p.values], texttemplate="%{text}",
        textfont=dict(size=14), colorbar=dict(tickformat=".0%", thickness=12, outlinewidth=0, title=dict(text="Share of<br>spend")),
        hovertemplate="%{y}: %{z:.0%} of spending on %{x}<extra></extra>",
    ))
    style(fig, height=340, legend=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, title="Age")
    fig.update_xaxes(side="top")
    return fig


SEGMENT_ORDER = ["Champions", "Active", "Valuable but slipping", "Lapsed"]


def rfm_figure(r: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for i, seg in enumerate(SEGMENT_ORDER):
        g = r[r["segment"] == seg]
        fig.add_scatter(x=g["frequency"], y=g["monetary"], mode="markers", name=f"{seg} ({len(g)})",
                        marker=dict(color=SERIES[i], size=np.clip(18 - g["recency_days"] / 20, 7, 18), line=dict(color="#fcfcfb", width=1.5), opacity=0.9),
                        customdata=np.stack([g["customer_id"], g["recency_days"]], axis=1),
                        hovertemplate="Customer %{customdata[0]}<br>%{x} purchases, %{y:,.0f} spent<br>Last purchase %{customdata[1]} days before the data ends<extra>" + seg + "</extra>")
    style(fig, height=440)
    fig.update_xaxes(title="Number of purchases", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(title="Total spent")
    return fig


def cohort_figure(c: pd.DataFrame) -> go.Figure:
    p = c.pivot(index="cohort", columns="quarters_later", values="retention")
    n = c[c["quarters_later"] == 0].set_index("cohort")["customers"]
    labels = [f"{d.year} Q{(d.month - 1) // 3 + 1} ({n[d]} new)" for d in p.index]
    fig = go.Figure(go.Heatmap(
        z=p.values, x=[f"+{q}" for q in p.columns], y=labels, colorscale=[[i / (len(SEQUENTIAL) - 1), col] for i, col in enumerate(SEQUENTIAL)],
        zmin=0, zmax=1, xgap=3, ygap=3, text=[["" if pd.isna(v) else f"{v:.0%}" for v in row] for row in p.values], texttemplate="%{text}",
        colorbar=dict(tickformat=".0%", thickness=12, outlinewidth=0, title=dict(text="Bought<br>again")),
        hovertemplate="%{y}<br>%{x} quarters later: %{z:.0%} bought again<extra></extra>",
    ))
    style(fig, height=320, legend=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, title="First purchase")
    fig.update_xaxes(title="Quarters after first purchase", side="bottom")
    return fig


def questions_html(answers) -> str:
    parts = []
    for qid, title, sql, df in answers:
        shown = df.head(8).copy()
        for col in shown.columns:
            if pd.api.types.is_datetime64_any_dtype(shown[col]):
                shown[col] = shown[col].dt.strftime("%Y-%m-%d")
            elif shown[col].dtype == object:
                shown[col] = shown[col].astype(str)
        more = f'<p class="note">{len(df):,} rows; first 8 shown.</p>' if len(df) > 8 else f'<p class="note">{len(df):,} row{"s" if len(df) != 1 else ""}.</p>'
        parts.append(
            f'<div class="qa"><h3>{qid}. {html.escape(title)}</h3><pre class="sql">{html.escape(sql)}</pre><div>{table_html(shown)}{more}</div></div>'
        )
    return "".join(parts)


EXAMPLES = {
    "Revenue by category and gender": "SELECT category, gender,\n       SUM(total_sale) AS revenue,\n       COUNT(*) AS orders\nFROM retail_sales\nGROUP BY ALL\nORDER BY revenue DESC;",
    "Busiest weekdays": "SELECT dayname(sale_date) AS weekday,\n       COUNT(*) AS orders,\n       ROUND(AVG(total_sale), 2) AS avg_sale\nFROM retail_sales\nGROUP BY ALL\nORDER BY orders DESC;",
    "Customers' first and last purchase": "SELECT customer_id,\n       MIN(sale_date) AS first_purchase,\n       MAX(sale_date) AS last_purchase,\n       COUNT(*) AS purchases\nFROM retail_sales\nGROUP BY ALL\nORDER BY purchases DESC\nLIMIT 10;",
    "Running revenue total in 2023": "SELECT date_trunc('month', sale_date) AS month,\n       SUM(total_sale) AS revenue,\n       SUM(SUM(total_sale)) OVER (ORDER BY date_trunc('month', sale_date)) AS running_total\nFROM retail_sales\nWHERE year(sale_date) = 2023\nGROUP BY ALL\nORDER BY month;",
}

PLAYGROUND = f"""
<form class="controls" id="pg-form" onsubmit="return false">
  <label>Start from an example<select id="pg-examples">{''.join(f'<option>{html.escape(k)}</option>' for k in EXAMPLES)}</select></label>
</form>
<label class="sr-only" for="pg-sql">SQL query</label>
<textarea id="pg-sql" class="sql" spellcheck="false"></textarea>
<div class="controls" style="margin-top:10px;align-items:center">
  <button type="button" class="run" id="pg-run" disabled>Run query</button>
  <span id="pg-status" class="note" style="margin:0">Loading DuckDB in your browser…</span>
</div>
<div id="pg-out"></div>
<p class="note">The table is <code>retail_sales</code> with columns transaction_id, sale_date, sale_time, customer_id, gender, age, category, quantity, price_per_unit, cogs, total_sale. Press Ctrl+Enter (⌘+Enter on Mac) to run. Everything runs in your browser; nothing is sent anywhere.</p>
"""


def playground_js() -> str:
    return f"""
import * as duckdb from 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@{DUCKDB_WASM}/+esm';
const EX = {to_json(EXAMPLES)};
const $ = id => document.getElementById(id);
const status = t => $('pg-status').textContent = t;
$('pg-sql').value = Object.values(EX)[0];
$('pg-examples').addEventListener('change', e => {{ $('pg-sql').value = EX[e.target.value]; }});
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
function cell(v, type) {{
  if (v === null || v === undefined) return '–';
  const t = String(type);
  if (t.startsWith('Decimal')) {{ v = Number(String(v)) / 10 ** (type.scale || 0); }}
  if (t.startsWith('Date')) return new Date(Number(v)).toISOString().slice(0, 10);
  if (t.startsWith('Time')) {{ const s = Number(v) / 1e6; return [s / 3600, (s % 3600) / 60, s % 60].map(x => String(Math.floor(x)).padStart(2, '0')).join(':'); }}
  if (t.startsWith('Timestamp')) return new Date(Number(v)).toISOString().slice(0, 10);
  if (typeof v === 'bigint') return v.toLocaleString();
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, {{maximumFractionDigits: 2}});
  return esc(v);
}}
let conn;
async function boot() {{
  try {{
    const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
    const workerUrl = URL.createObjectURL(new Blob([`importScripts("${{bundle.mainWorker}}");`], {{type: 'text/javascript'}}));
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(workerUrl));
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(workerUrl);
    const csv = await (await fetch('data/retail_sales_clean.csv')).text();
    await db.registerFileText('retail_sales.csv', csv);
    conn = await db.connect();
    await conn.query(`CREATE TABLE retail_sales AS
      SELECT transaction_id::INTEGER AS transaction_id, sale_date::DATE AS sale_date, sale_time::TIME AS sale_time,
             customer_id::INTEGER AS customer_id, gender, age::INTEGER AS age, category, quantity::INTEGER AS quantity,
             price_per_unit::DOUBLE AS price_per_unit, cogs::DOUBLE AS cogs, total_sale::DOUBLE AS total_sale
      FROM read_csv_auto('retail_sales.csv')`);
    status('Ready. 1,997 rows loaded.');
    $('pg-run').disabled = false;
    run();
  }} catch (e) {{
    status('The SQL engine could not load in this browser. The queries and results above still show the analysis.');
  }}
}}
async function run() {{
  if (!conn) return;
  $('pg-run').disabled = true; status('Running…');
  const t0 = performance.now();
  try {{
    const res = await conn.query($('pg-sql').value);
    const fields = res.schema.fields;
    const rows = res.toArray().slice(0, 200);
    const head = fields.map(f => `<th>${{esc(f.name)}}</th>`).join('');
    const body = rows.map(r => '<tr>' + fields.map(f => {{ const v = r[f.name]; const num = typeof v === 'number' || typeof v === 'bigint' || String(f.type).startsWith('Decimal'); return `<td class="${{num ? 'num' : ''}}">${{cell(v, f.type)}}</td>`; }}).join('') + '</tr>').join('');
    $('pg-out').innerHTML = `<div class="table-wrap" style="max-height:420px;overflow:auto"><table><thead><tr>${{head}}</tr></thead><tbody>${{body}}</tbody></table></div>`;
    status(`${{res.numRows.toLocaleString()}} row${{res.numRows === 1 ? '' : 's'}} in ${{Math.round(performance.now() - t0)}} ms` + (res.numRows > 200 ? ' (first 200 shown)' : '') + '.');
  }} catch (e) {{
    $('pg-out').innerHTML = `<pre class="sql" style="background:#3a1d1b">${{esc(e.message || e)}}</pre>`;
    status('That query has an error.');
  }}
  $('pg-run').disabled = false;
}}
$('pg-run').addEventListener('click', run);
$('pg-sql').addEventListener('keydown', e => {{ if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {{ e.preventDefault(); run(); }} }});
boot();
"""


def main(out="site/index.html"):
    con = data.connect()
    q = data.quality(con).iloc[0]
    answers = data.answers(con)
    A = {qid: df for qid, _, _, df in answers}
    m = data.monthly(con)
    h = data.hourly(con)
    mix = data.category_by_age(con)
    rfm = data.rfm(con)
    coh = data.cohorts(con)
    tot = con.sql("SELECT SUM(total_sale) AS revenue, COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS customers FROM retail_sales").df().iloc[0]
    new_2023 = con.sql("SELECT COUNT(*) FROM (SELECT customer_id, MIN(sale_date) d FROM retail_sales GROUP BY 1) WHERE year(d) = 2023").fetchone()[0]
    yearly = m.groupby(m["month"].dt.year)["revenue"].sum()
    best_rev = m.loc[m.groupby(m["month"].dt.year)["revenue"].idxmax()]
    shifts = A["Q10"].set_index("shift")["total_orders"]
    seg = rfm.groupby("segment").agg(customers=("customer_id", "size"), revenue=("monetary", "sum"))
    champ = seg.loc["Champions"]
    top20 = rfm.nlargest(int(len(rfm) * 0.2), "monetary")["monetary"].sum() / rfm["monetary"].sum()
    q4 = coh[(coh["cohort"] == coh["cohort"].min())].set_index("quarters_later")["retention"]
    old = mix[mix["age_band"] == "60+"].set_index("category")["share"]

    r = Report(
        title="Every customer this store has was won in 2022. Its future depends on keeping them.",
        project="Retail Sales Analysis (SQL)",
        summary=(
            f"{int(tot['orders']):,} transactions from {int(tot['customers'])} customers brought in {money(tot['revenue'], '')} in 2022 and 2023. "
            f"The original SQL questions are answered below by running the project's queries in DuckDB, and a live SQL editor lets you write your own. "
            f"Python adds customer segmentation and cohort retention, which show that no new customers arrived in 2023."
        ),
        repo=REPO,
        accent=SERIES[5],
        source="SQL - Retail Sales Analysis_utf.csv: 2,000 retail transactions (Jan 2022 – Dec 2023) across Beauty, Clothing and Electronics. Amounts are in the dataset's own currency units.",
        method=(
            "Python loads the CSV into DuckDB and runs the cleaning step and the ten business questions from retail_sales_query_p1.sql (only "
            "dialect differences changed). Segmentation scores recency, frequency and spend in quartiles with SQL window functions; cohorts group "
            f"customers by their first purchase quarter. The live editor runs DuckDB-WASM {DUCKDB_WASM} in your browser."
        ),
    )
    r.kpis([
        (money(tot["revenue"], ""), "revenue", f"{int(tot['orders']):,} transactions"),
        (f"{int(tot['customers'])}", "customers", f"{new_2023} new in 2023"),
        (f"{shifts['Evening'] / shifts.sum():.0%}", "of orders in the evening", "6 pm onwards, as defined in Q10"),
        (f"{top20:.0%}", "of revenue from the top 20% of customers"),
    ])

    qt = pd.DataFrame([q]).T.reset_index()
    qt.columns = ["check", "rows"]
    r.section(
        "Is the data clean enough to trust?",
        f"<p>Mostly. The SQL cleaning step removes <b>{int(q['rows_removed'])} rows</b> with missing quantity, price and cost, leaving {int(tot['orders']):,}. "
        f"Every remaining total equals quantity × price. {int(q['rows_missing_age'])} rows have no age and are left out of age analysis only.</p>"
        f"<p>One column needs care: <b>cogs is higher than the selling price in {int(q['cogs_above_price'])} rows</b>, so it isn't clear whether it's per unit or per "
        "transaction. This report doesn't calculate profit from it. The CSV also spells quantity as <code>quantiy</code>; the code renames it to match the SQL.</p>",
        html=table_html(qt),
    )
    r.section(
        "The ten business questions, answered in SQL",
        "<p>Each query from <code>retail_sales_query_p1.sql</code>, run against the cleaned table, beside its actual result. "
        f"Electronics edges Clothing on revenue ({money(A['Q3'].iloc[0]['net_sale'], '')} vs {money(A['Q3'].iloc[1]['net_sale'], '')}), "
        f"the evening shift handles over half of all orders, and the top five customers each spent more than {money(A['Q8']['total_sales'].min(), '')}.</p>",
        html=questions_html(answers),
        note="Q2's comment in the SQL file says 'more than 10' items, but its query uses 4 or more, the most a transaction ever has. The query's version is shown.",
    )
    mt = m.copy()
    mt["month"] = mt["month"].dt.strftime("%b %Y")
    r.section(
        "How do sales move through the year?",
        f"<p>Revenue was almost identical in both years ({money(yearly.iloc[0], '')} and {money(yearly.iloc[1], '')}) and follows one pattern: "
        f"roughly flat from January to August, then <b>close to triple that level from September to December</b>. Those four months bring in "
        f"{m.loc[m['month'].dt.month >= 9, 'revenue'].sum() / m['revenue'].sum():.0%} of the year's revenue. The best month by total revenue was "
        f"{best_rev.iloc[0]['month']:%B} in 2022 and {best_rev.iloc[1]['month']:%B} in 2023, which differs from Q7's answer because Q7 ranks months by "
        "average sale, not total.</p>",
        fig=monthly_figure(m), table=mt.round(0),
    )
    r.section(
        "When do people shop?",
        f"<p>Orders run steadily through the morning (about {h.loc[h['hour'].between(6, 11), 'orders'].mean():.0f} an hour), almost stop between noon and 5 pm "
        f"(about {h.loc[h['hour'].between(12, 16), 'orders'].mean():.0f}), then jump to about <b>{h.loc[h['hour'].between(17, 22), 'orders'].mean():.0f} an hour from 5 pm to 11 pm</b>. "
        "Staffing and promotions timed for the evening reach the most customers; midday is the natural slot for restocking.</p>",
        fig=hourly_figure(h), table=h,
    )
    r.section(
        "What does each age group buy?",
        f"<p>Spending is evenly split for most ages, but tilts with age: customers over 60 put <b>{old['Electronics']:.0%} of their spending into Electronics</b> "
        f"and only {old['Beauty']:.0%} into Beauty.</p>",
        fig=age_mix_figure(mix),
        table=mix.pivot(index="age_band", columns="category", values="share").mul(100).round(1).reset_index(),
    )
    seg_t = seg.loc[SEGMENT_ORDER].reset_index()
    seg_t["share_of_revenue"] = (seg_t["revenue"] / seg_t["revenue"].sum() * 100).round(1)
    r.section(
        "Who are the best customers?",
        f"<p>Each customer is scored on how recently, how often and how much they buy. <b>{int(champ['customers'])} Champions</b> "
        f"({champ['customers'] / len(rfm):.0%} of customers) bring in {champ['revenue'] / rfm['monetary'].sum():.0%} of revenue. "
        f"{int(seg.loc['Valuable but slipping', 'customers'])} high-value customers haven't bought recently, and they are the best target for a win-back offer.</p>",
        fig=rfm_figure(rfm), table=seg_t.round(0).rename(columns={"share_of_revenue": "% of revenue"}),
        note="Bigger dots bought more recently. Hover a dot for the customer.",
    )
    r.section(
        "Do customers come back?",
        f"<p>Strongly, and seasonally. Of the customers who first bought in early 2022, {q4.loc[3]:.0%} bought again in the fourth quarter that year and "
        f"{q4.loc[7]:.0%} in the fourth quarter of 2023. But <b>every cohort is from 2022: not a single new customer arrived in 2023</b>. "
        "The business is living off its existing base, so acquisition is the gap to close.</p>",
        fig=cohort_figure(coh),
        table=coh.assign(cohort=coh["cohort"].dt.strftime("%Y-%m"), retention=(coh["retention"] * 100).round(1)),
    )
    r.section(
        "Try your own SQL",
        "<p>A real SQL engine runs in this page. Pick an example or write any query against <code>retail_sales</code>, then run it.</p>",
        html=PLAYGROUND,
    )
    r.script(playground_js(), module=True)

    path = r.write(out)
    data.clean_csv(con, path.parent / "data" / "retail_sales_clean.csv")
    print(f"Wrote {path} ({path.stat().st_size / 1024:.0f} KB) and the cleaned CSV for the SQL editor.")
    return r


if __name__ == "__main__":
    main()
