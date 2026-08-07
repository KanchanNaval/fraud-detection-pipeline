# Scheduling the pipeline to run automatically every day

Pick whichever matches your infrastructure — you only need one.

## Option A: Windows Task Scheduler (simplest, if this runs on a work PC/server)

1. Open **Task Scheduler** → **Create Task**
2. **General tab**: Name it "Daily Fraud Detection". Check "Run whether user is logged on or not".
3. **Triggers tab**: New → Daily → pick a time after the business team's daily file usually lands (e.g. 7:00 AM), recur every 1 day.
4. **Actions tab**: New → Program/script:
   ```
   Program: C:\path\to\python.exe
   Arguments: src\main.py
   Start in: C:\path\to\fraud_pipeline
   ```
5. Set the environment variables (email password, webhook URLs) in **System Properties → Environment Variables** first, so the scheduled task can see them.

## Option B: Linux/Mac cron (if this runs on a server)

```bash
crontab -e
```
Add a line to run every day at 7 AM:
```
0 7 * * * cd /path/to/fraud_pipeline && /usr/bin/python3 src/main.py >> logs/run.log 2>&1
```
Set env vars in `~/.bashrc` or a dedicated `/etc/environment` entry so cron picks them up (cron doesn't load your normal shell profile).

## Option C: Cloud scheduler (if the Excel file arrives via SharePoint/email, not a local drop)

This is the more "hands-off business team" version:
- **Power Automate** (if you're in Microsoft 365): trigger "When a file is created in SharePoint folder" → run a script/Azure Function that calls this pipeline → the pipeline still handles detection + notification.
- **Azure Function / AWS Lambda on a timer**: same cron-style schedule as above, but serverless — no machine to keep running.
- **Airflow** (if your org already uses it): a simple `PythonOperator` DAG scheduled `@monthly`.

## Recommended first step

Run it manually for 1–2 weeks first (`python src/main.py`), review the flagged reports with the business team, and tune `config/config.yaml` thresholds based on what they confirm as real fraud vs. false positives. **Then** switch `dry_run: false` and turn on the schedule — this avoids flooding people's inboxes with false positives from day one.

## Important for daily mode: only NEW flags get notified

Each run loads **every** daily file seen so far (not just today's) because
duplicate/frequency rules need history to be accurate — a claim can only be
recognized as a duplicate or a frequent-claimant pattern by comparing it
against prior days. But you're only ever *alerted* on claims that weren't
already in `output/notified_claims_state.json` from a previous run, so the
same flagged claim won't spam the inbox every day. If a claim gets resolved
and should stop appearing in future *reports* entirely (not just
notifications), that's a good next step to add — see "Extending it" in
README.md.
