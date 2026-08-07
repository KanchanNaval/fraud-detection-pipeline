# Daily Insurance Fraud Detection Pipeline

Automatically screens the business team's daily claims Excel file for
potential fraud, and sends an alert (email + Teams, Slack optional) listing
**only the newly flagged claims** — no manual review, and no repeat alerts
about a claim you were already told about yesterday.

## How it works

```
data/daily_claims_2026-08-08.xlsx   (today's file)
data/daily_claims_2026-08-07.xlsx   (yesterday's — still loaded, for context)
data/daily_claims_...xlsx           (every prior day)
        │
        ▼  all combined into one history
   src/main.py  ──►  src/rules.py       (5 explainable business rules)
                 ──►  src/ml_model.py    (Isolation Forest anomaly detection)
                 ──►  combined fraud score per claim
        │
        ▼  compare against output/notified_claims_state.json
   only claims never notified before →  src/notify.py  ──►  Email + Teams + Slack
        │
        ▼
   output/fraud_report_<date>.xlsx     (full audit trail, every flagged claim + score)
```

**Why the pipeline reloads every prior day's file, not just today's:** the
duplicate-claim and claim-frequency rules only work by comparing a claim
against history. A claim looks perfectly normal in isolation but suspicious
once you see the claimant filed two more just like it last week — so today's
file alone isn't enough context.

## Current detection logic

**Rules (explainable, tunable in `config/config.yaml`):**
| Rule | What it catches |
|---|---|
| Early claim | Claim filed within 30 days of policy start |
| High amount | Claim ≥ 85% of coverage limit |
| Duplicate | Same policy + same amount, filed within 7 days |
| Frequency | Same claimant with ≥3 claims in trailing 12 months |
| Data integrity | Missing fields, or claim date before policy start |

**ML layer:** Isolation Forest flags claims that are numerically unusual
(amount, timing, claimant frequency) even if no single rule catches them.
No labeled fraud history needed to start. Once you have a few months of
confirmed fraud/not-fraud outcomes, this can be swapped for a supervised
model for better precision.

**Scoring:** each triggered rule = 1 point, ML anomaly = 2 points, flagged
if total ≥ 2. Fully adjustable in `config/config.yaml`.

## Running it

```bash
cd fraud_pipeline
pip install -r requirements.txt
python src/main.py
```

Drop each day's real file into `data/` (matching the naming pattern
`daily_claims_YYYY-MM-DD.xlsx` and the required columns listed in
`config.yaml`) and the pipeline automatically combines it with every prior
day already sitting in that folder — keep old daily files there, don't
delete them, since the duplicate/frequency rules depend on that history.

## Before going live

1. **Keep `dry_run: true`** (default) for the first few runs — it writes the
   email/Teams/Slack content to `output/` instead of sending, so you can
   sanity-check what the business team would actually receive.
2. **Set real credentials as environment variables** (never in config.yaml):
   - `FRAUD_ALERT_EMAIL_PASSWORD`
   - `FRAUD_ALERT_TEAMS_WEBHOOK`
   - `FRAUD_ALERT_SLACK_WEBHOOK` (if enabling Slack)
3. **Tune thresholds** in `config/config.yaml` with the business team after
   reviewing a couple of months of flagged output — this is the step that
   turns "a lot of false positives" into "a trusted alert."
4. **Flip `dry_run: false`** and set up the schedule — see `SCHEDULING.md`.

## Extending it

- New pattern the business team spots? Add a function to `src/rules.py`
  and register it in `apply_all_rules()`.
- Column names differ from the sample? Update `required_columns` in
  `config.yaml` and the corresponding references in `src/rules.py`.
- Want a Power BI / Excel dashboard of trends over time instead of just
  daily alerts? `output/fraud_report_*.xlsx` files accumulate every run —
  point a Power BI report at that folder.
- A claim gets investigated and cleared, but keeps showing up in the daily
  full report (it won't re-*notify*, but it stays in the audit trail by
  design)? Add a simple `resolved_claims.json` allow-list the business team
  can update, and filter it out in `main.py` before the report is saved.
- As `data/` accumulates months of daily files, loading all of them every
  run gets slower. At that point, switch `load_all_claims()` to read from a
  single running Parquet/SQLite file instead of re-reading every Excel file
  from scratch — happy to help set that up when you're there.
