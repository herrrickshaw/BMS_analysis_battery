#!/usr/bin/env python3
"""
llm_extract.py
==============
Generic "unstructured document -> structured JSON" extraction, using the
repo's existing Groq (OpenAI-compatible) LLM pattern (see repo-inventory/
canonicalize.py) with a Gemini fallback -- both already configured via
~/.env.local for the "AI Advisor" feature.

Derived from patents MY269019 "System and method for generating queryable
structured document from an unstructured document using machine learning"
(IIIT-Hyderabad, LTRC) and MY269128 "System for extracting and analyzing
nutritional information from food labels using a large language model"
(IIIT-Hyderabad, MLL) -- same core technique (unstructured text -> a fixed
schema via an LLM), applied here to two places in this repo that currently
rely on brittle regex/layout parsing:
  - SEBI DRHP filing text (SEBI_web_scraper.ipynb)
  - Portfolio broker-statement text (portfolio.py's PDF parsing)

Usage:
    from llm_extract import extract_structured

    schema = {
        "company_name": "string",
        "issue_size_cr": "number, issue size in INR crore",
        "price_band_low": "number",
        "price_band_high": "number",
        "listing_exchange": "string, e.g. NSE/BSE/both",
    }
    result = extract_structured(drhp_text, schema)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional


def _load_env_local() -> dict:
    """Minimal .env.local loader (avoids a hard python-dotenv dependency)."""
    env_path = Path.home() / ".env.local"
    values: dict = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def _client_and_model(provider: str):
    """Returns (openai.OpenAI-compatible client, model_name) for the given provider."""
    env = {**_load_env_local(), **os.environ}
    from openai import OpenAI

    if provider == "groq":
        key = env.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY not found in ~/.env.local or environment")
        return (OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1"),
                env.get("GROQ_MODEL", "llama-3.3-70b-versatile"))
    if provider == "gemini":
        key = env.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not found in ~/.env.local or environment")
        return (OpenAI(api_key=key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/"),
                env.get("GEMINI_MODEL", "gemini-2.0-flash"))
    raise ValueError(f"unknown provider {provider!r}")


def _extract_json(text: str) -> dict:
    """Pull the first {...} JSON object out of a model response (models sometimes wrap it in prose or ```json fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found in model response: {text[:200]!r}")
    return json.loads(match.group(0))


def extract_structured(
    text: str,
    schema: dict,
    instructions: str = "",
    provider: str = "groq",
    fallback_provider: Optional[str] = "gemini",
) -> dict:
    """
    Extract a JSON object matching *schema* out of unstructured *text* using
    an LLM. *schema* maps field name -> a short description of what to put
    there (used verbatim in the prompt, not validated as a JSON-schema spec --
    kept simple since every caller here just wants a flat field->value dict).

    Falls back to *fallback_provider* if the primary provider's call or JSON
    parse fails, then raises if that fails too -- callers should catch and
    degrade gracefully (e.g. skip the field, don't crash a whole report).
    """
    schema_lines = "\n".join(f'  "{k}": {v}' for k, v in schema.items())
    prompt = (
        "Extract the following fields from the document text below. "
        "Respond with ONLY a single JSON object -- no prose, no markdown fences. "
        "Use null for any field not present in the text.\n\n"
        f"Fields:\n{schema_lines}\n\n"
        f"{instructions}\n\n"
        f"Document text:\n{text}"
    )

    providers = [provider] + ([fallback_provider] if fallback_provider else [])
    last_error = None
    for p in providers:
        try:
            client, model = _client_and_model(p)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            return _extract_json(resp.choices[0].message.content)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"extract_structured failed on all providers {providers}: {last_error}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="LLM structured extraction demo")
    ap.add_argument("--demo", choices=["drhp", "portfolio"], default="drhp")
    args = ap.parse_args()

    if args.demo == "drhp":
        sample_text = (
            "Vantage Cold Chain Logistics Limited proposes to raise up to "
            "Rs. 850 crore through a fresh issue of equity shares, with a "
            "price band of Rs. 210 to Rs. 222 per equity share of face value "
            "Rs. 10 each. The equity shares are proposed to be listed on both "
            "BSE and NSE. The issue opens on 14 August and closes on 18 August."
        )
        schema = {
            "company_name": "string",
            "issue_size_cr": "number, total issue size in INR crore",
            "price_band_low": "number",
            "price_band_high": "number",
            "listing_exchange": "string, e.g. NSE/BSE/both",
        }
    else:
        sample_text = (
            "Holdings as of statement date: 120 shares of RELIANCE INDUSTRIES LTD "
            "purchased at an average price of Rs 2,410.50; 40 shares of TCS at "
            "average cost Rs 3,550.00; cash balance Rs 15,230.75."
        )
        schema = {
            "holdings": "array of {symbol, quantity, avg_price}",
            "cash_balance": "number",
        }

    result = extract_structured(sample_text, schema)
    print(json.dumps(result, indent=2))
