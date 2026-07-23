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
        frames = {}
        rows = W.build_rows(wl, frames_out=frames)
        W.assign_sectors(rows)
        W.assign_recommendations(rows)
        as_of = max([r["last"] for r in rows if r["last"]] or ["?"])
        # picks-based subject: the digest is portfolio-free (2026-07-23), so
        # the subject counts what the ANALYSIS found, not what is held
        picks = [r for r in rows if r.get("status") in ("watch", "signal", "justified")
                 and not r.get("missing") and not r.get("below_floor")]
        buy_n = sum(1 for r in picks if r.get("rec", r.get("zone")) == "BUY")
        new_n = sum(1 for r in picks
                    if r.get("days_in") is not None and r["days_in"] <= 1)
        # charts (treemap / RRG / breadth) — fail-soft PNGs. Body references
        # them as cid: inline images (image MIME parts do NOT count toward
        # Gmail's ~102KB HTML clip); the full attachment inlines them as data:
        # URIs so it stays a self-contained file.
        pngs = {}
        try:
            import watchlist_viz as V
            pngs = V.build_all(rows, frames, W.zone_series)
        except Exception as ve:  # noqa: BLE001
            print(f"  digest charts skipped: {str(ve)[:100]}")
        import base64
        cid_refs = {k: f"cid:{k}" for k in pngs}
        data_refs = {k: "data:image/png;base64," + base64.b64encode(v).decode()
                     for k, v in pngs.items()}
        # model portfolios: monthly-rebalanced co-movement bundles of the picks
        bundle_vals = []
        try:
            import portfolio_bundles as PB
            analysis = [r for r in rows
                        if r.get("status") in ("watch", "signal", "justified")]
            store = PB.maybe_build(analysis, frames)
            bundle_vals = PB.value(store, analysis, frames)
            if bundle_vals:
                print(f"  bundles: {len(bundle_vals)} model portfolios "
                      f"(built {store.get('built')})")
        except Exception as be:  # noqa: BLE001
            print(f"  bundles skipped: {str(be)[:100]}")
        # body = trimmed (stays under Gmail's ~102KB clip); attachment = the
        # SAME rows rendered untrimmed — attachments don't count toward the
        # clip, so nothing is lost, only demoted a click away.
        return (W.render(rows, as_of, purged=purged, images=cid_refs,
                         bundles=bundle_vals),
                f" + 📊 Picks ({len(picks)} · {buy_n} buy-zone · "
                f"{len(bundle_vals)} bundles)",
                W.render(rows, as_of, purged=purged, full=True, images=data_refs,
                         bundles=bundle_vals),
                pngs)
    except Exception as e:  # noqa: BLE001 — isolation is the whole point
        print(f"  digest section failed (brief still sent): {str(e)[:120]}")
        return (f'<p style="color:#ca3433;font-size:12px">watchlist digest '
                f'failed this morning: {str(e)[:200]}</p>', "", None, {})


def send(subject: str, text: str, html: str, attachments=None,
         inline_images=None) -> bool:
    """attachments: optional [(filename, html_str), ...] — attached as
    text/html files. inline_images: optional {cid: png_bytes} referenced from
    the body as <img src="cid:...">. Neither counts toward Gmail's ~102KB HTML
    clip, which is exactly why charts and the full digest ride here while the
    body stays trimmed.

    MIME shape: mixed( related( alternative(text, html), images... ), files )
    """
    from email.mime.image import MIMEImage

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
    core = alt
    if inline_images:
        core = MIMEMultipart("related")
        core.attach(alt)
        for cid, png in inline_images.items():
            img = MIMEImage(png, "png")
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
            core.attach(img)
    if attachments:
        msg = MIMEMultipart("mixed")
        msg.attach(core)
        for fname, content in attachments:
            part = MIMEText(content, "html")
            part.add_header("Content-Disposition", "attachment", filename=fname)
            msg.attach(part)
    else:
        msg = core
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
    digest_html, digest_subj, digest_full, pngs = _digest_section()
    html = (html
            + '<div style="margin:22px 0 10px;border-top:3px solid #0B2F4A"></div>'
            + digest_html)
    subject += digest_subj
    attachments = None
    if digest_full:
        fname = f"watchlist_full_{_dt.date.today():%Y-%m-%d}.html"
        attachments = [(fname, digest_full)]
    # bundle-validation report (monthly refresh, [16c]) rides as a small HTML
    # attachment so the "are we closet-indexing?" answer travels with the picks
    bv = Path("reports/bundle_validation.md")
    if attachments and bv.exists():
        import re as _re
        md = bv.read_text()
        h = md
        h = _re.sub(r"^## (.+)$", r'<h2 style="color:#0B2F4A;font-size:15px;margin:14px 0 4px">\1</h2>', h, flags=_re.M)
        h = _re.sub(r"^# (.+)$", r'<h1 style="color:#0B2F4A;font-size:18px">\1</h1>', h, flags=_re.M)
        h = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
        h = _re.sub(r"^- (.+)$", r'<div style="margin:2px 0 2px 12px">• \1</div>', h, flags=_re.M)
        h = ('<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
             'max-width:680px;font-size:13px;color:#333;background:#eef4f6;'
             'padding:14px;border-radius:8px">'
             + h.replace("\n\n", "<br>") + "</div>")
        attachments.append((f"bundle_validation_{_dt.date.today():%Y-%m}.html", h))
    if "--draft" in sys.argv:
        Path("brief_today.html").write_text(html)
        if digest_full:
            Path("watchlist_full.html").write_text(digest_full)
            print("  full digest draft → watchlist_full.html")
        for k, v in pngs.items():
            Path(f"digest_{k}.png").write_bytes(v)
        if pngs:
            print(f"  charts → {', '.join('digest_' + k + '.png' for k in pngs)}")
        print(f"  draft saved → brief_today.html ({subject})")
    else:
        send(subject, text, html, attachments=attachments, inline_images=pngs)
