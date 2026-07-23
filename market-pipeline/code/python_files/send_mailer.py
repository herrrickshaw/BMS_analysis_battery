#!/usr/bin/env python3
# send_mailer.py
# ==============
# Build the Daily Market Brief and SEND it by email — with ZERO Claude/LLM tokens.
# This is the token-free replacement for the Gmail-draft-via-MCP step: pure Python
# + Gmail SMTP, so it can run unattended from cron/launchd.
#
# Credentials via environment (never hard-code):
#   GMAIL_USER          your gmail address
#   GMAIL_APP_PASSWORD  a Google "App Password" (Account → Security → App passwords)
#   MAIL_TO             recipient (defaults to GMAIL_USER)
#
#   python3 send_mailer.py            # build + send (or save .html if no creds)
#   python3 send_mailer.py --draft    # just write brief_today.html, don't send
#
# Nothing here calls an LLM: data, screeners, sentiment (VADER) and assembly are
# all local. The only network is market data + the SMTP send.

from __future__ import annotations

import os

import env_loader as _env
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from build_mailer import build


def _digest_section() -> tuple:
    """(html, subject_suffix) for the watchlist digest, appended below the
    brief so the morning is ONE email, not two (user, 2026-07-23).

    Failure-isolated on purpose: the digest importing half the pipeline must
    never block the brief — a broken digest renders as an error strip and the
    brief still ships. Running it here also runs watchlist hygiene (entry
    backfill, sell-zone eviction, >3-week purge) exactly once per morning.
    """
    try:
        import pandas as pd
        import watchlist_digest as W
        wl_path = Path(W.__file__).resolve().parent / "watchlist.csv"
        wl = pd.read_csv(wl_path)
        wl, evicted, purged, changed = W.maintain(wl)
        if changed:
            wl.to_csv(wl_path, index=False)
        if evicted:
            print("  digest: evicted " + ", ".join(evicted))
        if purged:
            print("  digest: purged " + ", ".join(purged))
        rows = W.build_rows(wl)
        W.assign_sectors(rows)
        as_of = max([r["last"] for r in rows if r["last"]] or ["?"])
        held = [r for r in rows if r.get("status", "held") == "held"]
        up = sum(1 for r in held if r["mark"] == "🟢")
        dn = sum(1 for r in held if r["mark"] == "🔴")
        # body = trimmed (stays under Gmail's ~102KB clip); attachment = the
        # SAME rows rendered untrimmed — attachments don't count toward the
        # clip, so nothing is lost, only demoted a click away.
        return (W.render(rows, as_of, purged=purged),
                f" + 📊 Watchlist ({up}↑ {dn}↓ of {len(held)} held)",
                W.render(rows, as_of, purged=purged, full=True))
    except Exception as e:  # noqa: BLE001 — isolation is the whole point
        print(f"  digest section failed (brief still sent): {str(e)[:120]}")
        return (f'<p style="color:#ca3433;font-size:12px">watchlist digest '
                f'failed this morning: {str(e)[:200]}</p>', "", None)


def send(subject: str, text: str, html: str, attachments=None) -> bool:
    """attachments: optional [(filename, html_str), ...] — attached as
    text/html files. Attachments don't count toward Gmail's ~102KB clip, which
    is exactly why the full digest rides here while the body stays trimmed."""
    user = _env.get("GMAIL_USER")
    pw = _env.get("GMAIL_APP_PASSWORD")
    to = (_env.get("MAIL_TO") or user)
    if not (user and pw) or len(pw) < 16 or "PUT-YOUR" in pw:
        Path("brief_today.html").write_text(html)
        print("  no valid GMAIL_APP_PASSWORD set — saved brief_today.html instead of sending")
        return False
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text, "plain"))
    alt.attach(MIMEText(html, "html"))
    if attachments:
        msg = MIMEMultipart("mixed")
        msg.attach(alt)
        for fname, content in attachments:
            part = MIMEText(content, "html")
            part.add_header("Content-Disposition", "attachment", filename=fname)
            msg.attach(part)
    else:
        msg = alt
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"  sent '{subject}' → {to}"
          + (f" (+{len(attachments)} attachment)" if attachments else ""))
    return True


if __name__ == "__main__":
    import datetime as _dt

    subject, text, html = build()
    digest_html, digest_subj, digest_full = _digest_section()
    html = (html
            + '<div style="margin:22px 0 10px;border-top:3px solid #0B2F4A"></div>'
            + digest_html)
    subject += digest_subj
    attachments = None
    if digest_full:
        fname = f"watchlist_full_{_dt.date.today():%Y-%m-%d}.html"
        attachments = [(fname, digest_full)]
    if "--draft" in sys.argv:
        Path("brief_today.html").write_text(html)
        if digest_full:
            Path("watchlist_full.html").write_text(digest_full)
            print("  full digest draft → watchlist_full.html")
        print(f"  draft saved → brief_today.html ({subject})")
    else:
        send(subject, text, html, attachments=attachments)
