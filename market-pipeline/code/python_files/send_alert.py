#!/usr/bin/env python3
# send_alert.py
# ==============
# Short failure-alert email for daily_pipeline.sh — sent when one or more
# pipeline steps fail, separate from (and usually arriving before) the main
# daily brief. Reuses the same Gmail SMTP credentials as send_mailer.py
# (GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO); if they aren't configured this
# just logs what it would have sent instead of failing the pipeline.
#
#   python3 send_alert.py "US full market scan" "Japan full market scan"

from __future__ import annotations

import datetime as _dt
import os
import smtplib
import sys
from email.mime.text import MIMEText


def send_alert(failed_steps: list) -> bool:
    if not failed_steps:
        return True
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("MAIL_TO", user)
    today = _dt.date.today().strftime("%d %b %Y")
    log_name = f"daily_pipeline_{_dt.date.today().strftime('%Y%m%d')}.log"
    subject = f"⚠️ Daily Market Brief — {len(failed_steps)} step(s) failed ({today})"
    body = (
        f"{len(failed_steps)} step(s) failed in today's daily_pipeline.sh run ({today}):\n\n"
        + "\n".join(f"  - {s}" for s in failed_steps)
        + f"\n\nEach failed step falls back to cached/skipped data — the rest of the "
        f"pipeline still ran. Check {log_name} for details."
    )
    if not (user and pw) or len(pw) < 16 or "PUT-YOUR" in pw:
        print(f"  [alert] no valid GMAIL_APP_PASSWORD set — alert not sent. Would have said:\n{body}")
        return False
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"  [alert] sent '{subject}' -> {to}")
    return True


if __name__ == "__main__":
    send_alert(sys.argv[1:])
