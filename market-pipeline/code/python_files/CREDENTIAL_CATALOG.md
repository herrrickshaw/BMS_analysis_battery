# Credential Catalog

**Single source of truth for every data-fetch secret on this machine.**
Names and provenance only — **no values live in this file** (it is tracked).

## Where the secrets actually live

```
~/.config/market-secrets/credentials.env      # canonical store — dir 700, file 600, gitignored
```

Everything resolves through [`env_loader.py`](env_loader.py) → `env_loader.get("KEY")`.
Precedence: `os.environ` → canonical store → legacy `.env` → `~/.env.local`.
The legacy files are still read as a fallback during migration; once every fetch
is confirmed green they can be emptied. **Rotate a key in the canonical file
only — one edit, every consumer picks it up.**

Regenerate the canonical file from the (still-present) legacy stores with
`scratchpad/consolidate_secrets.py`. It masks all values in its output.

## The catalog

| Key | Provider | Feeds / data | Consumed by |
|---|---|---|---|
| `ALPHAVANTAGE_KEY` | Alpha Vantage | prices, fundamentals, news sentiment | `sentiment_pipeline.py`, `earnings_dates_dart.py` |
| `DART_KEY` | DART (KR OpenDART) | Korea corporate filings / fundamentals | `dart_fundamentals.py`, `earnings_dates_dart.py` |
| `EODHD_KEY` | EOD Historical Data | earnings calendar, EOD prices | `earnings_dates_dart.py` |
| `MARKETAUX_KEY` | Marketaux | market news | `sentiment_pipeline.py`, `earnings_dates_dart.py` |
| `NEWSAPI_KEY` | NewsAPI.org | headlines | `earnings_dates_dart.py` |
| `NEWSDATA_KEY` | NewsData.io | headlines | `sentiment_pipeline.py`, `earnings_dates_dart.py` |
| `FRED_API_KEY` | FRED (St. Louis Fed) | FX rates, macro series | `liquidity.py` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Google Gemini | LLM extraction | `llm_extract.py` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq | LLM extraction | `llm_extract.py` |
| `GROW_API_KEY` / `GROW_API_SECRET` | Groww | India broker / quotes | (broker layer) |
| `JQUANTS_API_KEY` | J-Quants | Japan fundamentals | `jquants_validator.py` |
| `SCREENER_EMAIL` / `SCREENER_PASSWORD` | screener.in | India 10y fundamentals | `decision_log.py`, `backtest_screeners.py` |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` / `MAIL_TO` | Gmail SMTP | brief + digest delivery | `env_loader` consumers, `watchlist_digest.py` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS (`default`) | EC2 global collection | boto3 / AWS CLI |
| `AWS_DATA_COLLECTOR_ACCESS_KEY_ID` / `..._SECRET_ACCESS_KEY` | AWS (`data-collector`) | EC2 collector profile | boto3 (profile) |

> **AWS note:** boto3 and the AWS CLI also read `~/.aws/credentials` natively by
> profile — the canonical env copy is for scripts that expect `AWS_*` env vars.
> Keep the two in sync when rotating, or point boto3 at the env copy explicitly.

## Rules (standing user policy)

- Real values live **only** in gitignored, machine-local, mode-600 files.
- Tracked files (this one, `*.example`) carry **names/placeholders**, never values.
- `~/` is a **public** git repo — the canonical folder is double-gitignored
  (home `.gitignore` + a `*` gitignore inside the folder). Never relax that.
- Never echo a secret to a terminal, log, or agent transcript.
