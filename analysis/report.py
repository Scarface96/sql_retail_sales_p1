"""Turn an analysis into a single, self-contained interactive web page.

Every chart is a Plotly figure, so the published page keeps hover, zoom and
legend toggles. Each chart can carry its numbers in a "Show the data" table,
so nothing depends on colour alone.

Usage:
    report = Report(title=..., project=..., summary=..., repo="Scarface96/repo")
    report.kpis([("10,000", "customers"), ...])
    report.section("Who leaves?", "Short takeaway.", fig=figure, table=df)
    report.write("site/index.html")
"""

from __future__ import annotations

import datetime as dt
import html
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version

# ---------------------------------------------------------------- palette ---
# Colour-blind-validated categorical order (use in this order, never cycled).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = SERIES
# Single-hue ramp for magnitude (light -> dark).
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Two-arm ramp with a neutral midpoint for +/- values.
DIVERGING = ["#184f95", "#3987e5", "#9ec5f4", "#f0efec", "#f2a3a2", "#e34948", "#a32c2b"]
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
GOOD = "#006300"
FONT = '"Public Sans", system-ui, -apple-system, "Segoe UI", sans-serif'


def style(fig: go.Figure, height: int = 420, legend: bool | None = None) -> go.Figure:
    """Apply the house chart style: quiet axes, hairline grid, readable hover."""
    fig.update_layout(
        height=height,
        font=dict(family=FONT, size=13, color=INK_2),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=SERIES,
        margin=dict(l=8, r=16, t=16, b=8),
        hoverlabel=dict(bgcolor="white", bordercolor=AXIS, font=dict(family=FONT, size=13, color=INK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text="", font=dict(size=13)),
        bargap=0.25,
        title=None,
    )
    if legend is not None:
        fig.update_layout(showlegend=legend)
    fig.update_xaxes(showgrid=False, linecolor=AXIS, ticks="", tickfont=dict(color=MUTED), title_font=dict(color=INK_2), automargin=True, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, linecolor=AXIS, showline=False, ticks="", tickfont=dict(color=MUTED), title_font=dict(color=INK_2), automargin=True, zeroline=False)
    return fig


# ----------------------------------------------------------------- report ---
@dataclass
class Section:
    heading: str
    text: str
    fig: go.Figure | None = None
    table: pd.DataFrame | None = None
    html: str | None = None
    note: str | None = None
    table_caption: str = "Show the data"


@dataclass
class Report:
    title: str              # the headline finding
    project: str            # the project name
    summary: str            # one or two sentences under the headline
    repo: str               # "owner/name" on GitHub
    accent: str = BLUE
    source: str = ""        # data source line (HTML allowed)
    method: str = ""        # how it was built (HTML allowed)
    _kpis: list = field(default_factory=list)
    _sections: list = field(default_factory=list)
    _scripts: list = field(default_factory=list)

    def kpis(self, items):
        """items: [(value, label)] or [(value, label, note)]"""
        self._kpis = list(items)
        return self

    def section(self, heading, text, fig=None, table=None, html=None, note=None, table_caption="Show the data"):
        self._sections.append(Section(heading, text, fig, table, html, note, table_caption))
        return self

    def script(self, js: str, module: bool = False):
        """Extra JavaScript appended once at the end of the page (optionally as an ES module)."""
        self._scripts.append((js, module))
        return self

    # -- rendering -----------------------------------------------------------
    def _kpi_html(self):
        if not self._kpis:
            return ""
        cells = []
        for item in self._kpis:
            value, label, *rest = item
            note = f'<span class="kpi-note">{rest[0]}</span>' if rest and rest[0] else ""
            cells.append(f'<div class="kpi"><b>{value}</b><span>{label}</span>{note}</div>')
        return f'<div class="kpis">{"".join(cells)}</div>'

    def _section_html(self, s: Section, index: int):
        parts = [f'<section id="s{index}"><h2>{s.heading}</h2><div class="lede">{s.text}</div>']
        if s.html:
            parts.append(f'<div class="block">{s.html}</div>')
        if s.fig is not None:
            fig_html = s.fig.to_html(
                full_html=False,
                include_plotlyjs=False,
                config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"]},
            )
            parts.append(f'<figure class="chart">{fig_html}</figure>')
        if s.note:
            parts.append(f'<p class="note">{s.note}</p>')
        if s.table is not None:
            parts.append(f"<details><summary>{s.table_caption}</summary>{table_html(s.table)}</details>")
        parts.append("</section>")
        return "".join(parts)

    def render(self) -> str:
        built = dt.datetime.now(dt.timezone.utc).strftime("%d %B %Y")
        body = "".join(self._section_html(s, i) for i, s in enumerate(self._sections, 1))
        scripts = "".join(f'<script{" type=module" if module else ""}>{js}</script>' for js, module in self._scripts)
        return PAGE.format(
            title=html.escape(self.title),
            project=html.escape(self.project),
            summary=self.summary,
            kpis=self._kpi_html(),
            body=body,
            source=self.source,
            method=self.method,
            repo=self.repo,
            built=built,
            accent=self.accent,
            plotly=get_plotlyjs_version(),
            css=CSS,
            scripts=scripts,
        )

    def write(self, path="site/index.html"):
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.render(), encoding="utf-8")
        (out.parent / ".nojekyll").write_text("")
        return out


def table_html(df: pd.DataFrame, max_rows: int = 60) -> str:
    """A plain, readable HTML table; numbers right-aligned with tabular figures."""
    df = df.head(max_rows)
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            num = isinstance(v, (int, float)) and not isinstance(v, bool)
            text = fmt(v) if num else html.escape(str(v))
            cells.append(f'<td class="{"num" if num else ""}">{text}</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def fmt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        if abs(v) >= 10:
            return f"{v:,.1f}"
        return f"{v:,.2f}"
    return f"{v:,}"


def money(v: float, symbol: str = "$") -> str:
    """$1.2M / $350K / $980"""
    a = abs(v)
    if a >= 1e9:
        return f"{symbol}{v / 1e9:.1f}B"
    if a >= 1e6:
        return f"{symbol}{v / 1e6:.1f}M"
    if a >= 1e4:
        return f"{symbol}{v / 1e3:.0f}K"
    return f"{symbol}{v:,.0f}"


def pct(v: float, digits: int = 1) -> str:
    return f"{v * 100:.{digits}f}%"


def to_json(obj) -> str:
    """JSON that is safe to embed inside a <script> tag."""
    return json.dumps(obj, separators=(",", ":"), default=str).replace("</", "<\\/")


CSS = """
:root{--plane:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;--rule:#e1e0d9;--axis:#c3c2b7}
*{box-sizing:border-box}
html{color-scheme:light;background:var(--plane)}
body{margin:0;background:var(--plane);color:var(--ink);font-family:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:17px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
a:focus-visible,button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px}
header.top{border-top:6px solid var(--accent);padding:40px 0 8px}
.project{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;font-size:15px;color:var(--ink-2);margin:0 0 28px}
.project b{color:var(--ink);font-weight:700}
h1{font-size:clamp(30px,4.6vw,46px);line-height:1.08;letter-spacing:-.02em;font-weight:800;margin:0;max-width:22ch}
.summary{font-size:19px;color:var(--ink-2);max-width:62ch;margin:18px 0 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin:36px 0 8px;border-top:1px solid var(--rule)}
.kpi{padding:18px 18px 18px 0;border-bottom:1px solid var(--rule)}
.kpi b{display:block;font-size:34px;line-height:1.05;font-weight:800;letter-spacing:-.02em}
.kpi span{display:block;color:var(--ink-2);font-size:15px;margin-top:6px}
.kpi .kpi-note{color:var(--muted);font-size:13px;margin-top:2px}
nav.toc{display:flex;flex-wrap:wrap;gap:6px 18px;margin:22px 0 0;font-size:15px}
nav.toc a{color:var(--ink-2);text-decoration:none;border-bottom:1px solid var(--rule)}
nav.toc a:hover{color:var(--ink);border-color:var(--accent)}
section{padding:44px 0 8px;border-bottom:1px solid var(--rule)}
section:last-of-type{border-bottom:0}
h2{font-size:clamp(22px,3vw,28px);line-height:1.2;letter-spacing:-.01em;font-weight:750;margin:0 0 10px;max-width:40ch}
.lede{color:var(--ink-2);max-width:68ch}
.lede p{margin:0 0 10px}
.lede b{color:var(--ink)}
figure.chart{margin:18px 0 0;background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:12px 8px 6px;overflow:hidden}
.block{margin:18px 0 0}
.note{color:var(--muted);font-size:14px;margin:8px 0 0;max-width:72ch}
details{margin:12px 0 0}
summary{cursor:pointer;color:var(--ink-2);font-size:15px;width:max-content}
.table-wrap{overflow-x:auto;margin:10px 0 0;border:1px solid var(--rule);border-radius:8px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:8px 12px;border-bottom:1px solid var(--rule);text-align:left;white-space:nowrap}
th{color:var(--ink-2);font-weight:650;background:var(--plane);position:sticky;top:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
pre.sql{background:#1f1e1c;color:#f3f1ea;border-radius:8px;padding:14px 16px;overflow-x:auto;font-size:13.5px;line-height:1.5;margin:0}
textarea.sql{width:100%;min-height:150px;background:#1f1e1c;color:#f3f1ea;border:0;border-radius:8px;padding:14px 16px;font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;resize:vertical}
button.run{font:inherit;font-weight:700;font-size:15px;padding:9px 18px;border:0;border-radius:6px;background:var(--accent);color:#fff;cursor:pointer}
button.run:disabled{opacity:.5;cursor:wait}
.qa{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;margin:18px 0 0;align-items:start}
.qa h3{grid-column:1/-1;font-size:17px;margin:10px 0 0}
@media (max-width:760px){.qa{grid-template-columns:minmax(0,1fr)}}
.controls{display:flex;flex-wrap:wrap;gap:12px 18px;align-items:end;margin:0 0 12px}
.controls label{display:flex;flex-direction:column;gap:4px;font-size:14px;color:var(--ink-2)}
.controls select,.controls input{font:inherit;font-size:15px;padding:7px 10px;border:1px solid var(--axis);border-radius:6px;background:#fff;color:var(--ink);min-width:150px}
.controls input[type=range]{padding:0;min-width:200px;accent-color:var(--accent)}
.readout{display:flex;flex-wrap:wrap;gap:12px 32px;margin:8px 0 0}
.readout div b{display:block;font-size:30px;font-weight:800;letter-spacing:-.02em;line-height:1.1}
.readout div span{color:var(--ink-2);font-size:14px}
footer{padding:36px 0 56px;color:var(--ink-2);font-size:15px}
footer p{max-width:72ch;margin:0 0 10px}
@media (max-width:640px){body{font-size:16px}.kpi b{font-size:28px}header.top{padding-top:28px}}
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{project}</title>
<meta name="description" content="{title}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-{plotly}.min.js" charset="utf-8"></script>
<style>:root{{--accent:{accent}}}{css}</style>
</head>
<body>
<header class="top"><div class="wrap">
<p class="project"><span><b>{project}</b></span><span>Tony Mulunda, data portfolio</span></p>
<h1>{title}</h1>
<div class="summary">{summary}</div>
{kpis}
</div></header>
<main class="wrap">{body}</main>
<footer class="wrap">
<p><b>Data.</b> {source}</p>
<p><b>Method.</b> {method}</p>
<p>Built with Python on {built} and rebuilt automatically on every change. Code and data: <a href="https://github.com/{repo}">github.com/{repo}</a>.</p>
</footer>
{scripts}
</body>
</html>
"""
