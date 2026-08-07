"""
Builds and sends the fraud alert notification.

Real credentials should NEVER live in config.yaml — they're pulled from
environment variables (see config's *_env_var keys). Set these on the
machine/server that runs the scheduled job:

    setx FRAUD_ALERT_EMAIL_PASSWORD "..."      (Windows)
    export FRAUD_ALERT_EMAIL_PASSWORD="..."    (Linux/Mac cron)

While dry_run: true in config.yaml, nothing is actually sent — the
generated email HTML and Teams/Slack payloads are written to /output
so you can review exactly what would go out.
"""
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

import requests


def build_html_summary(flagged_df, month_label: str) -> str:
    rows_html = ""
    for _, row in flagged_df.iterrows():
        reasons = "; ".join(row["rule_reasons"]) if row["rule_reasons"] else ""
        if row.get("flag_ml_anomaly"):
            reasons = (reasons + "; " if reasons else "") + "Statistical anomaly (ML)"
        rows_html += f"""
        <tr>
            <td>{row['ClaimID']}</td>
            <td>{row['PolicyID']}</td>
            <td>{row['ClaimantName']}</td>
            <td>{row['ClaimType']}</td>
            <td>${row['ClaimAmount']:,.2f}</td>
            <td>{row['total_score']}</td>
            <td>{reasons}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;">
    <h2>Fraud Alert Summary — {month_label}</h2>
    <p>{len(flagged_df)} claim(s) flagged for review this cycle.</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px;">
        <tr style="background:#f2f2f2;">
            <th>Claim ID</th><th>Policy ID</th><th>Claimant</th><th>Type</th>
            <th>Amount</th><th>Score</th><th>Reason(s)</th>
        </tr>
        {rows_html}
    </table>
    <p style="color:#888;font-size:12px;">Automated fraud screening — review before final determination.</p>
    </body></html>
    """


def send_email(html_body: str, cfg: dict, month_label: str, output_dir: str):
    email_cfg = cfg["notifications"]["email"]
    subject = f"{email_cfg['subject_prefix']} {month_label} — Claims flagged for review"

    if cfg["notifications"]["dry_run"]:
        path = os.path.join(output_dir, "email_preview.html")
        with open(path, "w") as f:
            f.write(html_body)
        print(f"[DRY RUN] Email not sent. Preview saved to {path}")
        return

    password = os.environ.get(email_cfg["sender_password_env_var"])
    if not password:
        raise RuntimeError(
            f"Missing env var {email_cfg['sender_password_env_var']} for email password."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg["sender_email"]
    msg["To"] = ", ".join(email_cfg["recipients"])
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
        server.starttls()
        server.login(email_cfg["sender_email"], password)
        server.sendmail(email_cfg["sender_email"], email_cfg["recipients"], msg.as_string())
    print(f"Email sent to {email_cfg['recipients']}")


def send_teams_message(flagged_df, cfg: dict, month_label: str, output_dir: str):
    facts = [
        {"name": "Claims flagged", "value": str(len(flagged_df))},
        {"name": "Period", "value": month_label},
        {"name": "Highest score", "value": str(int(flagged_df["total_score"].max())) if len(flagged_df) else "0"},
    ]
    top_claims = "; ".join(
        f"{r['ClaimID']} (${r['ClaimAmount']:,.0f})" for _, r in flagged_df.head(5).iterrows()
    )

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": "Fraud Alert Summary",
        "themeColor": "D9534F",
        "title": f"Fraud Alert — {month_label}",
        "sections": [{
            "activityTitle": f"{len(flagged_df)} claim(s) flagged for review",
            "facts": facts,
            "text": f"Top flagged claims: {top_claims}" if len(flagged_df) else "No claims flagged this cycle.",
        }],
    }

    if cfg["notifications"]["dry_run"]:
        path = os.path.join(output_dir, "teams_preview.json")
        with open(path, "w") as f:
            json.dump(card, f, indent=2)
        print(f"[DRY RUN] Teams message not sent. Preview saved to {path}")
        return

    webhook_url = os.environ.get(cfg["notifications"]["teams"]["webhook_url_env_var"])
    if not webhook_url:
        raise RuntimeError("Missing Teams webhook URL env var.")
    resp = requests.post(webhook_url, json=card, timeout=15)
    resp.raise_for_status()
    print("Teams message sent.")


def send_slack_message(flagged_df, cfg: dict, month_label: str, output_dir: str):
    text = (f"*Fraud Alert — {month_label}*\n"
            f"{len(flagged_df)} claim(s) flagged for review.\n")
    for _, r in flagged_df.head(10).iterrows():
        reasons = "; ".join(r["rule_reasons"])
        text += f"• `{r['ClaimID']}` — {r['ClaimantName']} — ${r['ClaimAmount']:,.0f} — {reasons}\n"

    payload = {"text": text}

    if cfg["notifications"]["dry_run"]:
        path = os.path.join(output_dir, "slack_preview.json")
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[DRY RUN] Slack message not sent. Preview saved to {path}")
        return

    webhook_url = os.environ.get(cfg["notifications"]["slack"]["webhook_url_env_var"])
    if not webhook_url:
        raise RuntimeError("Missing Slack webhook URL env var.")
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    print("Slack message sent.")


def notify(flagged_df, cfg: dict, month_label: str, output_dir: str):
    if cfg["notifications"]["send_email"]:
        html = build_html_summary(flagged_df, month_label)
        send_email(html, cfg, month_label, output_dir)
    if cfg["notifications"]["send_teams"]:
        send_teams_message(flagged_df, cfg, month_label, output_dir)
    if cfg["notifications"]["send_slack"]:
        send_slack_message(flagged_df, cfg, month_label, output_dir)
