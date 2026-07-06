#!/usr/bin/env python3
"""
_build_repo_pages.py — generate the multi-page repository site from one data
table (DRY). Produces docs/repos.html (hub) + docs/repo/<slug>.html per repo.

Run:  python3 docs/_build_repo_pages.py
"""
from pathlib import Path

DOCS = Path(__file__).parent
(REPO_DIR := DOCS / "repo").mkdir(exist_ok=True)
GH = "https://github.com/herrrickshaw"

# ── One row per repository (the single source of truth) ───────────────────────
REPOS = [
    {
        "slug": "retail-outlet-data", "name": "Retail-outlet-data", "lang": "HTML/Python",
        "status": "active", "url": f"{GH}/Retail-outlet-data",
        "pages": "https://herrrickshaw.github.io/Retail-outlet-data/",
        "tagline": "The Stock Analysis System — flagship quantitative platform.",
        "about": "Full NSE/BSE/NASDAQ/NYSE analysis platform: 6 screeners, walk-forward "
                 "backtesting, ML signals, news sentiment (IN + US), MPT portfolio builder, "
                 "Docker packaging, and this website. 13 tagged releases (v1.0.0 → v3.13.x).",
        "highlights": [
            "6 screeners: Darvas, Golden Cross, Piotroski, Coffee Can, Magic Formula, Bull Cartel",
            "Two pipelines: fundamentals (offline) + news sentiment (live RSS/APIs)",
            "Portfolio builder: efficient frontier, beta vs Nifty 50, yield-target weights",
            "Parquet cache (5-yr OHLC), C/R acceleration, DDD architecture",
            "Daily combined report emailed with convergence highlights",
        ],
        "structure": ["Downloads/*.py — analysis modules", "stock_ddd/ — DDD layers",
                      "docs/ — this website", "STOCK_ANALYSIS_SYSTEM.md, APPROACHES.md, SCREENER_BASIS.md"],
    },
    {
        "slug": "claude-stock-tools", "name": "claude-stock-tools", "lang": "Python",
        "status": "active", "url": f"{GH}/claude-stock-tools",
        "tagline": "Curated, organised toolkit of daily-report & screener scripts.",
        "about": "A tidied collection of the stock tooling, organised into numbered "
                 "workstreams for daily reporting, screening, Colab notebooks, strategy "
                 "reference and data enrichment. Has its own README and CHANGELOG.",
        "highlights": [
            "01_daily_reports — scheduled report generators",
            "02_market_screeners — screener implementations",
            "03_colab_notebooks — interactive analysis notebooks",
            "04_strategy_reference — strategy risk/reward cards",
            "05_enrichment — PE zones, company names, metadata",
        ],
        "structure": ["01_daily_reports/", "02_market_screeners/", "03_colab_notebooks/",
                      "04_strategy_reference/", "05_enrichment/", "README.md · CHANGELOG.md"],
    },
    {
        "slug": "global-market-scanners", "name": "global-market-scanners", "lang": "Python",
        "status": "active", "url": f"{GH}/global-market-scanners",
        "tagline": "Full-universe screeners across 5 global markets.",
        "about": "Standalone full-market scanners applying the 6-screener suite to "
                 "European, Indian, Japanese, Korean and US equity universes — one "
                 "self-contained script per market.",
        "highlights": [
            "full_indian_market_scan.py — NSE + BSE",
            "full_us_market_scan.py — NASDAQ + NYSE",
            "full_european_market_scan.py — European exchanges",
            "full_japan_market_scan.py — TSE",
            "full_korea_market_scan.py — KRX",
        ],
        "structure": ["full_<market>_market_scan.py × 5", "README.md"],
    },
    {
        "slug": "subscription-model-revenue", "name": "subscription-model-revenue", "lang": "Python",
        "status": "active", "url": f"{GH}/subscription-model-revenue",
        "tagline": "Revenue & cost-recovery modelling — DISCOM debt + subscription seasonality.",
        "about": "Revenue and cost-recovery scenario models. Includes a DISCOM "
                 "(electricity distribution company) debt-reduction calculator that shows "
                 "how consumer power-billing levers — tariff hikes, AT&C loss reduction, "
                 "collection efficiency, subsidy timeliness — close the ACS-ARR gap and "
                 "pay down debt, with the consumer affordability trade-off made explicit; "
                 "plus a Dirichlet off-month subscription-revenue simulation.",
        "highlights": [
            '<a href="../discom-calculator.html"><b>▶ Interactive DISCOM token-charge calculator (live)</b></a>',
            "discom_debt_calculator.py — DISCOM debt-reduction scenarios + consumer-bill impact",
            "Token-charge model: net = charge × connections × 12 × efficiency × (1−admin)",
            "Scenario table (₹1–₹100/mo) + charge×efficiency sensitivity heatmap",
            "random_numbers_using_dirichlet.py — Dirichlet revenue-share simulation",
        ],
        "structure": ["discom_debt_calculator.py", "random_numbers_using_dirichlet.py", "README.md"],
        "live": "../discom-calculator.html",
    },
    {
        "slug": "colab-experiments", "name": "colab-experiments", "lang": "Python",
        "status": "experiment", "url": f"{GH}/colab-experiments",
        "tagline": "Standalone Colab/ML experiments.",
        "about": "A scratchpad of Google Colab experiments — currently an image "
                 "restoration/colorization experiment (DeOldify).",
        "highlights": ["deoldify.py — image colorization (DeOldify) experiment"],
        "structure": ["deoldify.py"],
    },
]

CSS = '<link rel="stylesheet" href="{rel}style.css">'
DISC = ('<div class="disc">⚠️ Educational/research only. NOT investment advice. '
        'Past results do not guarantee future returns.</div>')


def page(repo) -> str:
    hl = "\n".join(f"<li>{h}</li>" for h in repo["highlights"])
    st = "\n".join(f"<li><code>{s}</code></li>" for s in repo["structure"])
    pages_link = (f' · <a href="{repo["pages"]}">Live site ↗</a>'
                  if repo.get("pages") else "")
    tagcls = "t-active" if repo["status"] == "active" else "t-exp"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{repo['name']} — Repository</title>{CSS.format(rel='../')}</head><body>
<header><div class="wrap">
  <div class="crumb"><a href="../repos.html">← All repositories</a></div>
  <h1>{repo['name']} <span class="tag {tagcls}">{repo['status']}</span></h1>
  <div class="sub">{repo['tagline']}</div>
  <div class="pills"><span class="pill">Lang <b>{repo['lang']}</b></span>
    <span class="pill"><a href="{repo['url']}">GitHub ↗</a></span></div>
</div></header>
<nav><div class="wrap">
  <a href="../index.html">Stock System</a>
  <a href="../repos.html" class="active">Repositories</a>
  <a href="{repo['url']}">View on GitHub</a>
</div></nav>
<div class="wrap">
  <section><h2>About</h2><p class="lead">{repo['about']}</p>
    <h3>Highlights</h3><ul>{hl}</ul>
    <h3>Structure</h3><ul>{st}</ul>
    <p style="margin-top:14px"><a href="{repo['url']}">Open {repo['name']} on GitHub ↗</a>{pages_link}</p>
  </section>{DISC}
</div>
<footer><a href="../repos.html">All repositories</a> · <a href="{GH}">github.com/herrrickshaw</a></footer>
</body></html>"""


def hub() -> str:
    cards = ""
    for r in REPOS:
        tagcls = "t-active" if r["status"] == "active" else "t-exp"
        cards += f"""<div class="card"><h3>{r['name']}<span class="lang">{r['lang']}</span></h3>
      <p><span class="tag {tagcls}">{r['status']}</span> {r['tagline']}</p>
      <a class="go" href="repo/{r['slug']}.html">Details →</a> &nbsp;
      <a class="go" href="{r['url']}">GitHub ↗</a></div>\n"""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Repositories — herrrickshaw</title>{CSS.format(rel='')}</head><body>
<header><div class="wrap">
  <h1>📚 Repositories</h1>
  <div class="sub">Projects on github.com/herrrickshaw — each documented on its own page.</div>
  <div class="pills"><span class="pill"><b>{len(REPOS)}</b> repositories</span>
    <span class="pill"><b>{sum(1 for r in REPOS if r['status']=='active')}</b> active</span></div>
</div></header>
<nav><div class="wrap">
  <a href="index.html">Stock System</a>
  <a href="repos.html" class="active">Repositories</a>
  <a href="{GH}">GitHub Profile</a>
</div></nav>
<div class="wrap"><section><h2>All projects</h2>
  <p class="lead">Click any repository for its dedicated page.</p>
  <div class="grid">{cards}</div></section>{DISC}</div>
<footer><a href="{GH}">github.com/herrrickshaw</a> · Educational/research only — NOT investment advice</footer>
</body></html>"""


def main():
    (DOCS / "repos.html").write_text(hub())
    print("wrote docs/repos.html")
    for r in REPOS:
        (REPO_DIR / f"{r['slug']}.html").write_text(page(r))
        print(f"wrote docs/repo/{r['slug']}.html")
    print(f"\n{len(REPOS)} repository pages generated.")


if __name__ == "__main__":
    main()
