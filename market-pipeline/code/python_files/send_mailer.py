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
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from build_mailer import build


# Search order for a local, gitignored .env. send_mailer previously read the PROCESS
# ENVIRONMENT only — unlike screener_in_auth.py, which loads a .env itself. So a key
# saved in a .env was never picked up and the mailer silently fell back to writing a
# draft, reporting "no valid GMAIL_APP_PASSWORD set" while the password sat on disk two
# directories away. The inconsistency between the two credential paths WAS the bug.
_ENV_PATHS = (
    Path(__file__).parent / ".env",
    Path.home() / "repos" / "global-stock-screener" / ".env",   # already holds SCREENER_*
    Path.home() / ".env",
)


def _load_dotenv() -> None:
    """Load GMAIL_* / MAIL_TO from the first local .env that has them.

    Existing environment variables WIN — an explicitly exported value should never be
    silently overridden by a file. Same contract as screener_in_auth._load_dotenv.
    """
    for envf in _ENV_PATHS:
        if not envf.exists():
            continue
        try:
            lines = envf.read_text().splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val


def send(subject: str, text: str, html: str) -> bool:
    _load_dotenv()
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("MAIL_TO", user)
    # App Passwords are 16 chars; Google displays them in 4 groups of 4 with spaces and
    # people paste them that way. Strip whitespace rather than rejecting a valid key.
    pw = (pw or "").replace(" ", "").strip()
    if not (user and pw) or len(pw) < 16 or "PUT-YOUR" in pw:
        Path("brief_today.html").write_text(html)
        why = ("GMAIL_USER not set" if not user else
               "GMAIL_APP_PASSWORD not set" if not pw else
               f"GMAIL_APP_PASSWORD is {len(pw)} chars, expected 16" if len(pw) < 16 else
               "GMAIL_APP_PASSWORD is still a placeholder")
        print(f"  NOT SENT — {why}. Saved brief_today.html instead.")
        print(f"  looked for a .env in: {', '.join(str(p) for p in _ENV_PATHS)}")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"  sent '{subject}' → {to}")
    return True


if __name__ == "__main__":
    subject, text, html = build()
    if "--draft" in sys.argv:
        Path("brief_today.html").write_text(html)
        print(f"  draft saved → brief_today.html ({subject})")
    else:
        send(subject, text, html)
